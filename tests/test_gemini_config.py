"""Offline transport checks; no request is sent to Google."""
import pytest

pytest.importorskip("crewai")
pytest.importorskip("google.genai")

from travel_agent.systems.llm import make_llm


@pytest.mark.parametrize("role", ["single", "multi"])
def test_gemini_applies_shared_settings_without_network(monkeypatch, role):
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: object())
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.1-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("LLM_SEED", "42")
    monkeypatch.setenv("LLM_TEMPERATURE", "0")
    monkeypatch.setenv("LLM_TIMEOUT_S", "60")
    llm = make_llm(role)
    config = llm._prepare_generation_config(None, None, None)
    assert llm.model == "gemini-3.1-flash-lite"
    assert config.temperature == 0
    assert config.max_output_tokens == 8192
    assert config.seed == 42
    assert llm.client_params["http_options"]["timeout"] == 60000
    assert not config.thinking_config.include_thoughts
