"""System registry: rules (A strong), rules_basic (A basic), single (B), multi (C)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..models import RunResult
from .base import SYSTEM_CODES, run_system


def run(system: str, request: Any, log_dir: Optional[Path] = None) -> RunResult:
    if system == "rules":                       # System A, strong baseline (default, documented)
        from .rules_strong import decide_rules_strong
        return run_system("rules", request, decide_rules_strong, log_dir)
    if system == "rules_basic":                 # System A, basic baseline (cheapest package, proximity-first itinerary)
        from .rules import decide_rules
        return run_system("rules_basic", request, decide_rules, log_dir)
    if system == "single":
        from .single_agent import decide_single
        return run_system("single", request, decide_single, log_dir)
    if system == "multi":
        from .multi_agent import decide_multi
        return run_system("multi", request, decide_multi, log_dir)
    raise ValueError(f"unknown system {system!r}; expected one of {list(SYSTEM_CODES)}")


__all__ = ["run", "SYSTEM_CODES"]
