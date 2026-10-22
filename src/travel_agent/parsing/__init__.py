"""Free-text request parsers (eval v3). Every parser maps a FreeTextRequest to TripRequest fields.

  keyword  (parse_rules.py)  - System A on free text: regular expressions + keyword lists, no LLM (honest best effort)
  llm      (parse_llm.py)    - one LLM call with the request schema, pydantic-validated (hybrid, B and C)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ParseResult:
    parser: str
    fields: Optional[dict[str, Any]]          # TripRequest fields (None = could not build a request)
    notes: list[str] = field(default_factory=list)   # assumptions / defaults used
    error: str = ""
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
