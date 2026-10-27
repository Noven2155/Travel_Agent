"""Run-local progress hooks. Events describe work that actually happened."""
from contextvars import ContextVar
from typing import Callable

sink: ContextVar[Callable | None] = ContextVar("travel_progress_sink", default=None)


def emit(kind: str, actor: str = "code", **data) -> None:
    callback = sink.get()
    if callback:
        callback(dict(kind=kind, actor=actor, **data))


def public_usage(usage):
    """Normalize provider token-count names without exporting model content."""
    aliases = {"prompt_tokens": ("prompt_tokens", "input_tokens", "prompt_token_count"),
               "completion_tokens": ("completion_tokens", "output_tokens", "candidates_token_count"),
               "total_tokens": ("total_tokens", "total_token_count")}
    return {name: usage[key] for name, keys in aliases.items()
            for key in [next((k for k in keys if usage.get(k) is not None), None)] if key is not None}


def install_llm_progress():
    """Listen to SDK call boundaries, including failures; exclude all model content."""
    callback = sink.get()
    if callback is None:
        return lambda: None
    from crewai.events import crewai_event_bus, LLMCallStartedEvent, LLMCallCompletedEvent, LLMCallFailedEvent

    def register(event_type, kind):
        def handler(source, event):
            usage = getattr(event, "usage", None) or {}
            callback(dict(kind=kind, actor=getattr(event, "agent_role", None) or "model",
                call_id=str(event.call_id), model=getattr(event, "model", None),
                ts=event.timestamp.isoformat(),
                error=str(getattr(event, "error", ""))[:4000],
                usage=public_usage(usage)))
        crewai_event_bus.on(event_type)(handler)
    for event_type, kind in ((LLMCallStartedEvent, "llm_start"), (LLMCallCompletedEvent, "llm_end"), (LLMCallFailedEvent, "llm_error")):
        register(event_type, kind)
    return lambda: crewai_event_bus.flush(timeout=2)
