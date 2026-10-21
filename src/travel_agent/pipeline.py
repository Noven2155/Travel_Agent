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
        out = T.get_forecast(log, req.city, [d.isoformat() for d in req.days], req.as_of.isoformat())
        return [DayCondition(**d) for d in out["days"]], WeatherStatus(out["weather_status"])
    except Exception:  # noqa: BLE001
        return [DayCondition(date=d.isoformat(), lead_days=(d - req.as_of).days, flags=["UNAVAILABLE"]) for d in req.days], \
            WeatherStatus.UNAVAILABLE


# ----------------------------------------------------------------- candidates
def build_candidates(log: ToolLog, req: TripRequest, top_k: int = 5) -> list[dict[str, Any]]:
    """Exhaustive search over flights x lodging (x car) filtered by every hard constraint incl. budget.
    Raises StepOutcome(NEEDS_DATA / NO_PACKAGE_IN_CATALOG) - decided in code, before any system decides."""
    city, Tn, start, end = req.city, req.travelers, req.start_date.isoformat(), req.end_date.isoformat()
    airports = C.CITIES[city]["airports"]
    if req.wants_car and Tn > C.MAX_CAR_TRAVELERS:
        r = T.search_cars(log, airports[0], start, end, Tn)
        raise StepOutcome(Status.NEEDS_DATA, r["reason"])
    outs = T.search_flights(log, req.origin, airports, start, Tn, "out")["options"]
    backs = T.search_flights(log, req.origin, airports, end, Tn, "back")["options"]
    stays = T.search_hotels(log, city, start, end, Tn, central=req.hotel_preference == "central")["options"]
    reasons = []
    if not outs:
        reasons.append(f"no outbound flight {req.origin}->{'/'.join(airports)} landing on {start} with >= {Tn} seats")
    if not backs:
        reasons.append(f"no return flight {'/'.join(airports)}->{req.origin} on {end} with >= {Tn} seats")
    if not stays:
        reasons.append("no lodging matching capacity / min-nights / availability / distance"
                       + (" within the central radius" if req.hotel_preference == "central" else ""))
    groups: list[tuple[list, list, Optional[dict]]] = []
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
                groups.append((o_a, b_a, c))
        if not any_car:
            reasons.append("no available car at an arrival airport with flights both ways (pick-up and return at the same airport)")
    elif not reasons:
        groups.append((outs, backs, None))
    if reasons:
        raise StepOutcome(Status.NO_PACKAGE_IN_CATALOG, "; ".join(reasons))
    nights = req.nights
    combos, cheapest = [], None
    for O, B, car in groups:
        for o in O:
            for b in B:
                for s in stays:
                    refs = dict(flight_out=o["ref"], flight_back=b["ref"], stay=s["ref"], car=car["ref"] if car else None)
                    p = T.price_lines(refs, Tn, nights)
                    pk = dict(refs=refs, total=p["total"], km_to_center=s["km_to_center"], stops=o["stops"] + b["stops"])
                    if cheapest is None or p["total"] < cheapest:
                        cheapest = p["total"]
                    if p["total"] <= req.budget_usd + 1e-9:
                        combos.append(pk)
    if not combos:
        raise StepOutcome(Status.NO_PACKAGE_IN_CATALOG,
                          f"budget {req.budget_usd} below the cheapest catalog package {cheapest:.2f}" if cheapest else "no combination")
    ranked = T.rank_packages(log, combos, top_k)["ranked"]
    by_ref = {o["ref"]: o for o in outs + backs}
    stay_by = {s["ref"]: s for s in stays}
    cands = []
    for pk in ranked:
        pr = T.calculate_price(log, pk["refs"], Tn, nights)
        car_opt = None
        if pk["refs"]["car"]:
            for e in log.by_tool("search_cars"):
                car_opt = next((c for c in e["output"]["options"] if c["ref"] == pk["refs"]["car"]), car_opt)
        cands.append(dict(refs=pk["refs"], total=pr["total"], price_lines=pr["lines"], price_call_id=pr["call_id"],
                          km_to_center=pk["km_to_center"], stops=pk["stops"], flight_out=by_ref[pk["refs"]["flight_out"]],
                          flight_back=by_ref[pk["refs"]["flight_back"]], stay=stay_by[pk["refs"]["stay"]], car=car_opt,
                          n_within_budget=len(combos)))
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
