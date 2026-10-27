"""Interruption and repair regressions; fixtures are local and never call a model."""
import json
import queue
import threading
from types import SimpleNamespace

from travel_agent import comparison
from travel_agent.config import REPO_ROOT
from travel_agent.events import public_usage
from travel_agent.models import CheckReport, CheckResult, RunResult, TripPlan, TripRequest
from travel_agent.monitoring import progress
from travel_agent.proof import validate_slot
from travel_agent.systems import run
from travel_agent.systems.agent_common import feedback_text


def request():
    return json.loads((REPO_ROOT / "web/scenarios.json").read_text(encoding="utf-8"))[0]["request"]


def test_sdk_prompt_token_count_is_retained_and_missing_input_is_unknown():
    assert public_usage({"prompt_token_count": 123, "completion_tokens": 7, "total_tokens": 130,
                         "private_content": "must not be exported"}) == dict(prompt_tokens=123, completion_tokens=7, total_tokens=130)
    slot = dict(state="complete", events=[dict(kind="llm_end", call_id="x", usage={"completion_tokens": 7, "total_tokens": 130})])
    assert progress(slot)["tokens_in_observed"] is None


def test_repair_feedback_retains_the_end_of_a_large_plan():
    report = CheckReport(checks=[CheckResult(name="weather_rule", passed=False, details=["OUT_OF_HORIZON but weather text present"])])
    previous = {"large": "x" * 7000, "last_item": {"weather_note": "must be null"}}
    feedback = feedback_text(report, previous, max_chars=None)
    assert '"last_item"' in feedback and '"weather_note"' in feedback
    assert "OUT_OF_HORIZON" in feedback


def test_supervisor_timeout_retains_draft_tools_rounds_and_observed_calls(monkeypatch):
    req = request()
    draft = run("rules", req).model_dump(mode="json")
    draft.update(system="B", run_id="B-local-test", rounds_used=2)
    observed_tool = dict(call_id="last-call", tool="search_places", actor="TripPlanner", args={}, output={})
    events = [dict(kind="agent", actor="TripPlanner", round=3), dict(kind="llm_start", call_id="one"),
              dict(kind="llm_end", call_id="one", usage={"prompt_tokens": 123, "completion_tokens": 7})]
    class EventQueue(queue.Queue):
        def close(self):
            pass
    stream = EventQueue()
    stream.put(("tool_record", dict(run_id="B-local-test", entry=observed_tool)))
    stream.put(("checkpoint", draft))
    for event in events:
        stream.put(("event", event))
    class Worker:
        stopped = False
        def start(self):
            pass
        def is_alive(self):
            return not self.stopped
        def terminate(self):
            self.stopped = True
        def join(self, timeout=None):
            pass
        def kill(self):
            self.stopped = True
    worker = Worker()
    context = SimpleNamespace(Queue=lambda: stream, Process=lambda **kwargs: worker)
    monkeypatch.setattr(comparison.mp, "get_context", lambda method: context)
    monkeypatch.setattr(comparison, "save", lambda data: None)
    monkeypatch.setattr(comparison.C, "DEADLINE_S", .05)
    data = dict(id="local-test", request=req, request_text=req["free_text"], input_mode="structured", pricing={},
                runs={"single": dict(state="waiting", events=[])})
    comparison._execute(data, "single", threading.RLock())
    slot = data["runs"]["single"]
    saved = RunResult.model_validate(slot["result"])
    assert worker.stopped and saved.status.value == "TIMEOUT"
    assert saved.system == "B" and saved.run_id == "B-local-test"
    assert saved.days and saved.rounds_used == 3 and saved.llm_calls == 1
    assert saved.tool_log == [observed_tool] and saved.usage_partial
    assert not saved.all_checks_passed
    validation = validate_slot(slot, req)
    assert validation["real_model_calls_observed"] and not validation["passed"]


def test_old_timeout_envelope_still_reports_observed_real_responses():
    slot = dict(result={"status": "TIMEOUT", "llm_calls": 0}, process_time_s=270.2,
                monitoring={"llm_completed": 28})
    validation = validate_slot(slot, request())
    assert validation["real_model_calls_observed"]
    assert validation["output_validation_error"] and not validation["passed"]


def test_b_uses_exactly_one_agent_and_one_structured_task(cases, monkeypatch):
    import time
    import crewai
    from fake_llm import ScriptedLLM
    from travel_agent.models import WeatherStatus
    from travel_agent.systems.base import RunContext
    from travel_agent.systems.single_agent import run_planner_task
    from travel_agent.systems.crew_tools import ALL_AGENT_TOOLS
    from travel_agent.tool_log import ToolLog
    captured = {}
    class CaptureCrew:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def kickoff(self):
            return "local-test-result"
    monkeypatch.setattr(crewai, "Crew", CaptureCrew)
    req = TripRequest.from_case(cases["A01"])
    ctx = RunContext(run_id="B-test", req=req, log=ToolLog("B-test"), conditions=[],
                     weather_status=WeatherStatus.OUT_OF_HORIZON, candidates=[], t0=time.monotonic(), system="B")
    assert run_planner_task(ctx, ScriptedLLM(model="fake/test"), "test prompt") == "local-test-result"
    assert len(captured["agents"]) == len(captured["tasks"]) == 1
    agent, task = captured["agents"][0], captured["tasks"][0]
    assert not agent.allow_delegation and task.output_pydantic is TripPlan
    assert {t.name for t in agent.tools} == set(ALL_AGENT_TOOLS)
