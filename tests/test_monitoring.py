"""Execution metadata and UI integration; synthetic events are used only in tests."""
import datetime as dt
import json

from travel_agent.monitoring import progress
from travel_agent.events import sink
from travel_agent.tool_log import ToolLog

NOW = dt.datetime(2026, 10, 22, 9, 0, 20, tzinfo=dt.timezone.utc)


def event(kind, second, **data):
    return dict(kind=kind, ts=f"2026-10-22T09:00:{second:02}+00:00", **data)


def test_observed_counts_durations_and_partial_usage():
    slot = dict(state="running", started_at="2026-10-22T09:00:00+00:00", events=[
        event("llm_start", 1, call_id="a"),
        event("llm_end", 4, call_id="a", usage={"prompt_tokens": 10, "completion_tokens": 5}),
        event("llm_end", 4, call_id="a", usage={"prompt_tokens": 10, "completion_tokens": 5}),
        event("tool_start", 5, call_id="tool", tool="search_places"),
        event("tool", 6, call_id="tool", tool="search_places", duration_s=1.),
        event("llm_start", 7, call_id="b"), event("llm_error", 8, call_id="b", error="test quota failure"),
        event("retry", 9), event("llm_start", 10, call_id="c")])
    view = progress(slot, now=NOW)
    assert (view["llm_started"], view["llm_completed"], view["llm_failed"], view["llm_in_flight"]) == (3, 1, 1, 1)
    assert view["elapsed_s"] == 20 and view["remaining_s"] == 250
    assert view["idle_s"] == 10 and view["action_elapsed_s"] == 10
    assert view["calls"][0]["duration_s"] == 3
    assert view["tokens_in_observed"] == 10 and view["tokens_out_observed"] == 5
    assert view["tools_completed"] == 1 and view["tools_started"] == 1
    assert view["retries"] == 1


def test_timeout_preserves_unfinished_calls_and_redacts_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-secret-only-in-test")
    view = progress(dict(state="complete", started_at="2026-10-22T09:00:00+00:00",
        finished_at="2026-10-22T09:00:15+00:00", result=dict(status="TIMEOUT", message="synthetic-secret-only-in-test"),
        events=[event("llm_start", 10, call_id="pending")]), now=NOW)
    assert view["elapsed_s"] == 15 and view["llm_unfinished"] == 1 and view["llm_in_flight"] == 0
    assert "synthetic-secret" not in json.dumps(view)
    assert view["tokens_in_observed"] is None


def test_tool_boundaries_are_measured():
    items=[]
    token=sink.set(items.append)
    try:
        log=ToolLog("test")
        cid=log.new_call_id("search_places")
        log.record(cid,"search_places",{},dict(status="OK"))
    finally:
        sink.reset(token)
    assert [e["kind"] for e in items] == ["tool_start", "tool_record", "tool"]
    assert items[1]["entry"]["output"] == {"status": "OK"}
    assert items[2]["duration_s"] >= 0


def test_streamlit_shows_partial_result_while_other_system_is_running():
    from streamlit.testing.v1 import AppTest
    observed=progress(dict(state="running", started_at="2026-10-22T09:00:00+00:00",
        events=[event("llm_start",10,call_id="pending")]), now=NOW)
    completed=dict(state="complete", events=[], result=dict(status="OK_PLAN",days=[]),
        metrics=dict(valid_plan=True,package_usd=123.,llm_calls=0,time_s=1.,checks_passed=1,checks_total=1))
    partial=dict(id="test-only",title="Synthetic UI test",mode="demo_parallel",runs={"rules":completed})
    snapshot=dict(state="running", progress={"single":observed}, partial=partial, result=None, error=None)
    source="""import streamlit as st
from travel_agent.streamlit_view import job_panel
class TestJob:
    results=[]
    def snapshot(self):return SNAPSHOT
    def cancel(self):pass
st.session_state.job=TestJob()
job_panel()
""".replace("SNAPSHOT",repr(snapshot))
    app=AppTest.from_string(source,default_timeout=15).run()
    assert not app.exception
    assert any(m.value == "$123.00" for m in app.metric)
    assert any("תוצאות שכבר התקבלו" in h.value for h in app.subheader)
    assert any("ממתינה לתשובת המודל" in m.value for m in app.markdown)
