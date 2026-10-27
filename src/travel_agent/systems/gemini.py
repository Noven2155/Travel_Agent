"""Apply shared comparison settings and quota handling to native Gemini calls."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from crewai.llms.providers.gemini.completion import GeminiCompletion
from pydantic import PrivateAttr, model_validator

from .. import config as C
from ..events import sink
from .gemini_rate_limit import RateLimiter, retry_delay


class ConfiguredGeminiCompletion(GeminiCompletion):
    """Keep pacing, request retries and generation settings identical for B and C."""

    requests_per_minute: float = 12
    _progress_callback: object = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _capture_progress(self):
        self._progress_callback = sink.get()
        return self

    def _prepare_generation_config(self, *args, **kwargs):
        config = super()._prepare_generation_config(*args, **kwargs)
        config.seed = self.seed
        return config

    def call(self, *args, **kwargs):
        path = Path(os.environ.get("TRAVEL_RATE_LIMIT_DB", C.REPO_ROOT / "runtime/gemini_rate.sqlite"))
        limiter = RateLimiter(path, self.model, self.requests_per_minute, self._progress_callback)
        for attempt in range(3):
            limiter.acquire()
            try:
                return super().call(*args, **kwargs)
            except Exception as exc:
                if getattr(exc, "code", None) != 429:
                    raise
                # Prevent the outer agent wrapper from restarting an entire task after this retry policy.
                exc._travel_rate_limit_handled = True
                delay = retry_delay(exc)
                if delay is None:
                    raise
                pause = max(delay, 2 ** attempt)
                limiter.defer(pause)
                if attempt == 2:
                    raise
                if self._progress_callback:
                    self._progress_callback(dict(kind="retry", actor="model", model=self.model,
                        attempt=attempt + 2, seconds=pause + 1, error="Gemini 429; waiting before retrying the same request."))

    async def acall(self, *args, **kwargs):
        return await asyncio.to_thread(self.call, *args, **kwargs)
