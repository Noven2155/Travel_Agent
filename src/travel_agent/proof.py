"""Export one real, isolated B/C comparison without feeding saved plans to agents."""
from __future__ import annotations

import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import uuid

from . import config as C
from . import comparison
from .models import RunResult, TripRequest
from .monitoring import redact
from .systems.llm import availability, settings


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def snapshot() -> dict[str, str]:
    paths = [C.INVENTORY_PATH, C.REPO_ROOT / "web/scenarios.json",
             C.REPO_ROOT / "scripts/prove_bc.py", C.REPO_ROOT / "requirements-task2.txt"]
    paths += sorted(C.PLACES_DIR.glob("*.csv"))
    paths += sorted(C.WEATHER_DIR.glob("*.json"))
    paths += sorted((C.REPO_ROOT / "src/travel_agent").rglob("*.py"))
    return {str(p.relative_to(C.REPO_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def source_commit() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.REPO_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def validate_slot(slot: dict, request: dict, system: str = "single") -> dict:
    """Recheck the saved output against the original request and real tool log."""
    result = slot["result"]
    observed = slot.get("monitoring", {})
    checks = None
    error = ""
    same_input = False
    system_matches = result.get("system") == {"single": "B", "multi": "C"}[system]
    try:
        parsed = RunResult.model_validate(result)
        approved = TripRequest.model_validate(request)
        same_input = parsed.request == approved
        audited = comparison.audit_approved_input(parsed, approved)
        checks = audited.check_report.model_dump(mode="json") if audited.check_report else None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    checks_passed = bool(checks and checks["checks"] and all(c["passed"] for c in checks["checks"]))
    real_calls = observed.get("llm_completed", 0) > 0
    within_limits = (slot.get("process_time_s", float("inf")) <= C.DEADLINE_S
                     and 1 <= result.get("rounds_used", 0) <= C.MAX_ROUNDS)
    passed = (result.get("status") == "OK_PLAN" and result.get("all_checks_passed")
              and checks_passed and same_input and system_matches and real_calls and within_limits)
    return dict(passed=bool(passed), checks=checks, same_approved_input=same_input,
                system_matches=system_matches, real_model_calls_observed=real_calls, within_limits=within_limits,
                output_validation_error=error,
                failed_checks=[c["name"] for c in (checks or {}).get("checks", []) if not c["passed"]])


def run_proof(output: Path, *, preflight_only: bool = False) -> dict:
    """No fake LLM or fallback planner is available through this entry point."""
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence directory must be empty; previous attempts must be retained.")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["WEATHER_MODE"] = "fixture"
    os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    scenario = next(s for s in json.loads((C.REPO_ROOT / "web/scenarios.json").read_text(encoding="utf-8")) if s["id"] == "S01")
    request = TripRequest.model_validate(scenario["request"]).model_dump(mode="json")
    model_settings = settings()
    if not model_settings["model"].startswith(("gemini/", "google/")):
        raise ValueError("Task 2 requires an explicit Gemini model: set LLM_MODEL=gemini/<model-name>.")
    # Only approved inputs are passed to the systems; scenario oracle fields are excluded.
    write_json(output / "request.json", dict(request=request, request_text=scenario["request_text"]))
    before = snapshot()
    manifest = dict(created_at=comparison.utc_now(), source_commit=source_commit(), scenario_id="S01",
                    systems=["single", "multi"], mode="benchmark_isolated", input_mode="structured",
                    settings={k: model_settings[k] for k in ("model", "temperature", "max_tokens", "seed", "timeout", "rpm")},
                    limits=dict(max_rounds=C.MAX_ROUNDS, deadline_s=C.DEADLINE_S), weather_mode="fixture",
                    file_sha256=before, python=platform.python_version(),
                    packages={d.metadata["Name"]: d.version for d in distributions() if d.metadata["Name"]},
                    input_sha256=hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    seed_note="The same seed is sent to both systems; deterministic provider output is not guaranteed.",
                    limitations=["Historical catalog; lodging/car availability is synthetic or estimated.",
                                 "One scenario and one attempt per system; no quality ranking is established.",
                                 "Event logs exclude model prompts, private reasoning and credentials."])
    write_json(output / "manifest.json", manifest)
    ready, reason = availability()
    preflight = dict(ready=ready, reason=reason, model_calls_made=False,
                     note="Configuration check only; credentials, quota and model availability are not verified online.")
    write_json(output / "preflight.json", preflight)
    if preflight_only or not ready:
        summary = dict(task2_complete=False, execution="NOT_RUN", model_calls_made=False,
                       reason="Preflight-only inspection requested." if preflight_only else reason)
        write_json(output / "summary.json", summary)
        return summary
    data = dict(id=str(uuid.uuid4()), title="Task 2: Chicago S01 B/C proof", created_at=manifest["created_at"],
                status="running", mode="benchmark_isolated", input_mode="structured", request=request,
                request_text=scenario["request_text"], pricing={}, model=model_settings["model"],
                runs={s: dict(state="waiting", events=[]) for s in ("single", "multi")})
    comparison.RUNTIME = C.REPO_ROOT / "runtime/task2" / data["id"]
    lock = threading.RLock()
    validation = {}
    for system in ("single", "multi"):
        print(f"Starting {system}; deadline={C.DEADLINE_S}s", flush=True)
        comparison._execute(data, system, lock)
        slot = data["runs"][system]
        folder = output / system
        write_json(folder / "result.json", slot["result"])
        write_json(folder / "tool_log.json", slot["result"].get("tool_log", []))
        write_json(folder / "metrics.json", dict(metrics=slot["metrics"], monitoring=slot["monitoring"],
                    process_time_s=slot["process_time_s"], started_at=slot["started_at"], finished_at=slot["finished_at"]))
        write_json(folder / "events.json", slot["events"])
        if slot.get("partial_result"):
            write_json(folder / "last_draft.json", slot["partial_result"])
        validation[system] = validate_slot(slot, request, system)
        write_json(folder / "validation.json", validation[system])
        print(f"Finished {system}: {slot['result']['status']}; proof_passed={validation[system]['passed']}", flush=True)
    unchanged = before == snapshot()
    data.update(status="complete", finished_at=comparison.utc_now())
    write_json(output / "comparison.json", data)
    summary = dict(task2_complete=unchanged and all(v["passed"] for v in validation.values()),
                   execution="REAL_MODEL_ATTEMPT", data_and_code_unchanged=unchanged,
                   finished_at=data["finished_at"],
                   systems={s: dict(status=data["runs"][s]["result"]["status"], **v) for s, v in validation.items()})
    write_json(output / "summary.json", summary)
    return summary
