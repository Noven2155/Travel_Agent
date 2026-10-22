"""Run-local progress hooks. Events describe work that actually happened."""
from contextvars import ContextVar
from typing import Callable

sink: ContextVar[Callable | None] = ContextVar("travel_progress_sink", default=None)


def emit(kind: str, actor: str = "code", **data) -> None:
    callback = sink.get()
    if callback:
        callback(dict(kind=kind, actor=actor, **data))


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
                usage={k: v for k, v in usage.items() if k in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens", "total_tokens")}))
        crewai_event_bus.on(event_type)(handler)
    for event_type, kind in ((LLMCallStartedEvent, "llm_start"), (LLMCallCompletedEvent, "llm_end"), (LLMCallFailedEvent, "llm_error")):
        register(event_type, kind)
    return lambda: crewai_event_bus.flush(timeout=2)
