"""Secondary metrics for eval v2 (valid_plan_rate stays the central metric). Pure functions over one result record
(eval/results/<system>/<ts>/<id>.json); facts come from the run's own tool log and the local data files, never from
what a model claims. Synthetic place fields (rating, review_count, price_level) are NOT used anywhere.

  soft_pref_satisfaction  share of the case's soft preferences satisfied by the chosen package (prefs.evaluate)
  conflict_handling       on true-conflict cases: mean of
                            detected   - the plan says there is a conflict / trade-off (tradeoffs + message text)
                            acceptable - the sacrificed-preference set is one of the case's acceptable sacrifices
                                         (= a Pareto-optimal profile verified by the oracle)
                            explained  - detected, and every sacrificed preference is named in the text
  quality checks          no_empty_full_day, opening_plausibility, interest_relevance, no_back_to_back_duplicate

THRESHOLDS were set on the 8 dev cases only (V01-V08, rules system A, see eval/cases/FROZEN_v2.md) and are frozen with v2.
"""
from __future__ import annotations

import csv
import datetime as dt
from functools import lru_cache
from typing import Any, Optional

from travel_agent import config as C
from travel_agent import prefs as P
from travel_agent.data_access import is_open
from travel_agent.timeutil import hm_to_min

THRESHOLDS = dict(
    edge_day_min_window_h=5.0,          # an arrival/departure day with a window >= 5 h must have >= 1 item
    relevance_min_share=1.0,            # every interest with notable places available must get >= 1 notable place
    meal_at_bar_from="11:00",           # dev tuning (V08): pubs/bars tagged food serve lunch -> a MEAL there is fine from 11:00
)
# plausible visiting hours by OSM category when the place has no parseable opening_hours (local time, minutes)
CATEGORY_HOURS = {
    "bar": ("16:00", "26:00"), "pub": ("16:00", "26:00"), "nightclub": ("20:00", "28:00"),
    "theatre": ("12:00", "23:59"),
    "museum": ("09:00", "18:00"), "gallery": ("10:00", "18:00"), "arts_centre": ("09:00", "22:00"),
    "park": ("06:00", "21:30"), "viewpoint": ("06:00", "22:00"), "zoo": ("09:00", "18:00"), "aquarium": ("09:00", "18:00"),
    "restaurant": ("11:00", "23:00"), "cafe": ("07:00", "19:00"), "fast_food": ("10:00", "23:00"), "food_court": ("10:00", "21:00"),
    "shopping": ("10:00", "21:00"),
}
# categories that count as a "notable" match for an interest (notable = in Wikivoyage AND has a Wikidata item)
CORE_CATEGORIES = {
    "culture": {"museum", "gallery"}, "nature": {"park", "viewpoint", "zoo"}, "shows": {"theatre", "arts_centre"},
    "attractions": {"attraction", "viewpoint", "aquarium", "zoo", "museum", "historic", "theme_park"},
    "family": {"zoo", "aquarium", "theme_park", "museum"}, "nightlife": {"bar", "pub", "nightclub"}, "shopping": {"shopping"},
}
DETECT_WORDS = ["conflict", "trade-off", "tradeoff", "trade off", "cannot satisfy", "can't satisfy", "cannot meet", "not all preferences",
                "sacrific", "compromise", "had to give up", "instead of"]


# ----------------------------------------------------------------- helpers
@lru_cache(maxsize=4)
def _places(city: str) -> dict[str, dict[str, str]]:
    p = C.PLACES_DIR / f"{C.CITIES[city]['key']}_places.csv"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {r["place_id"]: r for r in csv.DictReader(f)}


