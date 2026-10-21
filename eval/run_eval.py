"""Run one system over the frozen eval (or dev) cases.

    python -m eval.run_eval --system rules|rules_basic|single|multi --split eval|dev [--cases v2|v1] [--city chicago|nyc] [--ids A01,B02] [--out DIR]

--cases selects the frozen case set (default v2 = eval_cases_v2.json with verified true conflicts; v1 kept for history).

Writes one JSON per case to eval/results/<system>/<timestamp>/<id>.json (RunResult incl. plan, status, tool log,
llm_calls, tokens, wall_time_s, rounds) plus run_meta.json. Never calls an LLM for --system rules.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __name__ as _pkg  # noqa: F401  (adds src/ to sys.path)
from travel_agent import config as C  # noqa: E402
from travel_agent.data_access import get_places  # noqa: E402
from travel_agent.models import TripRequest  # noqa: E402
from travel_agent.systems import run  # noqa: E402

CITY_ALIASES = {"chicago": "Chicago", "nyc": "New York", "new york": "New York", "newyork": "New York"}


def frozen_sha(version: str = "v1") -> tuple[str, str | None]:
    actual = hashlib.sha256(C.CASES_PATHS[version].read_bytes()).hexdigest()
    frozen = None
    fp = C.FROZEN_FILES[version]
    if fp.exists():
        frozen = fp.read_text().split()[0]
    return actual, frozen


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=C.REPO_ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True, choices=["rules", "rules_basic", "single", "multi"])
    ap.add_argument("--split", default="eval", choices=["eval", "dev"])
    ap.add_argument("--cases", default="v2", choices=["v1", "v2"], help="case set version (default v2)")
    ap.add_argument("--city", default=None, help="chicago | nyc (default: both)")
    ap.add_argument("--ids", default=None, help="comma-separated case ids")
    ap.add_argument("--out", default=None, help="output directory (default eval/results/<system>/<timestamp>)")
    a = ap.parse_args(argv)
    if not a.system.startswith("rules"):
        os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    data = json.loads(C.CASES_PATHS[a.cases].read_text())
    cases = [c for c in data["cases"] if c["split"] == a.split]
    if a.city:
        city = CITY_ALIASES.get(a.city.lower())
        if not city:
            ap.error(f"unknown city {a.city}")
        cases = [c for c in cases if c["city"] == city]
    if a.ids:
        ids = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in ids]
    actual, frozen = frozen_sha(a.cases)
    if frozen and actual != frozen:
        print(f"WARNING: {C.CASES_PATHS[a.cases].name} sha256 {actual[:12]} != FROZEN {frozen[:12]} - results are not comparable", file=sys.stderr)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else C.RESULTS_DIR / a.system / ts
    out.mkdir(parents=True, exist_ok=True)
    missing_places = sorted({c["city"] for c in cases if get_places(c["city"]) is None})
    meta = dict(system=a.system, variant={"rules": "strong", "rules_basic": "basic"}.get(a.system), split=a.split, cases_version=a.cases, cases_file=C.CASES_PATHS[a.cases].name, city=a.city or "all", ids=a.ids, started=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                git_commit=git_commit(), cases_sha256=actual, frozen_sha256=frozen, frozen_ok=(frozen == actual) if frozen else None,
                n_cases=len(cases), weather_mode=os.environ.get("WEATHER_MODE", "fixture"),
                places_missing_for=missing_places,
                note=("places data missing for " + ", ".join(missing_places) + " -> those cases end as NEEDS_DATA after the package step")
                if missing_places else "")
    print(f"system={a.system} split={a.split} city={a.city or 'all'} cases={len(cases)} -> {out}")
    if missing_places:
        print("NOTE:", meta["note"])
    for c in cases:
        req = TripRequest.from_case(c)
        res = run(a.system, req)
        res.tool_log_path = str((out / f"{c['id']}.json").relative_to(C.REPO_ROOT)) if out.is_relative_to(C.REPO_ROOT) else str(out / f"{c['id']}.json")
        rec = json.loads(res.model_dump_json())
        rec["case"] = {k: c[k] for k in ("id", "split", "group", "city", "intended_conflict", "conflict_description",
                                          "expected_status", "weather_expected")}
        rec["case"]["oracle_package_status"] = c["oracle_package"]["status"]
        rec["case"]["oracle_cheapest_total"] = c["oracle_package"].get("cheapest_total")
        rec["case"]["oracle_places_status"] = c["oracle_places"]["status"]
        rec["case"]["cases_version"] = a.cases
        for k in ("soft_prefs", "preferred_budget_usd", "depart_flex_days", "return_flex_days", "conflict_type", "competing_prefs",
                  "interests", "pace", "start_date", "end_date"):
            if k in c:
                rec["case"][k] = c[k]
        tc = c.get("true_conflict") or {}
        rec["case"]["true_conflict"] = bool(tc.get("passed"))
        rec["case"]["acceptable_sacrifices"] = tc.get("acceptable_sacrifices", [])
        (out / f"{c['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":"), default=str))
        cr = res.check_report
        print(f"  {c['id']:4s} {c['group']} {c['city'][:7]:7s} expected={c['expected_status']:22s} got={res.status.value:22s} "
              f"checks={'PASS' if res.all_checks_passed else ('-' if cr is None else 'FAIL:' + ','.join(cr.failures))} "
              f"t={res.wall_time_s:.2f}s llm={res.llm_calls} rounds={res.rounds_used}"
              + (f"  [{res.message[:90]}]" if res.message and res.status.value != 'OK_PLAN' else ""))
    meta["finished"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    return out


if __name__ == "__main__":
    main()
