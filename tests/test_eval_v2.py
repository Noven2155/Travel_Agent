"""Eval v2: request extensions (date flex, soft prefs), oracle = pipeline consistency, true-conflict invariants,
final_checks with flex, conflict_handling and plan-quality metrics."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from eval import quality as Q
from eval import run_eval
from travel_agent import prefs as P
from travel_agent.checks import final_checks
from travel_agent.models import TripRequest
from travel_agent.pipeline import build_candidates, weather_step
from travel_agent.systems import run
from travel_agent.tool_log import ToolLog

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "eval" / "cases" / "eval_cases_v2.json"


@pytest.fixture(scope="module")
def v2():
    return {c["id"]: c for c in json.loads(V2.read_text())["cases"]}


def test_v2_frozen_and_counts(v2):
    assert hashlib.sha256(V2.read_bytes()).hexdigest() == (ROOT / "eval/cases/FROZEN_v2.sha256").read_text().split()[0]
    ev = [c for c in v2.values() if c["split"] == "eval"]
    assert len(ev) == 40 and sum(c["split"] == "dev" for c in v2.values()) == 8
    assert sum(1 for c in ev if c["group"] in "BCD") == 24
    assert all(c["oracle_places"]["status"] == "PASS" for c in v2.values())       # NYC filled from nyc_places.csv


def test_request_backward_compatible(cases):
    r = TripRequest.from_case(cases["A01"])
    assert r.depart_flex_days == 0 and r.soft_prefs == [] and not r.has_flex
    assert r.date_pairs() == [(r.start_date, r.end_date)]


def test_date_pairs_flex(v2):
    r = TripRequest.from_case(v2["D01"])
    pairs = r.date_pairs()
    assert pairs[0] == (r.start_date, r.end_date)
    assert len(pairs) == 7                         # 9 combinations minus the two that change the length by 2 nights
    assert all(abs((e - s).days - r.nights) <= 1 for s, e in pairs)


def test_invalid_soft_pref_combo(v2):
    c = dict(v2["B10"], preferred_budget_usd=None)
    with pytest.raises(ValueError):
        TripRequest.from_case(c)


@pytest.mark.parametrize("cid", ["B01", "B05", "B07", "B10", "B12", "C01", "C06", "D02", "D05", "V04"])
def test_oracle_matches_pipeline(v2, cid):
    c = v2[cid]
    req = TripRequest.from_case(c)
    log = ToolLog("t")
    conds, _ = weather_step(log, req)
    cands = build_candidates(log, req, conditions=conds)
    tc = c["true_conflict"]
    assert cands[0]["n_within_budget"] == tc["n_feasible_packages"]
    front = P.pareto_front(tuple(x["sacrificed_prefs"]) for x in cands)
    assert sorted(front) == sorted(tuple(x) for x in tc["acceptable_sacrifices"])


def test_true_conflict_invariants(v2):
    for c in v2.values():
        if c["group"] in "BCD":
            tc = c["true_conflict"]
            assert tc["passed"] and "none" not in tc["profiles"]
            assert len(tc["acceptable_sacrifices"]) >= 2 and tc["n_feasible_packages"] >= 20
            assert all(o["cheapest"]["total"] <= c["budget_usd"] for o in tc["pareto_options"])


@pytest.fixture(scope="module")
def d01(v2):
    r = run("rules", TripRequest.from_case(v2["D01"]))
    assert r.status.value == "OK_PLAN"
    return r


def test_flex_plan_passes_checks(d01):
    assert d01.all_checks_passed


def test_dates_outside_flex_fail(d01, v2):
    req = d01.request.model_copy(update=dict(depart_flex_days=0, return_flex_days=0))
    log = ToolLog("x")
    log.entries = copy.deepcopy(d01.tool_log)
    rep = final_checks(log, req, d01.package, d01.days, d01.dropped, d01.day_conditions)
    shifted = (d01.package.flight_out["date"], d01.package.flight_back["date"]) != (v2["D01"]["start_date"], v2["D01"]["end_date"])
    assert ("dates" in rep.failures) == shifted


def _rec(d01, v2):
    rec = json.loads(d01.model_dump_json())
    c = v2["D01"]
    rec["case"] = dict(id="D01", split="eval", group="D", city=c["city"], soft_prefs=c["soft_prefs"], true_conflict=True,
                       acceptable_sacrifices=c["true_conflict"]["acceptable_sacrifices"], interests=c["interests"],
                       preferred_budget_usd=None, start_date=c["start_date"], end_date=c["end_date"])
    return rec


def test_conflict_handling(d01, v2):
    rec = _rec(d01, v2)
    ch = Q.conflict_handling(rec)
    assert ch["detected"] is False and ch["explained"] is False        # rules never state the conflict
    sac = ch["sacrificed"]
    rec["tradeoffs"] = ["conflict: cannot have both exact dates and dry days; sacrificed " +
                        ("the rain-free days (weather)" if sac == ["dry_days"] else "the exact dates (shifted by a day)")]
    ch2 = Q.conflict_handling(rec)
    assert ch2["detected"] and ch2["explained"] == bool(sac) and ch2["acceptable"] == ch["acceptable"]
    assert Q.soft_pref_satisfaction(rec) == pytest.approx(1 - len(sac) / 2)


def test_quality_checks_detect_problems(d01, v2):
    rec = _rec(d01, v2)
    days = rec["days"]
    full = next(d for d in days[1:-1] if d["items"])
    bar = next(r for r in Q._places("Chicago").values() if r["category"] == "bar" and not r["opening_hours"])
    it = dict(full["items"][0], place_id=bar["place_id"], name=bar["name"], kind="activity", start="09:40", end="10:40")
    full["items"] = [it, dict(it, start="11:00", end="12:00")]
    q = Q.quality(rec)
    assert "opening_plausibility" in q["failed"] and "no_back_to_back_duplicate" in q["failed"]
    full["items"] = []
    assert "no_empty_full_day" in Q.quality(rec)["failed"]


def test_interest_relevance(d01, v2):
    rec = _rec(d01, v2)
    rec["case"]["interests"] = ["culture"]
    for d in rec["days"]:
        d["items"] = [x for x in d["items"] if Q._places("Chicago").get(x["place_id"], {}).get("category") != "museum"]
    assert "interest_relevance" in Q.quality(rec)["failed"]


def test_run_eval_v2_default(tmp_path):
    out = run_eval.main(["--system", "rules", "--split", "dev", "--ids", "V02,V04", "--out", str(tmp_path / "r")])
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["cases_version"] == "v2" and meta["frozen_ok"] is True
    rec = json.loads((out / "V04.json").read_text())
    assert rec["case"]["true_conflict"] and rec["case"]["acceptable_sacrifices"]
