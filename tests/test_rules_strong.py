"""System A strong rules (default `rules`) vs basic (`rules_basic`): plan-quality rules built into the itinerary
builder, Pareto package choice + template conflict explanation. Deterministic, no LLM."""
import json
from pathlib import Path

import pytest

from eval import quality as Q
from travel_agent import config as C
from travel_agent.models import TripRequest
from travel_agent.systems import run
from travel_agent.systems.rules_strong import plausible, value

ROOT = Path(__file__).resolve().parents[1]
V2 = {c["id"]: c for c in json.loads((ROOT / "eval/cases/eval_cases_v2.json").read_text())["cases"]}
DEV = [c for c in V2.values() if c["split"] == "dev" and c["expected_status"] == "OK_PLAN"]


def _rec(r, c):
    rec = json.loads(r.model_dump_json())
    rec["case"] = dict(id=c["id"], split=c["split"], group=c["group"], city=c["city"], soft_prefs=c.get("soft_prefs", []),
                       true_conflict=bool((c.get("true_conflict") or {}).get("passed")),
                       acceptable_sacrifices=(c.get("true_conflict") or {}).get("acceptable_sacrifices", []),
                       interests=c["interests"], preferred_budget_usd=c.get("preferred_budget_usd"),
                       start_date=c["start_date"], end_date=c["end_date"])
    return rec


@pytest.fixture(scope="module")
def strong():
    return {c["id"]: run("rules", TripRequest.from_case(c)) for c in DEV}


def test_variants_registered():
    c = V2["V01"]
    a, b = run("rules", TripRequest.from_case(c)), run("rules_basic", TripRequest.from_case(c))
    assert (a.system, a.variant) == ("A", "strong") and (b.system, b.variant) == ("A", "basic")
    assert a.llm_calls == b.llm_calls == 0


def test_strong_deterministic():
    c = V2["V08"]
    a, b = run("rules", TripRequest.from_case(c)), run("rules", TripRequest.from_case(c))
    strip = lambda r: [(d.date, [(i.place_id, i.start, i.end) for i in d.items]) for d in r.days]   # noqa: E731
    assert strip(a) == strip(b) and a.package.refs == b.package.refs and a.tradeoffs == b.tradeoffs


def test_strong_dev_plans_valid_and_quality(strong):
    for c in DEV:
        r = strong[c["id"]]
        assert r.status.value == "OK_PLAN" and r.all_checks_passed, (c["id"], r.message)
        q = Q.quality(_rec(r, c))
        assert q["passed"], (c["id"], q)


def test_strong_conflicts_detected_and_acceptable(strong):
    for c in DEV:
        if not (c.get("true_conflict") or {}).get("passed"):
            continue
        ch = Q.conflict_handling(_rec(strong[c["id"]], c))
        assert ch["full"], (c["id"], ch)
        assert len(ch["sacrificed"]) == min(len(s) for s in c["true_conflict"]["acceptable_sacrifices"])


def test_no_back_to_back_and_rain_indoor(cases):
    r = run("rules", TripRequest.from_case(cases["D01"]))       # v1 case with 2 rain days (not the frozen v2 eval split)
    facts = {p["place_id"]: p for e in r.tool_log if e["tool"] == "search_places" for p in e["output"]["places"]}
    rain = [d for d in r.days if "RAIN" in d.flags]
    assert rain and all(facts[i.place_id]["indoor"] == "true" for d in rain for i in d.items)
    for d in r.days:
        acts = [facts[i.place_id]["category"] if i.kind == "activity" else None for i in d.items]
        assert not any(x is not None and x == y for x, y in zip(acts, acts[1:]))


def test_full_days_filled(strong):
    for r in strong.values():
        for d in r.days[1:-1]:
            assert any(i.kind == "activity" for i in d.items), d.date


def test_plausible_hours_rules():
    import datetime as dt
    bar = dict(category="bar")
    day = dt.date(2022, 9, 18)
    assert not plausible(bar, "unknown", day, 10 * 60, 11 * 60)          # bars: evenings only (type window)
    assert plausible(bar, "unknown", day, 17 * 60, 18 * 60)
    assert plausible(bar, "Mo-Su 10:00-23:00", day, 10 * 60, 11 * 60)   # real opening_hours win
    assert not plausible(dict(category="museum"), "Mo 10:00-17:00", day, 11 * 60, 12 * 60)   # Sunday, closed
    assert plausible(dict(category="activity"), "", day, 8 * 60, 9 * 60)                       # unknown type: allowed


def test_value_uses_real_signals_only():
    base = dict(category="museum", tags=["culture"], in_wikivoyage=True, has_wikidata=True, rating=1.0, review_count=1)
    hi = value(base, ["culture"])
    assert value(dict(base, rating=5.0, review_count=9999), ["culture"]) == hi      # synthetic fields ignored
    assert value(dict(base, has_wikidata=False), ["culture"]) < hi
    assert value(dict(base, category="cafe"), ["culture"]) < hi
    assert set(C.TYPE_HOURS) >= {"bar", "pub", "nightclub", "museum", "theatre"}


def test_basic_unchanged_cheapest():
    c = V2["V02"]
    b = run("rules_basic", TripRequest.from_case(c))
    assert b.package.refs == b.candidates[0]["refs"]
    assert not any("conflict" in t.lower() for t in b.tradeoffs)
