"""Comparison orchestration, process deadlines and evidence-based metrics."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
import uuid

from . import config as C
from . import prefs as P
from .models import CheckReport, CheckResult, Status, TripRequest
from .monitoring import progress, redact

RUNTIME = Path(os.environ.get("TRAVEL_RUNTIME_DIR", C.REPO_ROOT / "runtime"))
SYSTEMS = ("rules", "single", "multi")
ACTIVE_LOCK = threading.Lock()


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def connect():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(RUNTIME / "comparisons.sqlite", timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS comparisons (id TEXT PRIMARY KEY, created_at TEXT, data TEXT)")
    return db


def save(data):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO comparisons VALUES (?, ?, ?)",
                   (data["id"], data["created_at"], json.dumps(data, ensure_ascii=False)))


def get(comparison_id):
    with connect() as db:
        row = db.execute("SELECT data FROM comparisons WHERE id=?", (comparison_id,)).fetchone()
    return json.loads(row[0]) if row else None


def history(limit=20):
    with connect() as db:
        rows = db.execute("SELECT data FROM comparisons ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(id=d["id"], created_at=d["created_at"], title=d["title"], status=d["status"], mode=d["mode"])
            for d in (json.loads(row[0]) for row in rows)]


def metrics(result, pricing):
    """No guessed success percentages. Cost uses actual token counts and supplied unit prices."""
    checks = (result.get("check_report") or {}).get("checks", [])
    req, pkg = result.get("request") or {}, result.get("package")
    vec, soft_score = {}, None
    if pkg and req.get("soft_prefs"):
        vec = P.evaluate(req["soft_prefs"], city=req["city"], req_start=req["start_date"], req_end=req["end_date"],
                         flight_out=pkg["flight_out"], flight_back=pkg["flight_back"], stay_km=pkg["stay"]["km_to_center"],
                         total=pkg["total"], preferred_budget=req.get("preferred_budget_usd"),
                         rain_by_date=P.rain_map(result.get("day_conditions", [])))
        weights = req.get("priority_weights", {})
        scored = [(v, weights.get(k, 1)) for k, v in vec.items() if v is not None]
        denominator = sum(w for _, w in scored)
        soft_score = sum(w for v, w in scored if v) / denominator if denominator else None
    valid = bool(result.get("all_checks_passed") and result.get("status") == "OK_PLAN"
                 and result.get("wall_time_s", 999) <= C.METRIC_TIME_LIMIT_S
                 and result.get("rounds_used", 999) <= C.MAX_ROUNDS)
    calls = result.get("llm_calls", 0)
    prices_known = pricing.get("input_per_million") is not None and pricing.get("output_per_million") is not None
    token_in, token_out = result.get("tokens_in", 0), result.get("tokens_out", 0)
    cost = ((token_in * pricing["input_per_million"] + token_out * pricing["output_per_million"]) / 1e6
            if prices_known else (0 if not calls else None))
    return dict(valid_plan=valid, time_s=result.get("wall_time_s"), rounds=result.get("rounds_used"),
                checks_passed=sum(c["passed"] for c in checks), checks_total=len(checks),
                interests_coverage=(result.get("check_report") or {}).get("coverage"),
                soft_satisfaction=soft_score, soft_preferences=vec,
                package_usd=pkg["total"] if pkg else None, tool_calls=len(result.get("tool_log", [])),
                llm_calls=calls, tokens_in=token_in, tokens_out=token_out,
                estimated_llm_cost_usd=cost, cost_basis="configured_unit_prices" if prices_known else "not_configured",
                notes=["Travel time and visit duration are estimates.",
                       "Package price excludes unrecorded lodging/car fees, meals and attraction tickets."])


def audit_approved_input(result, approved):
    """An agent cannot earn success by parsing away a user's hard constraint."""
    if result.request is None:
        return result
    from .checks import final_checks
    from .pipeline import day_windows
    from .models import effective_request
    from .tool_log import ToolLog
    result.parsed_request = result.request
    fields = ["city", "origin", "start_date", "end_date", "travelers", "budget_usd", "wants_car", "pace",
              "interests", "avoid", "hotel_preference", "depart_flex_days", "return_flex_days", "soft_prefs",
              "preferred_budget_usd", "priority_weights", "daily_blocked_windows", "max_walk_minutes", "day_start",
              "day_end", "accessibility", "no_early_flight_before", "unparsed_requirements"]
    mismatches = [key for key in fields if getattr(result.request, key) != getattr(approved, key)]
    result.request = approved
    report = result.check_report or CheckReport()
    if result.package:
        log = ToolLog(result.run_id)
        log.entries = result.tool_log
        eff = effective_request(approved, result.package)
        windows = day_windows(eff, result.package.flight_out, result.package.flight_back) if result.package.flight_out and result.package.flight_back else None
        report = final_checks(log, approved, result.package, result.days, result.dropped, result.day_conditions, windows)
    report.checks.append(CheckResult(name="approved_input", passed=not mismatches,
                                     details=["Parser changed approved field: " + key for key in mismatches]))
    result.check_report = report
    result.all_checks_passed = bool(result.package and report.all_passed)
    if mismatches and result.status not in (Status.TECHNICAL_ERROR, Status.TIMEOUT):
        result.status = Status.CONFLICT_UNRESOLVED
        result.message = "Parsed request differs from approved input: " + ", ".join(mismatches)
    elif result.status == Status.OK_PLAN and not result.all_checks_passed:
        result.status = Status.CONFLICT_UNRESOLVED
    return result


