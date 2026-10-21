"""final_checks (spec 1.4 / 6.3): identical code checks for all three systems.

All facts are re-derived from the run's tool log (never from what a model claims): tags/indoor of places,
prices, travel minutes, flight times. Synthetic place fields are never checked nor allowed in the output.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import ValidationError

from . import config as C
from .models import CheckReport, CheckResult, DayCondition, DayPlan, Dropped, Package, TripRequest
from .timeutil import hm_to_min, iso_local_hm
from .tool_log import ToolLog
from .tools import day_load_violations

SYNTHETIC_KEYS = {"rating", "review_count", "price_level"}


def place_facts(log: ToolLog) -> dict[str, dict[str, Any]]:
    """place_id -> PlaceSummary as returned by search_places / get_place_details in this run."""
    facts: dict[str, dict[str, Any]] = {}
    for e in log.entries:
        o = e["output"]
        if e["tool"] == "search_places":
            for p in o.get("places", []):
                facts.setdefault(p["place_id"], dict(p, _call_id=e["call_id"]))
        elif e["tool"] == "get_place_details" and o.get("status") == "OK":
            p = o["place"]
            facts.setdefault(p["place_id"], dict(p, _call_id=e["call_id"]))
            facts[p["place_id"]]["opening_hours"] = o.get("opening_hours")
    return facts


def _options(log: ToolLog, tool: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in log.by_tool(tool):
        for opt in e["output"].get("options", []):
            out.setdefault(opt["ref"], opt)
    return out


def _find_keys(obj: Any, keys: set[str], path: str = "") -> list[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                hits.append(f"{path}.{k}")
            hits += _find_keys(v, keys, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _find_keys(v, keys, f"{path}[{i}]")
    return hits


def final_checks(log: ToolLog, req: TripRequest, package: Optional[Package], days: list[DayPlan],
                 dropped: list[Dropped], conditions: list[DayCondition],
                 windows: Optional[dict[str, tuple[str, str]]] = None) -> CheckReport:
    res: list[CheckResult] = []
    facts = place_facts(log)
    flights = _options(log, "search_flights")
    stays = _options(log, "search_hotels")
    cars = _options(log, "search_cars")
    cond = {c.date: c for c in conditions}
    trip_dates = [d.isoformat() for d in req.days]
    all_items = [(d, it) for d in days for it in d.items]

    # ---- schema
    det = []
    try:
        if package is not None:
            Package.model_validate(package.model_dump())
        for d in days:
            DayPlan.model_validate(d.model_dump())
        for x in dropped:
            Dropped.model_validate(x.model_dump())
        if package is None:
            det.append("no package")
    except ValidationError as e:
        det.append(str(e)[:300])
    res.append(CheckResult(name="schema", passed=not det, details=det))

    # ---- budget
    det = []
    if package is None:
        det.append("no package")
    else:
        pc = log.get(package.price_call_id)
        if not pc or pc["tool"] != "calculate_price":
            det.append(f"price_call_id {package.price_call_id} is not a calculate_price call of this run")
        else:
            if abs(pc["output"].get("total", -1) - package.total) > 0.005:
                det.append(f"total {package.total} != calculate_price {pc['output'].get('total')}")
            if {k: v for k, v in pc["output"].get("refs", {}).items()} != {k: package.refs.get(k) for k in ("flight_out", "flight_back", "stay", "car")}:
                det.append("refs in package differ from the priced refs")
            if pc["output"].get("travelers") != req.travelers or pc["output"].get("nights") != req.nights:
                det.append("price computed for a different party size / nights")
        if package.total > req.budget_usd + 1e-9:
            det.append(f"total {package.total:.2f} > budget {req.budget_usd}")
    res.append(CheckResult(name="budget", passed=not det, details=det))

    # ---- dates (+ item windows)
    det = []
    fo = flights.get(package.refs.get("flight_out")) if package else None
    fb = flights.get(package.refs.get("flight_back")) if package else None
    if package:
        if not fo or not fb:
            det.append("flight refs not found in search_flights outputs")
        else:
            s, e = req.start_date.isoformat(), req.end_date.isoformat()
            if fo["date"] != s or fo["arrival_date"] != s:
                det.append(f"outbound must depart and land on {s} (got {fo['date']} / {fo['arrival_date']})")
            if fb["date"] != e:
                det.append(f"return must depart on {e} (got {fb['date']})")
            if fo["origin"] != req.origin or fb["destination"] != req.origin:
                det.append("flights do not connect the requested origin")
            if fo["destination"] not in C.CITIES[req.city]["airports"] or fb["origin"] not in C.CITIES[req.city]["airports"]:
                det.append("flights do not serve the destination city")
            arr_ok = hm_to_min(iso_local_hm(fo["arr"])) + C.ARRIVAL_BUFFER_MIN
            dep_ok = hm_to_min(iso_local_hm(fb["dep"])) - C.DEPARTURE_BUFFER_MIN
            for d, it in all_items:
                if d.date == s and hm_to_min(it.start) < arr_ok:
                    det.append(f"{d.date} {it.place_id} starts before landing + {C.ARRIVAL_BUFFER_MIN} min")
                if d.date == e and hm_to_min(it.end) > dep_ok:
                    det.append(f"{d.date} {it.place_id} ends after take-off - {C.DEPARTURE_BUFFER_MIN} min")
    for d in days:
        if d.date not in trip_dates:
            det.append(f"day {d.date} outside the trip")
    for d, it in all_items:
        if hm_to_min(it.end) <= hm_to_min(it.start):
            det.append(f"{d.date} {it.place_id} end <= start")
    res.append(CheckResult(name="dates", passed=not det, details=det))

    # ---- capacity
    det = []
    if package:
        for k, f in (("flight_out", fo), ("flight_back", fb)):
            if f and f["seats"] < req.travelers:
                det.append(f"{k} seats {f['seats']} < {req.travelers}")
        st = stays.get(package.refs.get("stay"))
        if not st:
            det.append("stay ref not found in search_hotels outputs")
        else:
            if st["capacity"] < req.travelers:
                det.append(f"stay capacity {st['capacity']} < {req.travelers}")
            if not (st["min_nights"] <= req.nights <= st["max_nights"]):
                det.append(f"nights {req.nights} outside [{st['min_nights']}, {st['max_nights']}]")
            if req.hotel_preference == "central" and st["km_to_center"] > C.CENTRAL_RADIUS_KM[req.city]:
                det.append(f"stay {st['km_to_center']} km from center > central radius {C.CENTRAL_RADIUS_KM[req.city]} km")
    res.append(CheckResult(name="capacity", passed=not det, details=det))

    # ---- car
    det = []
    if package:
        has_car = bool(package.refs.get("car"))
        if req.wants_car:
            if not has_car:
                det.append("wants_car but no car_ref")
            if package.price_lines.get("car", 0) <= 0:
                det.append("wants_car but no car price line")
            if req.travelers > C.MAX_CAR_TRAVELERS:
                det.append(f"travelers {req.travelers} > {C.MAX_CAR_TRAVELERS} with a car")
            if has_car and package.refs["car"] not in cars:
                det.append("car ref not found in search_cars outputs")
            for d, it in all_items:
                if it.mode == "transit":
                    det.append(f"{d.date} {it.place_id}: transit leg although a car is rented (legs > 1 km must be drive)")
        else:
            if has_car or package.price_lines.get("car", 0) > 0:
                det.append("car in package although wants_car=False")
            for d, it in all_items:
                if it.mode == "drive":
                    det.append(f"{d.date} {it.place_id}: drive leg without a car")
    res.append(CheckResult(name="car", passed=not det, details=det))

    # ---- day_load
    det = []
    for d in days:
        edge = d.date in (req.start_date.isoformat(), req.end_date.isoformat())
        v, _ = day_load_violations([it.model_dump() for it in d.items], req.pace, edge)
        det += [f"{d.date}: {x}" for x in v]
    res.append(CheckResult(name="day_load", passed=not det, details=det))

    # ---- travel (values equal the tool output; sequence is feasible)
    det = []
    for d in days:
        prev_end = None
        for it in d.items:
            call = log.get(it.travel_call_id)
            if not call or call["tool"] != "get_travel_time":
                det.append(f"{d.date} {it.place_id}: travel_call_id {it.travel_call_id} missing")
            else:
                leg = next((l for l in call["output"]["legs"] if l.get("from_id") == it.from_id and l.get("to_id") == it.place_id), None)
                if leg is None:
                    det.append(f"{d.date} {it.place_id}: leg {it.from_id}->{it.place_id} not in {it.travel_call_id}")
                else:
                    if leg.get("minutes") != it.travel_min:
                        det.append(f"{d.date} {it.place_id}: travel_min {it.travel_min} != tool {leg.get('minutes')}")
                    if leg.get("mode") != it.mode:
                        det.append(f"{d.date} {it.place_id}: mode {it.mode} != tool {leg.get('mode')}")
            if prev_end is not None and hm_to_min(it.start) < prev_end + it.travel_min:
                det.append(f"{d.date} {it.place_id}: starts before previous item end + travel")
            prev_end = hm_to_min(it.end)
    res.append(CheckResult(name="travel", passed=not det, details=det))

    # ---- weather_rule (rain_handled + heat window + no forecast text out of horizon)
    det, rain_days = [], []
    for d in days:
        c = cond.get(d.date)
        flags = c.flags if c else []
        if "RAIN" in flags:
            rain_days.append(d.date)
        for it in d.items:
            indoor = facts.get(it.place_id, {}).get("indoor", "unknown")
            if "RAIN" in flags and indoor != "true":
                det.append(f"{d.date} RAIN: {it.place_id} indoor={indoor}")
            if "HEAT" in flags and indoor != "true":
                if not (hm_to_min(it.end) <= hm_to_min(C.HEAT_OUTDOOR_BEFORE) or hm_to_min(it.start) >= hm_to_min(C.HEAT_OUTDOOR_FROM)):
                    det.append(f"{d.date} HEAT: outdoor {it.place_id} at {it.start}-{it.end}")
            if "OUT_OF_HORIZON" in flags and it.weather_note:
                det.append(f"{d.date} OUT_OF_HORIZON but weather text present")
    for x in dropped:
        if x.reason == "WEATHER" and not rain_days:
            det.append(f"{x.place_id} dropped for WEATHER without a RAIN day")
    res.append(CheckResult(name="weather_rule", passed=not det, details=det))

    # ---- coverage (tags from the tools, not from the model)
    det = []
    covered = set()
    for _, it in all_items:
        tags = set(facts.get(it.place_id, {}).get("tags", []))
        covered |= tags & set(req.interests)
        bad = tags & set(req.avoid)
        if bad:
            det.append(f"{it.place_id} has avoided tag(s) {sorted(bad)}")
    coverage = len(covered) / len(req.interests) if req.interests else 1.0
    if coverage < C.COVERAGE_MIN:
        det.append(f"coverage {coverage:.2f} < {C.COVERAGE_MIN} (missing {sorted(set(req.interests) - covered)})")
    res.append(CheckResult(name="coverage", passed=not det, details=det))

    # ---- grounding
    det = []
    if package:
        for k in ("flight_out", "flight_back"):
            r = package.refs.get(k)
            if r not in flights:
                det.append(f"{k} {r} not returned by search_flights")
            else:
                given = getattr(package, k) or {}
                for f in ("fare", "dep", "arr", "seats"):
                    if f in given and given[f] != flights[r][f]:
                        det.append(f"{k}.{f} {given[f]} != tool {flights[r][f]}")
        if package.refs.get("stay") not in stays:
            det.append(f"stay {package.refs.get('stay')} not returned by search_hotels")
        elif package.stay and package.stay.get("price_per_night") not in (None, stays[package.refs["stay"]]["price_per_night"]):
            det.append("stay price differs from the tool output")
        if package.refs.get("car") and package.refs["car"] not in cars:
            det.append(f"car {package.refs['car']} not returned by search_cars")
        if not log.get(package.price_call_id):
            det.append("price_call_id not in the tool log")
    for d, it in all_items:
        f = facts.get(it.place_id)
        if f is None:
            det.append(f"{d.date} place {it.place_id} not returned by search_places/get_place_details")
        elif it.name and it.name != f["name"]:
            det.append(f"{d.date} {it.place_id}: name '{it.name}' != tool '{f['name']}'")
        if not log.get(it.travel_call_id):
            det.append(f"{d.date} {it.place_id}: travel_call_id not in the tool log")
    plan_json = json.loads(json.dumps(dict(package=package.model_dump() if package else None,
                                           days=[d.model_dump() for d in days]), default=str))
    hits = _find_keys(plan_json, SYNTHETIC_KEYS)
    if hits:
        det.append(f"synthetic fields present in the plan: {hits[:5]}")
    res.append(CheckResult(name="grounding", passed=not det, details=det))

    return CheckReport(checks=res, coverage=round(coverage, 3), rain_days=rain_days)
