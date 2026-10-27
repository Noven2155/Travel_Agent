"""Wiring tests for systems B and C with a scripted fake LLM (no model, no network)."""
import pytest

pytest.importorskip("crewai")

from travel_agent.models import TripRequest  # noqa: E402
from travel_agent.systems import run  # noqa: E402
from travel_agent.systems.llm import set_llm_factory  # noqa: E402


@pytest.fixture
def fake(request):
    from fake_llm import ScriptedLLM
    bad = getattr(request, "param", False)
    set_llm_factory(lambda role: ScriptedLLM(model="fake/scripted", bad_first=bad))
    yield
    set_llm_factory(None)


@pytest.mark.parametrize("system", ["single", "multi"])
def test_flow_happy_path(cases, fake, system):
    r = run(system, TripRequest.from_case(cases["A01"]))
    assert r.status.value == "OK_PLAN", (r.message, r.notes)
    assert r.rounds_used == 1 and r.llm_calls >= 2 and r.tokens_in > 0
    actors = {e["actor"] for e in r.tool_log}
    assert actors - {"code"}, "agent tool calls are logged with the agent name"


@pytest.mark.parametrize("fake", [True], indirect=True)
@pytest.mark.parametrize("system", ["single", "multi"])
def test_router_replans_after_failed_check(cases, fake, system):
    r = run(system, TripRequest.from_case(cases["A01"]))
    assert r.status.value == "OK_PLAN", (r.message, r.notes)
    assert r.rounds_used == 2


def test_multi_agent_least_privilege(cases, fake):
    r = run("multi", TripRequest.from_case(cases["A01"]))
    by_actor = {}
    for e in r.tool_log:
        by_actor.setdefault(e["actor"], set()).add(e["tool"])
    assert by_actor.get("places", set()) <= {"search_places", "get_place_details"}
    assert by_actor.get("itinerary", set()) <= {"get_travel_time", "check_day_load"}


def test_code_decided_statuses_skip_the_agents(cases, fake):
    r = run("multi", TripRequest.from_case(cases["E02"]))
    assert r.status.value == "NO_PACKAGE_IN_CATALOG" and r.llm_calls == 0


@pytest.mark.parametrize("system", ["single", "multi"])
def test_no_llm_gives_technical_error(cases, monkeypatch, system):
    set_llm_factory(None)
    monkeypatch.setenv("LLM_MODEL", "ollama/qwen2.5:7b-instruct")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    r = run(system, TripRequest.from_case(cases["A01"]))
    assert r.status.value == "TECHNICAL_ERROR"
    assert "LLM not available" in r.message


def test_single_uses_next_round_for_grounding_guardrail_failure(cases, fake, monkeypatch):
    from travel_agent.systems import single_agent

    original = single_agent.run_planner_task
    attempts = []

    def fail_once_then_plan(ctx, llm, prompt):
        attempts.append(prompt)
        if len(attempts) == 1:
            raise RuntimeError(
                "Task failed guardrail validation after 1 retries. Last error: "
                "Grounding errors - place_id PL_001 was not returned by a tool; "
                "travel_call_id get_travel_time#002 is not a tool call of this run"
            )
        assert "Valid place IDs returned in this run" in prompt
        assert "Valid get_travel_time calls from this run" in prompt
        return original(ctx, llm, prompt)

    monkeypatch.setattr(single_agent, "run_planner_task", fail_once_then_plan)
    result = run("single", TripRequest.from_case(cases["A01"]))
    assert result.status.value == "OK_PLAN", result.message
    assert result.rounds_used == 2
    assert len(attempts) == 2


def test_single_exhausts_rounds_without_accepting_ungrounded_plan(cases, fake, monkeypatch):
    from travel_agent.systems import single_agent

    attempts = []

    def always_invalid(ctx, llm, prompt):
        attempts.append(prompt)
        raise RuntimeError(
            "Task failed guardrail validation after 1 retries. Last error: "
            "Grounding errors - place_id PL_001 was not returned by a tool"
        )

    monkeypatch.setattr(single_agent, "run_planner_task", always_invalid)
    result = run("single", TripRequest.from_case(cases["A01"]))
    assert result.status.value == "TECHNICAL_ERROR"
    assert result.rounds_used == 3
    assert len(attempts) == 3


def test_single_does_not_use_grounding_repair_for_provider_503(cases, fake, monkeypatch):
    from travel_agent.systems import single_agent

    attempts = []

    def provider_unavailable(ctx, llm, prompt):
        attempts.append(prompt)
        raise RuntimeError("503 UNAVAILABLE: high demand")

    monkeypatch.setattr(single_agent, "run_planner_task", provider_unavailable)
    result = run("single", TripRequest.from_case(cases["A01"]))
    assert result.status.value == "TECHNICAL_ERROR"
    assert result.rounds_used == 1
    assert len(attempts) == 2  # Existing bounded provider retry, not a new planning round.
