"""Shared helpers for the LLM systems B and C: prompt context, conversions, guardrails, feedback."""
from __future__ import annotations

import json
from typing import Any, Optional

from .. import config as C
from ..checks import final_checks, place_facts
from ..models import CheckReport, DayPlan, Dropped, ItineraryPlan, Package, PackageDecision, PlaceShortlist, Status, TripPlan
from ..pipeline import day_windows, travel_mode
from .base import Decision, RunContext, run_checks
from .llm import availability, usage_of

PACKAGE_CHECKS = ["budget", "dates", "capacity", "car"]
SCHEDULE_CHECKS = ["day_load", "travel", "weather_rule"]

RULES_TEXT = f"""Hard rules (checked in code after you answer):
- Use ONLY refs, place_ids, prices, minutes and call_ids returned by the tools in this run. Never invent them.
- Package total must equal the output of calculate_price (cite its call_id as price_call_id) and be <= budget.
- Day windows: full day {C.DAY_START}-{C.DAY_END}; arrival day starts at landing+{C.ARRIVAL_BUFFER_MIN} min; departure day ends at take-off-{C.DEPARTURE_BUFFER_MIN} min.
- Pace limits per day (activities excluding meals / hours incl. meals / travel minutes): {json.dumps(C.DAY_LOAD)}; arrival and departure day: at most 1 activity; at most {C.MAX_MEALS_PER_DAY} meals per day (kind='meal', {C.MEAL_MINUTES} min).
- Travel: call get_travel_time once per day with the legs [from_id, to_id] (first leg starts at the lodging ref); copy minutes, mode and call_id into travel_min, mode, travel_call_id. An item starts no earlier than previous end + travel_min.
- Mode: with a car use 'drive', otherwise 'transit' (legs <= 1 km are always 'walk').
- Weather: on a RAIN day only places with indoor == 'true' (unknown counts as outdoor); move outdoor places to a dry day or list them in dropped with reason WEATHER. On a HEAT day outdoor places only end by {C.HEAT_OUTDOOR_BEFORE} or start from {C.HEAT_OUTDOOR_FROM}. WIND is a note only. No weather text on OUT_OF_HORIZON days.
- Coverage: at least {C.COVERAGE_MIN:.0%} of the interests must be covered by scheduled places' tool tags; zero places with an avoided tag.
- Times are HH:MM local city time. Ratings do not exist (synthetic) - never mention them.
- Soft preferences (request.soft_prefs: central, nonstop, exact_dates, dry_days, long_days, under_preferred_budget) may be
  traded off; each candidate lists its sacrificed_prefs. If no candidate satisfies all of them, say so explicitly in
  tradeoffs ("conflict: ..."), name the preference you sacrificed and why (with numbers), and prefer a package that
  sacrifices as little as possible. With depart/return flex the trip dates are the dates of the chosen flights."""


def llm_or_error(ctx: RunContext) -> Optional[Decision]:
    ok, why = availability()
    if not ok:
        return Decision(status=Status.TECHNICAL_ERROR, rounds_used=0, message=why)
    return None


def request_context(ctx: RunContext) -> dict[str, Any]:
    req = ctx.req
    stay_pts = {}
    cands = []
    for i, c in enumerate(ctx.candidates):
        w = day_windows(req.with_dates(c["start_date"], c["end_date"]) if c.get("start_date") else req, c["flight_out"], c["flight_back"])
        extra = {k: c[k] for k in ("start_date", "end_date", "nights", "sacrificed_prefs") if k in c}
        cands.append(dict(rank=i + 1, **extra, refs=c["refs"], total=c["total"], price_lines=c["price_lines"], price_call_id=c["price_call_id"],
                          stay_km_to_center=c["km_to_center"], stay_lat=c["stay"]["lat"], stay_lon=c["stay"]["lon"],
                          stay_price_per_night=c["stay"]["price_per_night"], flight_out_arr=c["flight_out"]["arr"],
                          flight_back_dep=c["flight_back"]["dep"], stops=c["stops"], day_windows=w,
                          car=(c.get("car") or {}).get("vehicle_type")))
        stay_pts[c["refs"]["stay"]] = (c["stay"]["lat"], c["stay"]["lon"])
    return dict(request=json.loads(req.model_dump_json()), nights=req.nights, city_airports=C.CITIES[req.city]["airports"],
                travel_mode=travel_mode(req), top5_candidates=cands,
                weather=[dict(date=c.date, flags=c.flags, precip_mm=c.precip_mm, apparent_max=c.apparent_max,
                              gust_max=c.gust_max, source=c.source) for c in ctx.conditions])


