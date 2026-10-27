"""Apply shared comparison settings to CrewAI's native Gemini transport."""
from __future__ import annotations

from crewai.llms.providers.gemini.completion import GeminiCompletion


class ConfiguredGeminiCompletion(GeminiCompletion):
    """CrewAI 1.15 does not forward its base seed field to Gemini generation."""

    def _prepare_generation_config(self, *args, **kwargs):
        config = super()._prepare_generation_config(*args, **kwargs)
        config.seed = self.seed
        return config
