"""Run task 2 only, with an explicit Gemini configuration and durable JSON evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travel_agent.proof import run_proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evidence/task2") / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    summary = run_proof(args.output, preflight_only=args.preflight_only)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["task2_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