def _child(system, req, original_text, input_mode, event_queue):
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    from .events import sink
    from .systems import run
    callback = lambda data: event_queue.put(("event", redact(dict(data, ts=data.get("ts") or utc_now()))))
    sink.set(callback)
    flush = lambda: None
    try:
        if system != "rules":
            from .events import emit, install_llm_progress
            emit("stage", stage="initializing_agents")
            flush = install_llm_progress()
        raw = dict(req)
        raw["free_text"] = original_text
        if input_mode == "natural" and system != "rules":
            raw = dict(request_id=req["request_id"], request_text=original_text, as_of=req["as_of"])
        result = run(system, raw)
        if input_mode == "natural" and system != "rules":
            result = audit_approved_input(result, TripRequest.model_validate(req))
        flush()
        event_queue.put(("result", result.model_dump(mode="json")))
    except BaseException as exc:
        flush()
        event_queue.put(("error", redact(f"{type(exc).__name__}: {exc}")))


def _execute(data, system, lock):
    slot = data["runs"][system]
    start = time.monotonic()
    with lock:
        slot.update(state="running", started_at=utc_now())
        save(data)
    context = mp.get_context("spawn")
    events = context.Queue()
    process = context.Process(target=_child, args=(system, data["request"], data["request_text"], data["input_mode"], events))
    process.start()
    result = None
    last_saved = time.monotonic()
    try:
        while time.monotonic() - start < C.DEADLINE_S:
            try:
                kind, item = events.get(timeout=0.25)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            if kind == "result":
                result = item
                break
            if kind == "error":
                slot["error"] = item
                break
            with lock:
                slot["events"].append(item)
                if item["kind"] == "agent":
                    slot["actor"] = item["actor"]
                    slot["stage"] = item.get("stage", slot.get("stage"))
                if item["kind"] == "stage":
                    slot["stage"] = item["stage"]
                now = time.monotonic()
                if now - last_saved >= .2 or item["kind"] in ("agent", "stage", "llm_start", "llm_end", "llm_error", "retry", "checks"):
                    save(data)
                    last_saved = now
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=3)
        if process.is_alive():
            process.kill()
        events.close()
    with lock:
        if result is None:
            timed_out = time.monotonic() - start >= C.DEADLINE_S
            message = f"The system reached its {C.DEADLINE_S}-second execution limit." if timed_out else slot.get("error", "Process ended without a result")
            result = dict(status="TIMEOUT" if timed_out else "TECHNICAL_ERROR", message=message,
                          all_checks_passed=False, wall_time_s=round(time.monotonic() - start, 3), rounds_used=0,
                          llm_calls=0, tokens_in=0, tokens_out=0, tool_log=[], days=[], request=data["request"])
        slot.update(state="complete", finished_at=utc_now(), result=result, metrics=metrics(result, data["pricing"]),
                    process_time_s=round(time.monotonic()-start, 3))
        observed = progress(slot, deadline_s=C.DEADLINE_S)
        slot["monitoring"] = observed
        slot["metrics"].update(llm_calls_attempted=max(observed["llm_started"], result.get("llm_calls", 0)), llm_calls_failed=observed["llm_failed"],
                               llm_calls_unfinished=observed["llm_unfinished"], tool_calls_observed=observed["tools_completed"])
        if observed["llm_started"] and not result.get("llm_calls"):
            slot["metrics"]["estimated_llm_cost_usd"] = None
            slot["metrics"].update(tokens_in=observed["tokens_in_observed"], tokens_out=observed["tokens_out_observed"], usage_partial=True)
            slot["metrics"]["notes"].append("Model calls occurred; complete token usage was not reported before termination.")
        save(data)


def _coordinate(data):
    lock = threading.RLock()
    try:
        if data["mode"] == "benchmark_isolated":
            for system in SYSTEMS:
                _execute(data, system, lock)
        else:
            workers = [threading.Thread(target=_execute, args=(data, system, lock), daemon=True) for system in SYSTEMS]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        with lock:
            data.update(status="complete", finished_at=utc_now())
            save(data)
    finally:
        ACTIVE_LOCK.release()


def start(request, request_text, title, mode="demo_parallel", input_mode="structured", pricing=None):
    if not ACTIVE_LOCK.acquire(blocking=False):
        raise RuntimeError("An active comparison is already running")
    try:
        req = TripRequest.model_validate(request)
        req = req.model_copy(update={"request_id": "UI-" + uuid.uuid4().hex[:8]})
        data = dict(id=str(uuid.uuid4()), title=title, created_at=utc_now(), status="running", mode=mode,
                    input_mode=input_mode, request=req.model_dump(mode="json"), request_text=request_text,
                    snapshot_sha256=hashlib.sha256(C.INVENTORY_PATH.read_bytes()).hexdigest(),
                    pricing=pricing or {},
                    model=os.environ.get("LLM_MODEL", "ollama/qwen2.5:7b-instruct"),
                    runs={s: dict(state="waiting", events=[]) for s in SYSTEMS})
        save(data)
        threading.Thread(target=_coordinate, args=(data,), daemon=True).start()
        return data
    except Exception:
        ACTIVE_LOCK.release()
        raise
