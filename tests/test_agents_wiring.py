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
