"""Score result directories and print the 3-row comparison table (spec section 6).

    python -m eval.score eval/results/rules/<ts> [eval/results/single/<ts> eval/results/multi/<ts>] [--out DIR]

Central metric: valid_plan_rate over D = eval cases in groups A-D whose oracle is feasible (package FEASIBLE and
places oracle not FAIL), restricted to the cases present in the run. valid_plan = status OK_PLAN and all
final_checks pass and wall_time_s <= 300 and rounds_used <= 3. Also reported on the conflicting subset (groups
B-D) with a Wilson 95% CI; group E as correct_refusal_rate; secondary metrics as in spec 6.2.
v2 secondary metrics (eval/quality.py): soft_pref_satisfaction (cases with soft prefs), conflict_handling on the
true-conflict cases (detected / acceptable sacrifice / explained), and plan-quality checks (no empty full day,
opening-hour plausibility, interest relevance, no back-to-back duplicates). They never change valid_plan.
Writes comparison.md / comparison.csv / per_case.csv to --out (default eval/reports/<timestamp>).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from . import __name__ as _pkg  # noqa: F401
from travel_agent import config as C  # noqa: E402
from .quality import QUALITY_CHECKS, conflict_handling, quality, soft_pref_satisfaction  # noqa: E402

CHECKS = ["schema", "budget", "dates", "capacity", "car", "day_load", "travel", "weather_rule", "coverage", "grounding"]
SYSTEM_LABEL = {"A": "A - rules", "B": "B - single agent", "C": "C - multi-agent"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, math.ceil(0.95 * len(xs)) - 1)
    return xs[k]


def load_dir(d: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = json.loads((d / "run_meta.json").read_text()) if (d / "run_meta.json").exists() else {}
    recs = [json.loads(p.read_text()) for p in sorted(d.glob("*.json")) if p.name != "run_meta.json" and not p.name.endswith(".tool_log.json")]
    return meta, recs


def is_valid(r: dict[str, Any]) -> bool:
    return (r["status"] == "OK_PLAN" and bool(r.get("all_checks_passed")) and r.get("wall_time_s", 1e9) <= C.METRIC_TIME_LIMIT_S
            and r.get("rounds_used", 99) <= C.MAX_ROUNDS)


SPLITS = {"eval"}          # --dev scores the dev split instead (threshold tuning only; never reported)


def in_D(r: dict[str, Any]) -> bool:
    c = r["case"]
    return (c["split"] in SPLITS and c["group"] in "ABCD" and c["oracle_package_status"] == "FEASIBLE"
            and c["oracle_places_status"] != "FAIL")


def check_passed(r: dict[str, Any], name: str) -> bool | None:
    cr = r.get("check_report")
    if not cr:
        return None
    for c in cr["checks"]:
        if c["name"] == name:
            return c["passed"]
    return None


def plan_quality(r: dict[str, Any]) -> dict[str, float]:
    """Descriptive extras (not pass/fail): activities per full day, empty full days, travel minutes per day."""
    days = r.get("days") or []
    if not days:
        return {}
    full = days[1:-1]
    acts = [sum(1 for it in d["items"] if it["kind"] == "activity") for d in full]
    travel = [sum(it["travel_min"] for it in d["items"]) for d in days]
    return dict(acts_per_full_day=statistics.mean(acts) if acts else 0.0, empty_full_days=sum(1 for d in full if not d["items"]),
                travel_min_per_day=statistics.mean(travel) if travel else 0.0)


def fmt_rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 cases)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.2f} [{lo:.2f}, {hi:.2f}]"


def summarize(meta: dict[str, Any], recs: list[dict[str, Any]]) -> dict[str, Any]:
    sysc = recs[0]["system"] if recs else "?"
    D = [r for r in recs if in_D(r)]
    Dc = [r for r in D if r["case"]["intended_conflict"]]
    E = [r for r in recs if r["case"]["group"] == "E" and r["case"]["split"] in SPLITS]
    vD, vDc = sum(map(is_valid, D)), sum(map(is_valid, Dc))
    refusal = sum(1 for r in E if r["status"] == r["case"]["expected_status"] and not r.get("days"))
    e_status = sum(1 for r in E if r["status"] == r["case"]["expected_status"])
    times = [r["wall_time_s"] for r in recs]
    llm = [r.get("llm_calls", 0) for r in recs]
    tokens = [r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in recs]
    rounds = [r.get("rounds_used", 0) for r in recs if r.get("check_report")]
    cov = [r["check_report"]["coverage"] for r in recs if r.get("check_report") and r["check_report"].get("coverage") is not None]
    rain = [r for r in recs if r.get("check_report") and r["check_report"].get("rain_days")]
    rain_ok = sum(1 for r in rain if check_passed(r, "weather_rule"))
    with_plan = [r for r in recs if r.get("check_report")]
    fail_hist = Counter(c for r in with_plan for c in CHECKS if check_passed(r, c) is False)
    q = [plan_quality(r) for r in D if r.get("days")]
    statuses = Counter(r["status"] for r in recs)
    # ---- v2 secondary metrics
    sp = [x for x in (soft_pref_satisfaction(r) for r in D) if x is not None]
    TC = [r for r in D if r["case"].get("true_conflict")]
    ch = [conflict_handling(r) for r in TC]
    qs = [quality(r) for r in D]
    qs = [x for x in qs if x is not None]
    q_hist = Counter(n for x in qs for n in x["failed"])
    extra = dict(n_soft=len(sp), soft_pref_mean=statistics.mean(sp) if sp else float("nan"),
                 n_tc=len(TC), ch_mean=statistics.mean(x["score"] for x in ch) if ch else float("nan"),
                 ch_detected=sum(x["detected"] for x in ch), ch_acceptable=sum(x["acceptable"] for x in ch),
                 ch_explained=sum(x["explained"] for x in ch), ch_full=sum(x["full"] for x in ch),
                 n_quality=len(qs), quality_pass=sum(x["passed"] for x in qs), quality_hist=dict(q_hist),
                 relevance_mean=statistics.mean(x["relevance_share"] for x in qs) if qs else float("nan"))
    return dict(**extra,system=sysc, label=SYSTEM_LABEL.get(sysc, sysc), dir=meta.get("_dir", ""), n_cases=len(recs), city=meta.get("city", "?"),
                split=meta.get("split", "?"), git_commit=meta.get("git_commit"), frozen_ok=meta.get("frozen_ok"),
                n_D=len(D), valid_D=vD, valid_plan_rate=(vD / len(D)) if D else float("nan"), ci_D=wilson(vD, len(D)),
                n_conflict=len(Dc), valid_conflict=vDc, ci_conflict=wilson(vDc, len(Dc)),
                n_E=len(E), correct_refusal=refusal, e_status=e_status,
                time_mean=statistics.mean(times) if times else float("nan"), time_p95=p95(times),
                llm_mean=statistics.mean(llm) if llm else 0, llm_max=max(llm) if llm else 0,
                tokens_mean=statistics.mean(tokens) if tokens else 0, rounds_mean=statistics.mean(rounds) if rounds else 0,
                grounding_fail=fail_hist.get("grounding", 0), schema_fail=fail_hist.get("schema", 0), n_with_plan=len(with_plan),
                coverage_mean=statistics.mean(cov) if cov else float("nan"), n_rain=len(rain), rain_ok=rain_ok,
                fail_hist=dict(fail_hist), statuses=dict(statuses),
                acts_per_full_day=statistics.mean([x["acts_per_full_day"] for x in q]) if q else float("nan"),
                empty_full_days=sum(x["empty_full_days"] for x in q) if q else 0,
                travel_min_per_day=statistics.mean([x["travel_min_per_day"] for x in q]) if q else float("nan"),
                needs_data=statuses.get("NEEDS_DATA", 0))


def render(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    hdr = ["system", "cases", "valid_plan_rate (D) [Wilson 95%]", "conflicting B-D [Wilson 95%]", "correct_refusal (E)",
           "time mean / p95 (s)", "LLM calls mean / max", "tokens / case", "rounds mean", "grounding / schema fails",
           "coverage mean", "rain_handled", "E correct status"]
    lines = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    csv_rows = []
    for s in rows:
        cells = [s["label"], f"{s['n_cases']} ({s['city']}, {s['split']})", fmt_rate(s["valid_D"], s["n_D"]),
                 fmt_rate(s["valid_conflict"], s["n_conflict"]), f"{s['correct_refusal']}/{s['n_E']}",
                 f"{s['time_mean']:.2f} / {s['time_p95']:.2f}", f"{s['llm_mean']:.1f} / {s['llm_max']}", f"{s['tokens_mean']:.0f}",
                 f"{s['rounds_mean']:.2f}", f"{s['grounding_fail']} / {s['schema_fail']} (of {s['n_with_plan']} plans)",
                 f"{s['coverage_mean']:.2f}", f"{s['rain_ok']}/{s['n_rain']}", f"{s['e_status']}/{s['n_E']}"]
        lines.append("| " + " | ".join(cells) + " |")
        csv_rows.append(dict(system=s["system"], label=s["label"], n_cases=s["n_cases"], city=s["city"], split=s["split"],
                             n_D=s["n_D"], valid_D=s["valid_D"], valid_plan_rate=round(s["valid_plan_rate"], 4),
                             ci_D_low=round(s["ci_D"][0], 4), ci_D_high=round(s["ci_D"][1], 4), n_conflict=s["n_conflict"],
                             valid_conflict=s["valid_conflict"], ci_conflict_low=round(s["ci_conflict"][0], 4),
                             ci_conflict_high=round(s["ci_conflict"][1], 4), n_E=s["n_E"], correct_refusal=s["correct_refusal"], e_correct_status=s["e_status"],
                             time_mean_s=round(s["time_mean"], 3), time_p95_s=round(s["time_p95"], 3), llm_calls_mean=s["llm_mean"],
                             llm_calls_max=s["llm_max"], tokens_mean=s["tokens_mean"], rounds_mean=round(s["rounds_mean"], 3),
                             grounding_fail=s["grounding_fail"], schema_fail=s["schema_fail"], coverage_mean=round(s["coverage_mean"], 3),
                             rain_cases=s["n_rain"], rain_handled=s["rain_ok"], needs_data=s["needs_data"],
                             acts_per_full_day=round(s["acts_per_full_day"], 2), empty_full_days=s["empty_full_days"],
                             travel_min_per_day=round(s["travel_min_per_day"], 1), statuses=json.dumps(s["statuses"]),
                             fail_hist=json.dumps(s["fail_hist"]), dir=s["dir"]))
    md = "\n".join(lines)
    hdr2 = ["system", "soft_pref_satisfaction (mean)", "conflict_handling (mean)", "detected", "acceptable sacrifice",
            "explained", "full handling [Wilson 95%]", "quality pass (D plans)", "quality failures by check", "interest relevance (mean share)"]
    md += "\n\nv2 secondary metrics (true-conflict cases = groups B-D of eval_cases_v2; valid_plan unchanged):\n\n"
    md += "| " + " | ".join(hdr2) + " |\n|" + "---|" * len(hdr2) + "\n"
    for s in rows:
        md += "| " + " | ".join([s["label"], f"{s['soft_pref_mean']:.2f} (n={s['n_soft']})", f"{s['ch_mean']:.2f} (n={s['n_tc']})",
                                  f"{s['ch_detected']}/{s['n_tc']}", f"{s['ch_acceptable']}/{s['n_tc']}", f"{s['ch_explained']}/{s['n_tc']}",
                                  fmt_rate(s["ch_full"], s["n_tc"]), f"{s['quality_pass']}/{s['n_quality']}",
                                  ", ".join(f"{k} {s['quality_hist'].get(k, 0)}" for k in QUALITY_CHECKS),
                                  f"{s['relevance_mean']:.2f}"]) + " |\n"
    for r_ in csv_rows:
        s_ = next(x for x in rows if x["system"] == r_["system"] and x["dir"] == r_["dir"])
        r_.update(soft_pref_mean=round(s_["soft_pref_mean"], 4), n_true_conflict=s_["n_tc"], conflict_handling_mean=round(s_["ch_mean"], 4),
                  ch_detected=s_["ch_detected"], ch_acceptable=s_["ch_acceptable"], ch_explained=s_["ch_explained"], ch_full=s_["ch_full"],
                  quality_pass=s_["quality_pass"], n_quality=s_["n_quality"], quality_hist=json.dumps(s_["quality_hist"]),
                  relevance_mean=round(s_["relevance_mean"], 4))
    md += "\n\nFailure histogram (runs with a plan, by check) and status counts:\n\n"
    for s in rows:
        md += f"- {s['label']}: failures {s['fail_hist'] or '{}'}; statuses {s['statuses']}; plan quality on D: " \
              f"{s['acts_per_full_day']:.2f} activities / full day, {s['empty_full_days']} empty full days, " \
              f"{s['travel_min_per_day']:.0f} travel min / day\n"
    return md, csv_rows


def per_case_rows(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in recs:
        c = r["case"]
        cr = r.get("check_report") or {}
        sp = soft_pref_satisfaction(r)
        ch = conflict_handling(r) or {}
        q = quality(r) or {}
        out.append(dict(system=r["system"], id=c["id"], group=c["group"], city=c["city"], in_D=in_D(r), conflict=c["intended_conflict"],
                        expected=c["expected_status"], status=r["status"], valid_plan=is_valid(r),
                        failed_checks=";".join(x["name"] for x in cr.get("checks", []) if not x["passed"]),
                        coverage=cr.get("coverage"), total=(r.get("package") or {}).get("total"),
                        oracle_cheapest=c.get("oracle_cheapest_total"), wall_time_s=r["wall_time_s"], llm_calls=r.get("llm_calls", 0),
                        tokens=r.get("tokens_in", 0) + r.get("tokens_out", 0), rounds=r.get("rounds_used", 0),
                        soft_prefs=";".join(c.get("soft_prefs") or []), true_conflict=bool(c.get("true_conflict")),
                        soft_pref_satisfaction=None if sp is None else round(sp, 3), sacrificed=";".join(ch.get("sacrificed") or []),
                        acceptable_sacrifices=" | ".join("+".join(x) for x in c.get("acceptable_sacrifices") or []),
                        ch_detected=ch.get("detected"), ch_acceptable=ch.get("acceptable"), ch_explained=ch.get("explained"),
                        conflict_handling=ch.get("score"), quality_failed=";".join(q.get("failed", [])),
                        quality_details=" || ".join(d for k in QUALITY_CHECKS for d in q.get(k, []))[:500],
                        message=r.get("message", "")))
    return out


def main(argv: list[str] | None = None) -> str:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dev", action="store_true", help="score the dev split (threshold tuning only)")
    a = ap.parse_args(argv)
    SPLITS.clear()
    SPLITS.add("dev" if a.dev else "eval")
    rows, cases = [], []
    for d in a.dirs:
        meta, recs = load_dir(Path(d))
        if not recs:
            print(f"(no results in {d})")
            continue
        meta["_dir"] = str(d)
        rows.append(summarize(meta, recs))
        cases += per_case_rows(recs)
    rows.sort(key=lambda s: s["system"])
    md, csv_rows = render(rows)
    title = f"# Comparison ({dt.datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n" \
            "valid_plan = OK_PLAN and all final_checks pass and time <= 300 s and rounds <= 3. " \
            "D = eval cases A-D with a feasible oracle, restricted to the cases in each run.\n\n"
    out = Path(a.out) if a.out else C.EVAL_DIR / "reports" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.md").write_text(title + md)
    with open(out / "comparison.csv", "w", newline="", encoding="utf-8") as f:
        if csv_rows:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
            w.writeheader()
            w.writerows(csv_rows)
    with open(out / "per_case.csv", "w", newline="", encoding="utf-8") as f:
        if cases:
            w = csv.DictWriter(f, fieldnames=list(cases[0]))
            w.writeheader()
            w.writerows(cases)
    print(title + md)
    print(f"written: {out}/comparison.md, comparison.csv, per_case.csv")
    return md


if __name__ == "__main__":
    main()
