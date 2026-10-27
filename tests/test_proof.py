"""Evidence acceptance tests; these never count as real Gemini execution."""
import json

import pytest

from travel_agent import comparison
from travel_agent.config import REPO_ROOT
from travel_agent.proof import run_proof, validate_slot
from travel_agent.systems import run


def scenario_request():
    return json.loads((REPO_ROOT / "web/scenarios.json").read_text(encoding="utf-8"))[0]["request"]


def test_proof_blocks_missing_credentials_and_preserves_input(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.1-flash-lite")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("travel_agent.proof.availability", lambda: (False, "GEMINI_API_KEY is not set"))
    summary = run_proof(tmp_path)
    assert summary["execution"] == "NOT_RUN"
    assert not summary["task2_complete"]
    assert json.loads((tmp_path / "request.json").read_text())["request"] == scenario_request()
    assert not (tmp_path / "single").exists()
    with pytest.raises(ValueError, match="must be empty"):
        run_proof(tmp_path)


def test_proof_rejects_non_gemini_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "ollama/example")
    with pytest.raises(ValueError, match="explicit Gemini"):
        run_proof(tmp_path)


def test_valid_plan_without_observed_model_response_is_not_live_proof():
    req = scenario_request()
    result = run("rules", req).model_dump(mode="json")
    slot = dict(result=result, process_time_s=1, monitoring={})
    validation = validate_slot(slot, req)
    assert validation["same_approved_input"]
    assert not validation["real_model_calls_observed"]
    assert not validation["passed"]


def test_proof_rejects_timeout_and_changed_input():
    req = scenario_request()
    result = run("rules", req).model_dump(mode="json")
    result["llm_calls"] = 2
    slot = dict(result=result, process_time_s=271, monitoring={"llm_completed": 2})
    assert not validate_slot(slot, req)["within_limits"]
    slot["process_time_s"] = 1
    result["request"]["budget_usd"] = 9999
    assert not validate_slot(slot, req)["same_approved_input"]


def test_proof_rechecks_grounding_instead_of_trusting_success_flags():
    req = scenario_request()
    result = run("rules", req).model_dump(mode="json")
    result["llm_calls"] = 2
    result["days"][0]["items"][0]["place_id"] = "invented-place"
    slot = dict(result=result, process_time_s=1, monitoring={"llm_completed": 2})
    validation = validate_slot(slot, req)
    assert "grounding" in validation["failed_checks"]
    assert not validation["passed"]


def test_export_preserves_both_failures_without_claiming_live_proof(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.1-flash-lite")
    monkeypatch.setattr("travel_agent.proof.availability", lambda: (True, "offline test configuration"))

    def offline_execute(data, system, lock):
        result = run("rules", data["request"]).model_dump(mode="json")
        data["runs"][system].update(result=result, metrics={}, monitoring={}, process_time_s=1,
                                    started_at="2026-10-27T00:00:00+00:00", finished_at="2026-10-27T00:00:01+00:00")

    monkeypatch.setattr(comparison, "_execute", offline_execute)
    summary = run_proof(tmp_path)
    assert not summary["task2_complete"]
    for system in ("single", "multi"):
        validation = json.loads((tmp_path / system / "validation.json").read_text())
        assert not validation["real_model_calls_observed"]
        assert not validation["system_matches"]
        assert (tmp_path / system / "events.json").is_file()
        assert (tmp_path / system / "tool_log.json").is_file()