def _facts(rec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for e in rec.get("tool_log") or []:
        o = e.get("output") or {}
        if e["tool"] == "search_places":
            for p in o.get("places", []):
                facts.setdefault(p["place_id"], dict(p))
        elif e["tool"] == "get_place_details" and o.get("status") == "OK":
            facts.setdefault(o["place"]["place_id"], dict(o["place"]))
            facts[o["place"]["place_id"]]["opening_hours"] = o.get("opening_hours")
    return facts


def _text(rec: dict[str, Any]) -> str:
    return (" ".join(rec.get("tradeoffs") or []) + " " + (rec.get("message") or "")).lower()


def _notable(r: dict[str, str]) -> bool:
    return r.get("in_wikivoyage") == "true" and bool(r.get("wikidata"))


# ----------------------------------------------------------------- soft preferences / conflict handling
def pref_vector(rec: dict[str, Any]) -> Optional[dict[str, Optional[bool]]]:
    case, pkg = rec["case"], rec.get("package")
    prefs = case.get("soft_prefs") or []
    if not prefs or not pkg or not pkg.get("flight_out") or not pkg.get("flight_back") or not pkg.get("stay"):
        return None
    req = rec.get("request") or {}
    return P.evaluate(prefs, city=case["city"], req_start=req.get("start_date", case.get("start_date")),
                      req_end=req.get("end_date", case.get("end_date")), flight_out=pkg["flight_out"], flight_back=pkg["flight_back"],
                      stay_km=pkg["stay"]["km_to_center"], total=pkg["total"], preferred_budget=case.get("preferred_budget_usd"),
                      rain_by_date=P.rain_map(rec.get("day_conditions") or []))


def soft_pref_satisfaction(rec: dict[str, Any]) -> Optional[float]:
    """None when the case has no soft prefs; 0.0 when it has soft prefs but the run produced no package."""
    if not rec["case"].get("soft_prefs"):
        return None
    v = pref_vector(rec)
    return 0.0 if v is None else P.satisfaction(v)


def conflict_handling(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    case = rec["case"]
    if not case.get("true_conflict"):
        return None
    v = pref_vector(rec)
    text = _text(rec)
    if v is None or rec["status"] != "OK_PLAN":
        return dict(detected=False, acceptable=False, explained=False, score=0.0, sacrificed=None, full=False)
    sac = list(P.sacrificed(v))
    detected = any(w in text for w in DETECT_WORDS)
    acceptable = sac in [list(x) for x in case.get("acceptable_sacrifices") or []]
    named = all(any(k in text for k in P.PREF_KEYWORDS[p]) for p in sac) if sac else False
    explained = detected and named
    score = (detected + acceptable + explained) / 3
    return dict(detected=detected, acceptable=acceptable, explained=explained, score=round(score, 4), sacrificed=sac,
                full=bool(detected and acceptable and explained))


# ----------------------------------------------------------------- quality checks
def quality(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    days = rec.get("days") or []
    if not days or rec["status"] != "OK_PLAN":
        return None
    case = rec["case"]
    facts = _facts(rec)
    places = _places(case["city"])
    out: dict[str, Any] = {}
    # 1. no empty full day (arrival/departure days only if their window is long enough)
    det = []
    for i, d in enumerate(days):
        acts = [it for it in d["items"] if it["kind"] == "activity"]
        edge = i in (0, len(days) - 1)
        if not edge and not acts:
            det.append(f"{d['date']}: full day without activities")
        elif edge and not d["items"] and d.get("window"):
            w = (hm_to_min(d["window"][1]) - hm_to_min(d["window"][0])) / 60
            if w >= THRESHOLDS["edge_day_min_window_h"]:
                det.append(f"{d['date']}: arrival/departure day with a {w:.1f} h window and no items")
    out["no_empty_full_day"] = det
    # 2. opening-hour plausibility (OSM hours when parseable, else category defaults)
    det = []
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        for it in d["items"]:
            f = facts.get(it["place_id"]) or {}
            cat = f.get("category") or (places.get(it["place_id"]) or {}).get("category", "")
            hours = f.get("opening_hours") or (places.get(it["place_id"]) or {}).get("opening_hours") or ""
            s, e = hm_to_min(it["start"]), hm_to_min(it["end"])
            ok = is_open(hours, date, s, e) if hours and hours != "unknown" else None
            if ok is None and cat in CATEGORY_HOURS:
                lo, hi = (hm_to_min(x) for x in CATEGORY_HOURS[cat])
                if it["kind"] == "meal" and cat in ("bar", "pub"):
                    lo = hm_to_min(THRESHOLDS["meal_at_bar_from"])
                ok = lo <= s and e <= hi
            if ok is False:
                det.append(f"{d['date']} {it['start']}-{it['end']} {cat} '{it.get('name') or it['place_id']}'")
    out["opening_plausibility"] = det
    # 3. interest relevance (notable places of the interest's core categories, when the city has them)
    det, n_need, n_ok = [], 0, 0
    sched = [it["place_id"] for d in days for it in d["items"]]
    for t in case.get("interests") or []:
        core = CORE_CATEGORIES.get(t)
        if not core:
            continue               # food is served by meals; no notable-place requirement
        avail = [r for r in places.values() if t in r["tags"].split(";") and r["category"] in core and _notable(r)]
        if not avail:
            continue
        n_need += 1
        hit = [pid for pid in sched if pid in places and places[pid]["category"] in core and _notable(places[pid])
               and t in places[pid]["tags"].split(";")]
        if hit:
            n_ok += 1
        else:
            det.append(f"'{t}': no notable {'/'.join(sorted(core))} scheduled ({len(avail)} available)")
    share = (n_ok / n_need) if n_need else 1.0
    out["interest_relevance"] = det if share < THRESHOLDS["relevance_min_share"] else []
    out["relevance_share"] = round(share, 3)
    # 4. no back-to-back duplicates of the same kind (consecutive activities of the same category)
    det = []
    for d in days:
        prev = None
        for it in d["items"]:
            if it["kind"] != "activity":
                prev = None
                continue
            cat = (facts.get(it["place_id"]) or {}).get("category") or (places.get(it["place_id"]) or {}).get("category")
            if prev is not None and cat == prev:
                det.append(f"{d['date']}: two {cat} in a row ({it.get('name') or it['place_id']})")
            prev = cat
    out["no_back_to_back_duplicate"] = det
    names = ["no_empty_full_day", "opening_plausibility", "interest_relevance", "no_back_to_back_duplicate"]
    out["failed"] = [n for n in names if out[n]]
    out["passed"] = not out["failed"]
    return out


QUALITY_CHECKS = ["no_empty_full_day", "opening_plausibility", "interest_relevance", "no_back_to_back_duplicate"]
