"""python -m travel_agent.cli --case A01 [--system rules|single|multi] [--json]"""
from __future__ import annotations

import argparse
import json

from . import config as C
from .models import TripRequest
from .render import render_markdown
from .systems import run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="eval/dev case id, e.g. A01")
    ap.add_argument("--system", default="rules", choices=["rules", "single", "multi"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    case = next(c for c in json.loads(C.CASES_PATH.read_text())["cases"] if c["id"] == a.case)
    r = run(a.system, TripRequest.from_case(case))
    print(r.model_dump_json(indent=1) if a.json else render_markdown(r))


if __name__ == "__main__":
    main()
