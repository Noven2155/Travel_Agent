"""System B - one CrewAI agent (TripPlanner) with all 8 tools, inside a CrewAI Flow with a replan router
(spec section 3). Same shared steps, top-5 candidates, final_checks, round limit (3) and deadline (270 s)."""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from pydantic import BaseModel

from .. import config as C
from ..models import CheckReport, Status, TripPlan
from .agent_common import (RULES_TEXT, account_usage, days_from_itinerary, feedback_text, finish, grounding_guardrail,
                           llm_or_error, package_from_decision, request_context)
from .base import Decision, RunContext, run_checks
from .crew_tools import ALL_AGENT_TOOLS, make_tools
from .llm import make_llm, usage_of
from ..events import emit


def _retryable_provider_error(exc: Exception) -> bool:
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

ROLE = "Trip planner for one traveler or a small party in Chicago or New York"
GOAL = ("Return one plan, package and daily schedule, that passes every code check: within budget, the requested pace, "
        "the weather rule and preference coverage, using only facts returned by the tools")
BACKSTORY = ("An experienced travel agent who never invents a price, a place or a time. When a constraint cannot be met, "
             "the agent names the trade-off in numbers")
MAX_ITER = 12
MAX_EXEC_S = 150


class BState(BaseModel):
    round: int = 0
    feedback: str = ""
    plan: Optional[dict[str, Any]] = None
    report: Optional[dict[str, Any]] = None
    outcome: str = ""
    message: str = ""


def build_agent(ctx: RunContext, llm, time_left: float):
    from crewai import Agent
    return Agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, tools=make_tools(ctx.log, ALL_AGENT_TOOLS), llm=llm,
                 allow_delegation=False, max_iter=MAX_ITER, max_execution_time=int(max(5, min(MAX_EXEC_S, time_left))),
                 guardrail=grounding_guardrail(ctx, "trip"), guardrail_max_retries=1, verbose=False)


def make_flow(ctx: RunContext):
    from crewai.flow.flow import Flow, listen, or_, router, start

    llm = make_llm("single")

    class SingleAgentFlow(Flow[BState]):
        def _plan(self) -> None:
            if ctx.time_left() < 5:
                self.state.outcome, self.state.message = "timeout", "deadline reached before the agent call"
                return
            self.state.round += 1
            emit("agent", actor="TripPlanner", round=self.state.round, stage="planning")
            ctx.log.actor = "TripPlanner"
            prompt = ("Plan this trip. Choose one of the top-5 candidate packages (or search for another and price it), "
                      "pick places with search_places / get_place_details, and schedule them with get_travel_time and "
                      "check_day_load. Return the TripPlan JSON.\n\n" + RULES_TEXT + "\n\nCONTEXT:\n" +
                      json.dumps(request_context(ctx), default=str))
            if self.state.feedback:
                prompt += "\n\n" + self.state.feedback
            before = usage_of(llm)
            last_err = None
            for _attempt in range(2):
                if _attempt:
                    if not _retryable_provider_error(last_err) or ctx.time_left() < 5:
                        break
                    delay = min(2.0, max(0.0, ctx.time_left() - 3.0))
                    emit("retry", actor="TripPlanner", attempt=_attempt + 1,
                         error=f"{type(last_err).__name__}; transient provider error; retrying after {delay:.1f}s")
                    time.sleep(delay)
                try:
                    out = build_agent(ctx, llm, ctx.time_left()).kickoff(prompt, response_format=TripPlan)
                    plan = out.pydantic if getattr(out, "pydantic", None) is not None else TripPlan.model_validate_json(out.raw)
                    self.state.plan = plan.model_dump()
                    last_err = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if _attempt or not _retryable_provider_error(e):
                        break
            account_usage(ctx, llm, before)
            if last_err is not None:
                self.state.outcome, self.state.message = "error", f"agent failed: {type(last_err).__name__}: {last_err}"

        @start()
        def plan_round(self) -> None:
            self._plan()

        @listen("replan")
        def replan_round(self) -> None:
            self._plan()

        @router(or_(plan_round, replan_round))
        def check_and_route(self) -> str:
            if self.state.outcome:
                return "stop"
            plan = TripPlan.model_validate(self.state.plan)
            pkg = package_from_decision(ctx, plan.package)
            days = days_from_itinerary(ctx, pkg, plan.itinerary)
            rep = run_checks(ctx, pkg, days, plan.itinerary.dropped)
            self.state.report = rep.model_dump()
            if rep.all_passed:
                self.state.outcome = "ok"
                return "stop"
            if self.state.round >= C.MAX_ROUNDS:
                self.state.outcome = "conflict"
                return "stop"
            if ctx.time_left() < 10:
                self.state.outcome = "timeout"
                return "stop"
            self.state.feedback = feedback_text(rep, self.state.plan)
            return "replan"

        @listen("stop")
        def done(self) -> str:
            return self.state.outcome

    return SingleAgentFlow()


def decide_single(ctx: RunContext) -> Decision:
    err = llm_or_error(ctx)
    if err:
        return err
    flow = make_flow(ctx)
    flow.kickoff()
    st = flow.state
    if st.outcome == "error" and not st.plan:
        return Decision(status=Status.TECHNICAL_ERROR, rounds_used=st.round, message=st.message)
    if not st.plan:
        return Decision(status=Status.TIMEOUT if st.outcome == "timeout" else Status.TECHNICAL_ERROR,
                        rounds_used=st.round, message=st.message or "no plan")
    plan = TripPlan.model_validate(st.plan)
    pkg = package_from_decision(ctx, plan.package)
    days = days_from_itinerary(ctx, pkg, plan.itinerary)
    rep = CheckReport.model_validate(st.report) if st.report else None
    status = {"ok": Status.OK_PLAN, "conflict": Status.CONFLICT_UNRESOLVED, "timeout": Status.TIMEOUT}.get(st.outcome, Status.TECHNICAL_ERROR)
    tradeoffs = list(plan.package.tradeoffs) + ([plan.itinerary.explanation] if plan.itinerary.explanation else [])
    return finish(ctx, status, pkg, days, plan.itinerary.dropped, tradeoffs, rep, st.round,
                  st.message or ("" if status == Status.OK_PLAN else "failed checks: " + ", ".join(rep.failures if rep else [])))
