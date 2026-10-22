"""System registry: rules (A strong), rules_basic (A basic), hybrid (H = LLM parser + strong rules), single (B), multi (C)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..models import RunResult
from .base import SYSTEM_CODES, run_system


def _keyword_parser(ft):
    from ..parsing.parse_rules import parse
    return parse(ft)


def _llm_parser(ft):
    from ..parsing.parse_llm import parse
    from .llm import availability
    ok, why = availability()
    if not ok:                                    # same behaviour as B/C without an LLM
        from ..models import Status
        from ..pipeline import StepOutcome
        raise StepOutcome(Status.TECHNICAL_ERROR, why)
    return parse(ft)


def run(system: str, request: Any, log_dir: Optional[Path] = None) -> RunResult:
    """Free-text requests (eval v3): rules / rules_basic parse with the keyword parser; hybrid, single and multi
    with one LLM parse call (same LLM as the agents, counted in llm_calls)."""
    if system == "rules":                       # System A, strong baseline (default, documented)
        from .rules_strong import decide_rules_strong
        return run_system("rules", request, decide_rules_strong, log_dir, parser=_keyword_parser)
    if system == "rules_basic":                 # System A, basic baseline (cheapest package, proximity-first itinerary)
        from .rules import decide_rules
        return run_system("rules_basic", request, decide_rules, log_dir, parser=_keyword_parser)
    if system == "hybrid":                      # System H: LLM parser + strong rules (no agent)
        from .rules_strong import decide_rules_strong
        return run_system("hybrid", request, decide_rules_strong, log_dir, parser=_llm_parser)
    if system == "single":
        from .single_agent import decide_single
        return run_system("single", request, decide_single, log_dir, parser=_llm_parser)
    if system == "multi":
        from .multi_agent import decide_multi
        return run_system("multi", request, decide_multi, log_dir, parser=_llm_parser)
    raise ValueError(f"unknown system {system!r}; expected one of {list(SYSTEM_CODES)}")


__all__ = ["run", "SYSTEM_CODES"]
