"""Common runner: shared Flow steps + system-specific DECIDE + final_checks + RunResult."""
from __future__ import annotations

import datetime as dt
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .. import config as C
from ..checks import final_checks
from ..models import (CheckReport, DayCondition, DayPlan, Dropped, Package, RunResult, Status, TripRequest,
                      WeatherStatus)
from ..pipeline import StepOutcome, build_candidates, day_windows, intake, weather_step
from ..tool_log import ToolLog

SYSTEM_CODES = {"rules": "A", "single": "B", "multi": "C"}


@dataclass
class RunContext:
    run_id: str
    req: TripRequest
    log: ToolLog
    conditions: list[DayCondition]
    weather_status: WeatherStatus
    candidates: list[dict[str, Any]]
    t0: float
    deadline_s: float = C.DEADLINE_S
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    notes: list[str] = field(default_factory=list)

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def time_left(self) -> float:
        return self.deadline_s - self.elapsed()


@dataclass
class Decision:
    """What a DECIDE step returns (after its own internal checks / replan loop)."""
    status: Status
    package: Optional[Package] = None
    days: list[DayPlan] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    check_report: Optional[CheckReport] = None
    rounds_used: int = 1
    message: str = ""


def package_from_candidate(c: dict[str, Any]) -> Package:
    return Package(refs=c["refs"], price_lines=c["price_lines"], total=c["total"], price_call_id=c["price_call_id"],
                   flight_out=c["flight_out"], flight_back=c["flight_back"], stay=c["stay"], car=c.get("car"))


def run_checks(ctx: RunContext, package: Optional[Package], days: list[DayPlan], dropped: list[Dropped]) -> CheckReport:
    windows = day_windows(ctx.req, package.flight_out, package.flight_back) if package and package.flight_out else None
    return final_checks(ctx.log, ctx.req, package, days, dropped, ctx.conditions, windows)


def run_system(system: str, raw_request: Any, decide: Callable[[RunContext], Decision],
               log_dir: Optional[Path] = None, deadline_s: float = C.DEADLINE_S) -> RunResult:
    code = SYSTEM_CODES[system]
    run_id = f"{code}-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    t0 = time.monotonic()
    log = ToolLog(run_id)
    rid = raw_request.request_id if isinstance(raw_request, TripRequest) else (raw_request.get("request_id") or raw_request.get("id") or "ADHOC")
    base = dict(run_id=run_id, system=code, request_id=rid)
    req: Optional[TripRequest] = None
    ctx: Optional[RunContext] = None
    try:
        req = intake(raw_request)
        conditions, wstatus = weather_step(log, req)
        base.update(request=req, day_conditions=conditions, weather_status=wstatus)
        cands = build_candidates(log, req)
        ctx = RunContext(run_id=run_id, req=req, log=log, conditions=conditions, weather_status=wstatus,
                         candidates=cands, t0=t0, deadline_s=deadline_s)
        dec = decide(ctx)
        if dec.check_report is None and dec.package is not None:
            dec.check_report = run_checks(ctx, dec.package, dec.days, dec.dropped)
        status = dec.status
        if status == Status.OK_PLAN and (dec.check_report is None or not dec.check_report.all_passed):
            status = Status.CONFLICT_UNRESOLVED
        result = RunResult(**base, status=status, message=dec.message, package=dec.package, candidates=cands,
                           days=dec.days, dropped=dec.dropped, tradeoffs=dec.tradeoffs, check_report=dec.check_report,
                           all_checks_passed=bool(dec.check_report and dec.check_report.all_passed),
                           rounds_used=dec.rounds_used, notes=ctx.notes)
    except StepOutcome as so:
        result = RunResult(**base, status=so.status, message=so.message, rounds_used=0)
    except Exception as e:  # noqa: BLE001 - the harness must never crash
        result = RunResult(**base, status=Status.TECHNICAL_ERROR, message=f"{type(e).__name__}: {e}",
                           notes=[traceback.format_exc(limit=6)])
    result.wall_time_s = round(time.monotonic() - t0, 3)
    if ctx is not None:
        result.llm_calls, result.tokens_in, result.tokens_out = ctx.llm_calls, ctx.tokens_in, ctx.tokens_out
        if result.wall_time_s > deadline_s and result.status == Status.OK_PLAN:
            result.status = Status.TIMEOUT
    result.tool_log = log.dump()
    if log_dir is not None:
        result.tool_log_path = log.save(Path(log_dir) / f"{rid}.tool_log.json")
    return result
