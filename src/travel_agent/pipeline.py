"""Shared Flow steps (code, identical for A/B/C): intake -> ask_car -> weather_step -> build_candidates
-> DECIDE (system-specific) -> final_checks -> route -> render."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from . import config as C
from . import tools as T
from .data_access import get_catalog
from .models import DayCondition, Status, TripRequest, WeatherStatus
from .timeutil import hm_to_min, iso_local_hm, min_to_hm
from .tool_log import ToolLog


class StepOutcome(Exception):
    """Raised by a shared step to end the run with a code-decided status."""

    def __init__(self, status: Status, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ----------------------------------------------------------------- intake / ask_car
def intake(raw: Any) -> TripRequest:
    if isinstance(raw, TripRequest):
        req = raw
    else:
        try:
            req = TripRequest.model_validate(raw)
        except ValidationError as e:
            raise StepOutcome(Status.INVALID_REQUEST, "invalid request: " + "; ".join(
                f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors())) from e
    cat = get_catalog()
    if req.origin not in cat.origins:
        raise StepOutcome(Status.INVALID_REQUEST, f"origin {req.origin} is not in the catalog origin airports ({', '.join(cat.origins)})")
    if req.origin in C.CITIES[req.city]["airports"]:
        raise StepOutcome(Status.INVALID_REQUEST, f"origin {req.origin} is an airport of the destination city")
    return req


def ask_car(req: TripRequest) -> TripRequest:
    """HITL step: wants_car is mandatory in the schema (pre-filled in the eval); the UI asks it explicitly."""
    return req


# ----------------------------------------------------------------- weather
def weather_step(log: ToolLog, req: TripRequest) -> tuple[list[DayCondition], WeatherStatus]:
    try:
        dates = req.all_dates() if req.has_flex else req.days
        out = T.get_forecast(log, req.city, [d.isoformat() for d in dates], req.as_of.isoformat())
        return [DayCondition(**d) for d in out["days"]], WeatherStatus(out["weather_status"])
    except Exception:  # noqa: BLE001
        return [DayCondition(date=d.isoformat(), lead_days=(d - req.as_of).days, flags=["UNAVAILABLE"]) for d in req.days], \
            WeatherStatus.UNAVAILABLE


# ----------------------------------------------------------------- candidates
MAX_PARETO_EXTRA = 5


def _pair_groups(log: ToolLog, req: TripRequest, start: str, end: str, flight_cache: dict) -> tuple[list, list[str]]:
    """Hard-constraint search for one (start, end) pair. Returns ([(outs, backs, car, stays)], reasons)."""
    city, Tn = req.city, req.travelers
    airports = C.CITIES[city]["airports"]
    if ("out", start) not in flight_cache:
        flight_cache[("out", start)] = T.search_flights(log, req.origin, airports, start, Tn, "out")["options"]
    if ("back", end) not in flight_cache:
        flight_cache[("back", end)] = T.search_flights(log, req.origin, airports, end, Tn, "back")["options"]
    outs, backs = flight_cache[("out", start)], flight_cache[("back", end)]
    stays = T.search_hotels(log, city, start, end, Tn, central=req.hotel_preference == "central")["options"]
    reasons = []
    if not outs:
        reasons.append(f"no outbound flight {req.origin}->{'/'.join(airports)} landing on {start} with >= {Tn} seats")
    if not backs:
        reasons.append(f"no return flight {'/'.join(airports)}->{req.origin} on {end} with >= {Tn} seats")
    if not stays:
        reasons.append("no lodging matching capacity / min-nights / availability / distance"
                       + (" within the central radius" if req.hotel_preference == "central" else ""))
    groups: list[tuple[list, list, Optional[dict], list]] = []
    if req.wants_car and not reasons:
        any_car = False
        for a in airports:
            o_a = [o for o in outs if o["destination"] == a]
            b_a = [b for b in backs if b["origin"] == a]
            if not o_a or not b_a:
                continue
            cars = T.search_cars(log, a, start, end, Tn)["options"]
            any_car = any_car or bool(cars)
            for c in cars:
                groups.append((o_a, b_a, c, stays))
        if not any_car:
            reasons.append("no available car at an arrival airport with flights both ways (pick-up and return at the same airport)")
    elif not reasons:
        groups.append((outs, backs, None, stays))
    return ([] if reasons else groups), reasons


def build_candidates(log: ToolLog, req: TripRequest, top_k: int = 5,
                     conditions: Optional[list[DayCondition]] = None) -> list[dict[str, Any]]:
    """Exhaustive search over flights x lodging (x car) filtered by every hard constraint incl. budget, over every
    (start, end) pair allowed by the date flexibility (multi-airport cities search all their airports).
    Returns the top_k cheapest packages (rank_packages order) plus, when the request has soft preferences, the
    cheapest package of every Pareto-optimal preference profile not yet in the list (so a deciding system sees
    the real trade-offs). Raises StepOutcome(NEEDS_DATA / NO_PACKAGE_IN_CATALOG) - decided in code."""
    from . import prefs as P
    Tn = req.travelers
    if req.wants_car and Tn > C.MAX_CAR_TRAVELERS:
        r = T.search_cars(log, C.CITIES[req.city]["airports"][0], req.start_date.isoformat(), req.end_date.isoformat(), Tn)
        raise StepOutcome(Status.NEEDS_DATA, r["reason"])
    flight_cache: dict = {}
    all_groups, first_reasons = [], None
    for s_d, e_d in req.date_pairs():
        g, reasons = _pair_groups(log, req, s_d.isoformat(), e_d.isoformat(), flight_cache)
        if first_reasons is None:
            first_reasons = reasons
        all_groups += [(s_d.isoformat(), e_d.isoformat(), (e_d - s_d).days) + x for x in g]
    if not all_groups:
        raise StepOutcome(Status.NO_PACKAGE_IN_CATALOG, "; ".join(first_reasons or ["no combination"])
                          + (" (also for every date shift within the flexibility)" if req.has_flex else ""))
    rain = P.rain_map(conditions or [])
    combos, cheapest = [], None
    for s_d, e_d, nights, O, B, car, stays in all_groups:
        for o in O:
            for b in B:
                for s in stays:
                    refs = dict(flight_out=o["ref"], flight_back=b["ref"], stay=s["ref"], car=car["ref"] if car else None)
                    p = T.price_lines(refs, Tn, nights)
                    pk = dict(refs=refs, total=p["total"], km_to_center=s["km_to_center"], stops=o["stops"] + b["stops"])
                    if req.has_flex:
                        pk.update(start_date=s_d, end_date=e_d, nights=nights)
                    if cheapest is None or p["total"] < cheapest:
                        cheapest = p["total"]
                    if p["total"] <= req.budget_usd + 1e-9:
                        if req.soft_prefs:
                            vec = P.evaluate(req.soft_prefs, city=req.city, req_start=req.start_date.isoformat(),
                                             req_end=req.end_date.isoformat(), flight_out=o, flight_back=b,
                                             stay_km=s["km_to_center"], total=p["total"], preferred_budget=req.preferred_budget_usd,
                                             rain_by_date=rain)
                            pk["sacrificed"] = list(P.sacrificed(vec))
                        combos.append(pk)
    if not combos:
        raise StepOutcome(Status.NO_PACKAGE_IN_CATALOG,
                          f"budget {req.budget_usd} below the cheapest catalog package {cheapest:.2f}" if cheapest else "no combination")
    ranked = list(T.rank_packages(log, combos, top_k)["ranked"])
    if req.soft_prefs:
        front = P.pareto_front(tuple(c["sacrificed"]) for c in combos)
        have = {tuple(c["sacrificed"]) for c in ranked}
        for v in front[:MAX_PARETO_EXTRA]:
            if v in have:
                continue
            best = min((c for c in combos if tuple(c["sacrificed"]) == v), key=T.rank_key)
            ranked.append(best)
            have.add(v)
    by_ref = {o["ref"]: o for o in flight_cache.get(("out", req.start_date.isoformat()), [])}
    for k, v in flight_cache.items():
        for o in v:
            by_ref.setdefault(o["ref"], o)
    stay_by: dict[str, dict] = {}
    for e in log.by_tool("search_hotels"):
        for s in e["output"].get("options", []):
            stay_by.setdefault((e["args"]["check_in"], e["args"]["check_out"], s["ref"]), s)
    cands = []
    for pk in ranked:
        nights = pk.get("nights", req.nights)
        pr = T.calculate_price(log, pk["refs"], Tn, nights)
        car_opt = None
        if pk["refs"]["car"]:
            for e in log.by_tool("search_cars"):
                car_opt = next((c for c in e["output"]["options"] if c["ref"] == pk["refs"]["car"]), car_opt)
        sd, ed = pk.get("start_date", req.start_date.isoformat()), pk.get("end_date", req.end_date.isoformat())
        c = dict(refs=pk["refs"], total=pr["total"], price_lines=pr["lines"], price_call_id=pr["call_id"],
                 km_to_center=pk["km_to_center"], stops=pk["stops"], flight_out=by_ref[pk["refs"]["flight_out"]],
                 flight_back=by_ref[pk["refs"]["flight_back"]], stay=stay_by[(sd, ed, pk["refs"]["stay"])], car=car_opt,
                 n_within_budget=len(combos))
        if req.has_flex:
            c.update(start_date=sd, end_date=ed, nights=nights)
        if req.soft_prefs:
            c["sacrificed_prefs"] = pk["sacrificed"]
        cands.append(c)
    return cands


# ----------------------------------------------------------------- day windows
def day_windows(req: TripRequest, flight_out: dict[str, Any], flight_back: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Local-time windows: full day 09:30-20:00; arrival day from landing + 90 min; departure day until take-off - 180 min."""
    ds, de = hm_to_min(C.DAY_START), hm_to_min(C.DAY_END)
    out = {}
    for d in req.days:
        a, b = ds, de
        if d == req.start_date:
            a = max(a, hm_to_min(iso_local_hm(flight_out["arr"])) + C.ARRIVAL_BUFFER_MIN)
        if d == req.end_date:
            b = min(b, hm_to_min(iso_local_hm(flight_back["dep"])) - C.DEPARTURE_BUFFER_MIN)
        out[d.isoformat()] = (min_to_hm(a), min_to_hm(max(a, b)))
    return out


def travel_mode(req: TripRequest) -> str:
    return "drive" if req.wants_car else "transit"