def package_from_decision(ctx: RunContext, d: PackageDecision) -> Package:
    pc = ctx.log.get(d.price_call_id)
    lines = (pc or {}).get("output", {}).get("lines", {}) if pc and pc["tool"] == "calculate_price" else {}
    flights, stays, cars = {}, {}, {}
    for e in ctx.log.entries:
        tgt = {"search_flights": flights, "search_hotels": stays, "search_cars": cars}.get(e["tool"])
        if tgt is not None:
            for o in e["output"].get("options", []):
                tgt.setdefault(o["ref"], o)
    return Package(refs=dict(flight_out=d.flight_out_ref, flight_back=d.flight_back_ref, stay=d.hotel_ref, car=d.car_ref or None),
                   price_lines=lines or {"flights": 0.0, "lodging": 0.0, "car": 0.0}, total=d.total_price,
                   price_call_id=d.price_call_id, flight_out=flights.get(d.flight_out_ref),
                   flight_back=flights.get(d.flight_back_ref), stay=stays.get(d.hotel_ref), car=cars.get(d.car_ref or ""))


def days_from_itinerary(ctx: RunContext, pkg: Package, it: ItineraryPlan) -> list[DayPlan]:
    days = []
    for d in it.days:
        prev = pkg.refs.get("stay") or ""
        items = []
        for x in d.items:
            if not x.from_id:
                x = x.model_copy(update=dict(from_id=prev))
            items.append(x)
            prev = x.place_id
        days.append(DayPlan(date=d.date, items=items, flags=next((c.flags for c in ctx.conditions if c.date == d.date), [])))
    return days


def package_report(ctx: RunContext, pkg: Package) -> CheckReport:
    rep = final_checks(ctx.log, ctx.req, pkg, [], [], ctx.conditions)
    keep = [c for c in rep.checks if c.name in PACKAGE_CHECKS + ["schema"]]
    g = rep.get("grounding")
    if g:
        keep.append(g)
    return CheckReport(checks=keep)


def feedback_text(report: CheckReport, previous: Any) -> str:
    lines = ["The previous plan FAILED these code checks:"]
    for c in report.checks:
        if not c.passed:
            lines.append(f"- {c.name}: " + "; ".join(c.details[:6]))
    lines.append("Previous output (fix only what failed, keep call_ids from the tools):")
    lines.append(json.dumps(previous, default=str)[:6000])
    return "\n".join(lines)


def grounding_guardrail(ctx: RunContext, kind: str):
    """Guardrail (code): every ref / place_id / call_id in the output must exist in this run's tool log.
    Failure triggers one retry of the same agent (guardrail_max_retries=1); not counted as a round."""
    def _guard(output):
        obj = getattr(output, "pydantic", None)
        if obj is None:
            try:
                raw = getattr(output, "raw", "") or ""
                obj = {"package": PackageDecision, "places": PlaceShortlist, "itinerary": ItineraryPlan,
                       "trip": TripPlan}[kind].model_validate_json(raw)
            except Exception as e:  # noqa: BLE001
                return False, f"output is not valid JSON for the schema: {e}"
        def _ok():
            # Task guardrails may return the TaskOutput itself; LiteAgent (Agent.kickoff) expects str or the pydantic object
            if type(output).__name__ == "TaskOutput":
                return True, output
            return True, (obj if obj is not None else getattr(output, "raw", str(output)))
        if obj is None:
            return _ok()
        errs = []
        facts = place_facts(ctx.log)
        logged = {e["call_id"] for e in ctx.log.entries}
        pkg = getattr(obj, "package", obj if isinstance(obj, PackageDecision) else None)
        if isinstance(pkg, PackageDecision) and pkg.price_call_id not in logged:
            errs.append(f"price_call_id {pkg.price_call_id} is not a tool call of this run")
        shortlist = getattr(obj, "places", obj if isinstance(obj, PlaceShortlist) else None)
        if isinstance(shortlist, PlaceShortlist):
            errs += [f"place_id {p.place_id} was not returned by a tool" for p in shortlist.places if p.place_id not in facts]
        itin = getattr(obj, "itinerary", obj if isinstance(obj, ItineraryPlan) else None)
        if isinstance(itin, ItineraryPlan):
            for d in itin.days:
                for x in d.items:
                    if x.place_id not in facts:
                        errs.append(f"{d.date}: place_id {x.place_id} was not returned by a tool")
                    if x.travel_call_id not in logged:
                        errs.append(f"{d.date}: travel_call_id {x.travel_call_id} is not a tool call of this run")
        if errs:
            return False, "Grounding errors - use only values returned by the tools: " + "; ".join(errs[:8])
        return _ok()
    return _guard


def account_usage(ctx: RunContext, llm, before: tuple[int, int, int]) -> None:
    after = usage_of(llm)
    ctx.llm_calls += max(0, after[0] - before[0])
    ctx.tokens_in += max(0, after[1] - before[1])
    ctx.tokens_out += max(0, after[2] - before[2])


def finish(ctx: RunContext, status: Status, pkg: Optional[Package], days: list[DayPlan], dropped: list[Dropped],
           tradeoffs: list[str], report: Optional[CheckReport], rounds: int, message: str = "") -> Decision:
    if pkg is not None and report is None:
        report = run_checks(ctx, pkg, days, dropped)
    return Decision(status=status, package=pkg, days=days, dropped=dropped, tradeoffs=tradeoffs, check_report=report,
                    rounds_used=rounds, message=message)
