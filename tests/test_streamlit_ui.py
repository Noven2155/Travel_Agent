"""Exercise real Streamlit controls and the existing engines without a model key."""
import datetime as dt
import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest
from travel_agent.streamlit_service import ComparisonJob, locate_data, metric_rows
from travel_agent.streamlit_view import approved_request

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "web/scenarios.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_baseline_is_actual_engine(case):
    job = ComparisonJob(ROOT, ROOT / "data")
    job.start(request=case["request"], request_text=case["request_text"], title=case["title"], only_rules=True)
    state = job.wait(45)
    assert state["state"] == "complete", state
    result = state["result"]
    assert result["runs"]["rules"]["result"]["status"] == case["verification"]["baseline_status"]
    price = result["runs"]["rules"]["metrics"]["package_usd"]
    assert price == case["verification"]["baseline_price"]
    assert metric_rows(result)[1]["status"] == "NOT_RUN"


def test_ui_runs_and_updates_request():
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
    assert not app.exception
    app.number_input(key="field_budget_usd").set_value(3100).run()
    assert "3,100" in app.text_area(key="request_text").value
    app.button(key="run_comparison").click().run()
    state = app.session_state.job.wait(45)
    assert state["state"] == "complete", state
    app.run()
    assert not app.exception
    assert any(m.value == "$1,386.80" for m in app.metric)
    assert state["result"]["request"]["budget_usd"] == 3100
    assert "3,100" in state["result"]["request_text"]
    assert state["result"]["runs"]["rules"]["result"]["status"] == "OK_PLAN"


def test_data_navigation_and_invalid_request():
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
    app.radio[0].set_value("הנתונים").run()
    assert not app.exception
    assert any("15,254" in c.value for c in app.caption)
    app.radio[0].set_value("השוואת מערכות").run()
    app.date_input(key="field_end").set_value(dt.date(2022, 8, 19)).run()
    app.button(key="run_comparison").click().run()
    assert app.error
    assert app.session_state.job.snapshot()["state"] == "idle"


def test_sessions_and_drive_layout_are_independent(tmp_path, monkeypatch):
    a = ComparisonJob(ROOT, ROOT / "data")
    b = ComparisonJob(ROOT, ROOT / "data")
    assert a.workspace != b.workspace
    a.results.append({"id": "only-a"})
    assert b.results == []
    (tmp_path / "data").mkdir()
    (tmp_path / "data/inventory.json").write_text("{}")
    monkeypatch.delenv("TRAVEL_DATA_DIR", raising=False)
    assert locate_data(tmp_path / "project") == tmp_path / "data"


def test_unconfigured_agents_are_reported_not_faked():
    case = CASES[0]
    job = ComparisonJob(ROOT, ROOT / "data")
    job.start(request=case["request"], request_text=case["request_text"], title=case["title"], only_rules=False)
    state = job.wait(60)
    assert state["state"] == "complete", state
    runs = state["result"]["runs"]
    assert runs["rules"]["result"]["status"] == "OK_PLAN"
    for key in ("single", "multi"):
        assert runs[key]["result"]["status"] == "TECHNICAL_ERROR"
        assert runs[key]["metrics"]["llm_calls"] == 0
