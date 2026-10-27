"""System C - three CrewAI agents (Trip Manager, Places, Itinerary) in a CrewAI Flow (spec section 4).

Flow: build_candidates (code, before the Flow) -> trip_manager -> check_package (code router) -> places ->
itinerary -> final_checks (code router) -> route. The router re-runs only the agent responsible for a failure:
budget/capacity/dates/car -> Trip Manager; day_load/travel/weather_rule -> Itinerary (HOTEL_TOO_FAR -> Trip Manager);
coverage -> Places (at most once); grounding/schema -> guardrail retry of the same agent (not a round).
Limits: max_rounds=3 in total, internal deadline 270 s -> TIMEOUT with the best partial plan.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from pydantic import BaseModel

from .. import config as C
from ..checks import place_facts
from ..models import CheckReport, ItineraryPlan, PackageDecision, PlaceShortlist, Status, effective_request
from ..pipeline import day_windows, travel_mode
from .agent_common import (PACKAGE_CHECKS, RULES_TEXT, SCHEDULE_CHECKS, account_usage, days_from_itinerary,
                           feedback_text, finish, grounding_guardrail, llm_or_error, package_from_decision,
                           package_report, request_context)
from .base import Decision, RunContext, run_checks
from .crew_tools import make_tools
from .llm import make_llm, usage_of
from ..events import emit


def _retryable_provider_error(exc: Exception) -> bool:
    if getattr(exc, "_travel_rate_limit_handled", False):
        return False
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in (408, 429, 500, 502, 503, 504):
        return True
    message = str(exc).lower()
    return any(token in message for token in (
        "503", "429", "500", "502", "504", "unavailable",
        "resource_exhausted", "rate limit", "too many requests",
        "temporarily unavailable", "timed out", "timeout",
        "connection reset", "connection error",
    ))

AGENTS = {
    "trip_manager": dict(
        role="Trip manager who builds the package",
        goal="Choose flights + lodging (+ car) within budget and dates; decide and explain trade-offs",
        backstory="Experienced travel agent who explains every compromise with numbers from the tools and never invents a price",
        tools=["search_flights", "search_hotels", "search_cars", "calculate_price"], max_iter=4, max_exec=60,
        output=PackageDecision),
    "places": dict(
        role="Local guide who matches places to preferences",
        goal="Choose 8-12 places that cover the interests and respect avoid",
        backstory="Local guide who justifies every pick by a specific preference and source",
        tools=["search_places", "get_place_details"], max_iter=4, max_exec=60, output=PlaceShortlist),
    "itinerary": dict(
        role="Scheduler who balances days",
        goal="Schedule the places into days that pass day_load, travel and the weather rule",
        backstory="Planner who prefers a calm day to a packed one",
        tools=["get_travel_time", "check_day_load"], max_iter=5, max_exec=75, output=ItineraryPlan),
}
GUARD_KIND = {"trip_manager": "package", "places": "places", "itinerary": "itinerary"}


class CState(BaseModel):
    rounds: int = 0
    package: Optional[dict[str, Any]] = None
    shortlist: Optional[dict[str, Any]] = None
    itinerary: Optional[dict[str, Any]] = None
    report: Optional[dict[str, Any]] = None
    feedback: dict[str, str] = {}
    places_reruns: int = 0
    need_places: bool = True
    outcome: str = ""
    message: str = ""


def run_agent(ctx: RunContext, llm, name: str, description: str) -> Any:
    """One agent = one Task with output_pydantic + code guardrail (guardrail_max_retries=1), run as a one-task Crew."""
    from crewai import Agent, Crew, Process, Task
    spec = AGENTS[name]
    emit("agent", actor=name, stage=name)
    ctx.log.actor = name
    agent = Agent(role=spec["role"], goal=spec["goal"], backstory=spec["backstory"], tools=make_tools(ctx.log, spec["tools"]),
                  llm=llm, allow_delegation=False, max_iter=spec["max_iter"],
                  max_execution_time=int(max(5, min(spec["max_exec"], ctx.time_left()))), verbose=False)
    task = Task(description=description, expected_output=f"A JSON object matching {spec['output'].__name__}", agent=agent,
                output_pydantic=spec["output"], guardrail=grounding_guardrail(ctx, GUARD_KIND[name]), guardrail_max_retries=1)
    before = usage_of(llm)
    last = None
    try:
        for _attempt in range(2):
            if _attempt:
                if not _retryable_provider_error(last) or ctx.time_left() < 5:
                    break
                delay = min(2.0, max(0.0, ctx.time_left() - 3.0))
                emit("retry", actor=name, attempt=_attempt + 1,
                     error=f"{type(last).__name__}; transient provider error; retrying after {delay:.1f}s")
                time.sleep(delay)
            try:
                out = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False).kickoff()
                obj = out.pydantic if getattr(out, "pydantic", None) is not None else spec["output"].model_validate_json(out.raw)
                return obj
            except Exception as e:  # noqa: BLE001
                last = e
                if _attempt or not _retryable_provider_error(e):
                    break
        raise RuntimeError(f"{name} failed: {type(last).__name__}: {last}")
    finally:
        account_usage(ctx, llm, before)


def make_flow(ctx: RunContext):
    from crewai.flow.flow import Flow, listen, or_, router, start

    llm = make_llm("multi")
    base_ctx = request_context(ctx)

    class MultiAgentFlow(Flow[CState]):
        def _deadline(self) -> bool:
            if ctx.time_left() < 5:
                self.state.outcome, self.state.message = "timeout", "internal deadline reached"
                return True
            return False

        @start()
        def begin(self) -> None:
            self.state.rounds = 1

        @listen(or_(begin, "to_manager"))
        def trip_manager(self) -> None:
            if self.state.outcome or self._deadline():
                return
            req = ctx.req
            desc = ("Choose the package for this trip. Prefer one of the top-5 candidates (each already priced, cite its "
                    "price_call_id); you may search and price another combination if it serves the request better "
                    "(e.g. a central stay). Explain trade-offs with numbers.\n" + RULES_TEXT + "\nCONTEXT:\n" +
                    json.dumps(dict(request=base_ctx["request"], nights=req.nights, top5_candidates=base_ctx["top5_candidates"],
                                    city_airports=base_ctx["city_airports"]), default=str))
            if self.state.feedback.get("trip_manager"):
                desc += "\n\n" + self.state.feedback.pop("trip_manager")
            try:
                self.state.package = run_agent(ctx, llm, "trip_manager", desc).model_dump()
            except Exception as e:  # noqa: BLE001
                self.state.outcome, self.state.message = "error", str(e)

        @router(trip_manager)
        def check_package(self) -> str:
            if self.state.outcome:
                return "stop"
            pkg = package_from_decision(ctx, PackageDecision.model_validate(self.state.package))
            rep = package_report(ctx, pkg)
            if rep.all_passed:
                return "package_ok"
            self.state.report = rep.model_dump()
            if self.state.rounds >= C.MAX_ROUNDS:
                self.state.outcome = "conflict"
                return "stop"
            self.state.rounds += 1
            self.state.feedback["trip_manager"] = feedback_text(rep, self.state.package)
            return "to_manager"

        @listen(or_("package_ok", "to_places"))
        def places(self) -> None:
            if self.state.outcome or self._deadline():
                return
            if self.state.shortlist and not self.state.need_places:
                return                                   # Places runs once; again only on a coverage failure
            req = ctx.req
            pkg = PackageDecision.model_validate(self.state.package)
            stay = next((c["stay"] for c in ctx.candidates if c["refs"]["stay"] == pkg.hotel_ref), None)
            rain = [c.date for c in ctx.conditions if "RAIN" in c.flags]
            desc = ("Pick 8-12 places for this trip that cover the interests (structured tags) and the free text, "
                    "and never include an avoided tag. Use search_places (pass near_lat/near_lon of the lodging) and "
                    "get_place_details. If there are RAIN days include at least one indoor place per rain day. "
                    "Food places become meals.\n" + RULES_TEXT + "\nCONTEXT:\n" +
                    json.dumps(dict(city=req.city, interests=req.interests, avoid=req.avoid, free_text=req.free_text, pace=req.pace,
                                    days=len(req.days), rain_days=rain,
                                    lodging=dict(ref=pkg.hotel_ref, lat=stay and stay["lat"], lon=stay and stay["lon"])), default=str))
            if self.state.feedback.get("places"):
                desc += "\n\n" + self.state.feedback.pop("places")
            try:
                self.state.shortlist = run_agent(ctx, llm, "places", desc).model_dump()
                self.state.need_places = False
            except Exception as e:  # noqa: BLE001
                self.state.outcome, self.state.message = "error", str(e)

        @listen(or_(places, "to_itinerary"))
        def itinerary(self) -> None:
            if self.state.outcome or self._deadline():
                return
            pkg = package_from_decision(ctx, PackageDecision.model_validate(self.state.package))
            req = effective_request(ctx.req, pkg)
            facts = place_facts(ctx.log)
            sl = PlaceShortlist.model_validate(self.state.shortlist)
            places = [dict(place_id=p.place_id, name=facts.get(p.place_id, {}).get("name"), category=facts.get(p.place_id, {}).get("category"),
                           tags=facts.get(p.place_id, {}).get("tags"), indoor=facts.get(p.place_id, {}).get("indoor"),
                           minutes=facts.get(p.place_id, {}).get("typical_visit_minutes"),
                           opening_hours=facts.get(p.place_id, {}).get("opening_hours", "unknown")) for p in sl.places]
            windows = day_windows(req, pkg.flight_out, pkg.flight_back) if pkg.flight_out and pkg.flight_back else {}
            desc = ("Schedule these places into the trip days. Return ItineraryPlan (status OK or CANNOT_SCHEDULE with "
                    "cannot_reason; use HOTEL_TOO_FAR if the lodging makes travel limits impossible).\n" + RULES_TEXT +
                    "\nCONTEXT:\n" + json.dumps(dict(pace=req.pace, travel_mode=travel_mode(req), lodging_ref=pkg.refs.get("stay"),
                                                       day_windows=windows, weather=base_ctx["weather"], places=places,
                                                       interests=req.interests), default=str))
            if self.state.feedback.get("itinerary"):
                desc += "\n\n" + self.state.feedback.pop("itinerary")
            try:
                self.state.itinerary = run_agent(ctx, llm, "itinerary", desc).model_dump()
            except Exception as e:  # noqa: BLE001
                self.state.outcome, self.state.message = "error", str(e)

        @router(itinerary)
        def final_checks_route(self) -> str:
            if self.state.outcome:
                return "stop"
            pkg = package_from_decision(ctx, PackageDecision.model_validate(self.state.package))
            it = ItineraryPlan.model_validate(self.state.itinerary)
            days = days_from_itinerary(ctx, pkg, it)
            rep = run_checks(ctx, pkg, days, it.dropped, rounds_used=self.state.rounds)
            self.state.report = rep.model_dump()
            if rep.all_passed and it.status == "OK":
                self.state.outcome = "ok"
                return "stop"
            if self.state.rounds >= C.MAX_ROUNDS:
                self.state.outcome = "conflict"
                return "stop"
            if ctx.time_left() < 10:
                self.state.outcome = "timeout"
                return "stop"
            self.state.rounds += 1
            failed = set(rep.failures)
            if failed & set(PACKAGE_CHECKS) or it.cannot_reason == "HOTEL_TOO_FAR":
                # A new lodging/date choice invalidates both dependent products.
                self.state.need_places = True
                self.state.shortlist = None
                self.state.itinerary = None
                self.state.feedback["trip_manager"] = feedback_text(rep, self.state.package)
                return "to_manager"
            if "coverage" in failed and self.state.places_reruns < 1:
                self.state.places_reruns += 1
                self.state.need_places = True
                self.state.feedback["places"] = feedback_text(rep, self.state.shortlist)
                return "to_places"
            self.state.feedback["itinerary"] = feedback_text(rep, self.state.itinerary)
            return "to_itinerary"

        @listen("stop")
        def done(self) -> str:
            return self.state.outcome

    return MultiAgentFlow()


def decide_multi(ctx: RunContext) -> Decision:
    err = llm_or_error(ctx)
    if err:
        return err
    flow = make_flow(ctx)
    flow.kickoff()
    st = flow.state
    if not st.package:
        return Decision(status=Status.TIMEOUT if st.outcome == "timeout" else Status.TECHNICAL_ERROR,
                        rounds_used=st.rounds, message=st.message or "no package decision")
    pkg = package_from_decision(ctx, PackageDecision.model_validate(st.package))
    it = ItineraryPlan.model_validate(st.itinerary) if st.itinerary else ItineraryPlan(status="CANNOT_SCHEDULE")
    days = days_from_itinerary(ctx, pkg, it)
    rep = CheckReport.model_validate(st.report) if st.report else None
    if st.outcome == "error":
        status = Status.TECHNICAL_ERROR
    else:
        status = {"ok": Status.OK_PLAN, "conflict": Status.CONFLICT_UNRESOLVED, "timeout": Status.TIMEOUT}.get(st.outcome, Status.TECHNICAL_ERROR)
    tradeoffs = list(PackageDecision.model_validate(st.package).tradeoffs) + ([it.explanation] if it.explanation else [])
    if st.shortlist:
        unc = PlaceShortlist.model_validate(st.shortlist).uncovered_prefs
        if unc:
            tradeoffs.append("uncovered preferences: " + ", ".join(unc))
    rep_full = run_checks(ctx, pkg, days, it.dropped, rounds_used=st.rounds) if status != Status.OK_PLAN or rep is None else rep
    return finish(ctx, status, pkg, days, it.dropped, tradeoffs, rep_full, st.rounds,
                  st.message or ("" if status == Status.OK_PLAN else "failed checks: " + ", ".join(rep_full.failures)))
