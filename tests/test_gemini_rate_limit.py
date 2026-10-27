"""Quota tests with a simulated clock and SDK responses; no real model calls."""
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("crewai")
pytest.importorskip("google.genai")

from google.genai.errors import ClientError
from crewai.llms.providers.gemini.completion import GeminiCompletion
from travel_agent.events import sink
from travel_agent.systems.gemini import ConfiguredGeminiCompletion
from travel_agent.systems.gemini_rate_limit import RateLimiter, retry_delay
from travel_agent.systems.single_agent import _retryable_provider_error as retry_single
from travel_agent.systems.multi_agent import _retryable_provider_error as retry_multi


@pytest.fixture
def clock(monkeypatch):
    state = {"now": 1000., "sleeps": []}
    monkeypatch.setattr("travel_agent.systems.gemini_rate_limit.time.time", lambda: state["now"])
    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds
    monkeypatch.setattr("travel_agent.systems.gemini_rate_limit.time.sleep", sleep)
    return state


def quota_error(delay="53s", quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier", value="15"):
    return ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded",
        "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
                    {"violations": [{"quotaId": quota_id, "quotaValue": value}]}]}})


def test_two_worker_instances_share_pacing_and_provider_cooldown(tmp_path, clock):
    events = []
    first = RateLimiter(tmp_path / "rate.sqlite", "gemini-test", 12, events.append)
    second = RateLimiter(tmp_path / "rate.sqlite", "gemini-test", 12, events.append)
    first.acquire()
    second.acquire()
    assert clock["now"] == pytest.approx(1005.05)
    first.defer(53)
    second.acquire()
    assert clock["now"] == pytest.approx(1059.05)
    assert all(s <= 10 for s in clock["sleeps"])
    assert any(e["kind"] == "rate_wait" and e["seconds"] >= 53 for e in events)
    assert "api_key" not in json.dumps(events)


@pytest.mark.parametrize("delay,expected", [("53s", 53), ("4.216s", 4.216), ({"seconds": "12", "nanos": 500000000}, 12.5)])
def test_provider_retry_info_is_respected(delay, expected):
    assert retry_delay(quota_error(delay)) == expected


def test_retry_after_header_can_extend_provider_delay():
    error = quota_error("3s")
    error.response = SimpleNamespace(headers={"retry-after": "20"})
    assert retry_delay(error) == 20


@pytest.mark.parametrize("quota_id,value", [("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "15"), ("Minute", "0")])
def test_daily_or_zero_quota_is_not_retried(quota_id, value):
    assert retry_delay(quota_error(quota_id=quota_id, value=value)) is None


def make_model(monkeypatch, tmp_path):
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: object())
    monkeypatch.setenv("TRAVEL_RATE_LIMIT_DB", str(tmp_path / "rate.sqlite"))
    return ConfiguredGeminiCompletion(model="gemini-test", provider="gemini", requests_per_minute=12)


def test_429_retries_the_same_conversation_after_waiting(tmp_path, monkeypatch, clock):
    messages = [{"role": "user", "content": "approved request"}]
    calls, events = [], []
    def sdk_call(self, *args, **kwargs):
        calls.append((args[0], clock["now"]))
        if len(calls) == 1:
            raise quota_error("53s")
        return "actual SDK response placeholder used only in this test"
    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    token = sink.set(events.append)
    try:
        model = make_model(monkeypatch, tmp_path)
        model.call(messages)
    finally:
        sink.reset(token)
    assert len(calls) == 2 and calls[0][0] is messages and calls[1][0] is messages
    assert calls[1][1] - calls[0][1] >= 54
    assert any(e["kind"] == "retry" for e in events)


def test_exhausted_policy_does_not_restart_entire_agent(tmp_path, monkeypatch, clock):
    def sdk_call(self, *args, **kwargs):
        raise quota_error("1s")
    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    model = make_model(monkeypatch, tmp_path)
    with pytest.raises(ClientError) as caught:
        model.call([{"role": "user", "content": "request"}])
    assert not retry_single(caught.value)
    assert not retry_multi(caught.value)


def test_authentication_failure_is_not_retried(tmp_path, monkeypatch, clock):
    calls = []
    def sdk_call(self, *args, **kwargs):
        calls.append(1)
        raise ClientError(403, {"error": {"message": "Permission denied"}})
    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    with pytest.raises(ClientError):
        make_model(monkeypatch, tmp_path).call([])
    assert len(calls) == 1 and not clock["sleeps"]


class TemporaryProviderError(Exception):
    code = 503


def test_503_retries_same_messages_without_restarting_agent(tmp_path, monkeypatch, clock):
    messages = [{"role": "user", "content": "approved trip request"}]
    calls, events = [], []

    def sdk_call(self, *args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise TemporaryProviderError("503 UNAVAILABLE: high demand")
        return "response after transient outage"

    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    token = sink.set(events.append)
    try:
        result = make_model(monkeypatch, tmp_path).call(messages)
    finally:
        sink.reset(token)
    assert result == "response after transient outage"
    assert len(calls) == 2 and all(call is messages for call in calls)
    assert any(e.get("kind") == "retry" and "503" in e.get("error", "") for e in events)
    assert clock["now"] >= 1004.


def test_503_exhaustion_keeps_error_and_suppresses_outer_task_retry(tmp_path, monkeypatch, clock):
    calls = []

    def sdk_call(self, *args, **kwargs):
        calls.append(args[0])
        raise TemporaryProviderError("503 UNAVAILABLE: high demand")

    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    model = make_model(monkeypatch, tmp_path)
    messages = [{"role": "user", "content": "same request"}]
    with pytest.raises(TemporaryProviderError) as error:
        model.call(messages)
    assert len(calls) == 3 and all(call is messages for call in calls)
    assert not retry_single(error.value)
    assert not retry_multi(error.value)


def test_ordinary_400_is_not_retried(tmp_path, monkeypatch, clock):
    calls = []

    class InvalidRequest(Exception):
        code = 400

    def sdk_call(self, *args, **kwargs):
        calls.append(1)
        raise InvalidRequest("400 INVALID_ARGUMENT")

    monkeypatch.setattr(GeminiCompletion, "call", sdk_call)
    with pytest.raises(InvalidRequest):
        make_model(monkeypatch, tmp_path).call([])
    assert len(calls) == 1
