"""Score eval v3 (free-text segment) runs.

    python -m eval.score_v3 <results dir> [<results dir> ...] [--dev] [--out DIR]

Per system (one row per results dir):
  valid_plan_rate (gold)  OK_PLAN and every final_check passes against the HIDDEN gold request (rec.gold_check_report),
                          time <= 300 s, rounds <= 3 - with Wilson 95% CI
  key requirements        met / flagged-not-handled / silently ignored (eval/keyreq.py), overall and by phrasing_type
  key_requirement_score   mean over cases of met / n
  parse accuracy          diagnostic: share of core fields (city, origin, dates, travelers, budget, car) equal to gold
Writes comparison_v3.md, comparison_v3.csv, per_case_v3.csv, per_requirement_v3.csv.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import __name__ as _pkg  # noqa: F401
from travel_agent import config as C  # noqa: E402

from .keyreq import evaluate  # noqa: E402
from .score import fmt_rate, wilson  # noqa: E402

CORE = ["city", "origin", "start_date", "end_date", "travelers", "budget_usd", "wants_car"]
LABEL = {("A", "strong"): "A - rules (keyword parser + strong rules)", ("A", "basic"): "A0 - rules basic (keyword parser)",
         ("H", None): "H - hybrid (LLM parser + strong rules)", ("B", None): "B - single agent", ("C", None): "C - multi-agent"}


def load(d: Path):
    meta = json.loads((d / "run_meta.json").read_text()) if (d / "run_meta.json").exists() else {}
    recs = [json.loads(p.read_text()) for p in sorted(d.glob("*.json")) if p.name != "run_meta.json"]
    return meta, recs


def is_valid(r) -> bool:
    g = r.get("gold_check_report")
    return r["status"] == "OK_PLAN" and bool(g and g["all_passed"]) and r["wall_time_s"] <= C.METRIC_TIME_LIMIT_S and r.get("rounds_used", 0) <= C.MAX_ROUNDS


def parse_acc(r, case) -> float:
    req, g = r.get("request") or {}, case["gold"]["request"]
    return sum(str(req.get(k)) == str(g.get(k)) for k in CORE) / len(CORE)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    cases = {c["id"]: c for c in json.loads(C.CASES_PATH_V3.read_text())["cases"]}
    split = "dev" if a.dev else "eval"
    rows, per_case, per_req = [], [], []
    for d in a.dirs:
        meta, recs = load(Path(d))
        recs = [r for r in recs if r["case"]["id"] in cases and cases[r["case"]["id"]]["split"] == split]
        if not recs:
            continue
        label = LABEL.get((recs[0]["system"], recs[0].get("variant")), recs[0]["system"])
        ev = {r["case"]["id"]: evaluate(r, cases[r["case"]["id"]]) for r in recs}
        by = defaultdict(Counter)
        scores = defaultdict(list)
        for r in recs:
            c = cases[r["case"]["id"]]
            e = ev[c["id"]]
            for o in e["requirements"]:
                for k in ("all", c["phrasing_type"]):
                    by[k][o["outcome"]] += 1
                per_req.append(dict(system=label, case=c["id"], city=c["city"], phrasing_type=c["phrasing_type"], requirement=o["id"],
                                    checker=o["checker"], outcome=o["outcome"], detail=o["detail"]))
            for k in ("all", c["phrasing_type"]):
                scores[k].append(e["score"])
            per_case.append(dict(system=label, id=c["id"], city=c["city"], phrasing_type=c["phrasing_type"], status=r["status"],
                                 valid_plan_gold=is_valid(r), own_checks_passed=r.get("all_checks_passed"),
                                 gold_failures=";".join((r.get("gold_check_report") or {}).get("failures") or []),
                                 key_score=e["score"], met=e["met"], flagged=e["flagged"], ignored=e["ignored"],
                                 parse_accuracy=round(parse_acc(r, c), 3), parse_notes="; ".join(r.get("parse_notes") or []),
                                 llm_calls=r.get("llm_calls", 0), tokens=r.get("tokens_in", 0) + r.get("tokens_out", 0),
                                 wall_time_s=r["wall_time_s"], message=(r.get("message") or "")[:120]))
        vk = sum(map(is_valid, recs))
        row = dict(label=label, dir=d, n=len(recs), valid=vk, valid_fmt=fmt_rate(vk, len(recs)))
        for k in ("all", "direct", "indirect"):
            c_ = by[k]
            n = sum(c_.values())
            row[k] = dict(n=n, met=c_["met"], flagged=c_["flagged"], ignored=c_["ignored"],
                          score=statistics.mean(scores[k]) if scores[k] else float("nan"))
        for ph in ("direct", "indirect"):
            sub = [r for r in recs if cases[r["case"]["id"]]["phrasing_type"] == ph]
            row["valid_" + ph] = fmt_rate(sum(map(is_valid, sub)), len(sub))
        row["parse_acc"] = statistics.mean(parse_acc(r, cases[r["case"]["id"]]) for r in recs)
        row["llm"] = statistics.mean(r.get("llm_calls", 0) for r in recs)
        row["tokens"] = statistics.mean(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in recs)
        row["time"] = statistics.mean(r["wall_time_s"] for r in recs)
        row["statuses"] = dict(Counter(r["status"] for r in recs))
        row["by_checker"] = {}
        for x in per_req:
            if x["system"] == label:
                row["by_checker"].setdefault(x["checker"], Counter())[x["outcome"]] += 1
        rows.append(row)
    md = f"# Eval v3 - free-text segment ({split}, {dt.datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n"
    md += ("valid_plan (gold) = OK_PLAN and all final_checks pass against the hidden gold request. Key requirements: "
           "met / flagged (not met, but named as not handled) / ignored (not met, not mentioned).\n\n")
    md += "| system | cases | valid_plan_rate (gold) [Wilson 95%] | direct | indirect | key req met / flagged / ignored (all) | direct | indirect | key_requirement_score all / direct / indirect | parse accuracy (core fields) | LLM calls / tokens per case |\n"
    md += "|---|---|---|---|---|---|---|---|---|---|---|\n"
    for r in rows:
        f = lambda k: f"{r[k]['met']} / {r[k]['flagged']} / {r[k]['ignored']} (of {r[k]['n']})"   # noqa: E731
        md += (f"| {r['label']} | {r['n']} | {r['valid_fmt']} | {r['valid_direct']} | {r['valid_indirect']} | {f('all')} | {f('direct')} | {f('indirect')} | "
               f"{r['all']['score']:.2f} / {r['direct']['score']:.2f} / {r['indirect']['score']:.2f} | {r['parse_acc']:.2f} | {r['llm']:.1f} / {r['tokens']:.0f} |\n")
    md += "\nBy checker (met / flagged / ignored):\n\n"
    for r in rows:
        md += f"- {r['label']}: " + "; ".join(f"{k} {v['met']}/{v['flagged']}/{v['ignored']}" for k, v in sorted(r["by_checker"].items())) + \
              f"; statuses {r['statuses']}\n"
    out = Path(a.out) if a.out else C.EVAL_DIR / "reports" / ("v3-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison_v3.md").write_text(md)
    with open(out / "comparison_v3.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["system", "n", "valid_plan_gold", "valid_direct", "valid_indirect", "met", "flagged", "ignored", "score_all", "score_direct",
                    "score_indirect", "parse_accuracy", "llm_calls_mean", "tokens_mean", "time_mean_s"])
        for r in rows:
            w.writerow([r["label"], r["n"], r["valid_fmt"], r["valid_direct"], r["valid_indirect"], r["all"]["met"], r["all"]["flagged"], r["all"]["ignored"],
                        round(r["all"]["score"], 4), round(r["direct"]["score"], 4), round(r["indirect"]["score"], 4), round(r["parse_acc"], 4),
                        r["llm"], r["tokens"], round(r["time"], 3)])
    for name, data in (("per_case_v3.csv", per_case), ("per_requirement_v3.csv", per_req)):
        with open(out / name, "w", newline="", encoding="utf-8") as fh:
            if data:
                w = csv.DictWriter(fh, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)
    print(md)
    print(f"written: {out}")
    return out


if __name__ == "__main__":
    main()
