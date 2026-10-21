"""Eval v3 (free-text segment): deterministic checks of the 2-3 hidden key requirements of a case.

Each requirement ends in exactly one outcome:
  met       the plan satisfies it (checked on the plan / package / tool log, never on what the system claims)
  flagged   not met, but the system said so: an entry of tradeoffs / message / the parsed request's
            unparsed_requirements names the topic (requirement keywords) together with a not-handled marker
  ignored   not met and not mentioned (silently ignored)
key_requirement_score of a case = met / n. 'flag_unsupported' requirements (e.g. wheelchair access - the data has
no step-free information) can only be met BY flagging them. A run without a plan meets nothing.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

from travel_agent import config as C
from travel_agent import prefs as P
from travel_agent.timeutil import hm_to_min, iso_local_hm

from .quality import _facts, _places

NOT_HANDLED = ["not handled", "could not", "couldn't", "cannot", "can't", "unable", "not supported", "no data", "not possible",
               "not available", "unparsed", "not guaranteed", "not checked", "no information"]
FLAG_WORDS = {   # default topic keywords per checker (a requirement may add its own 'keywords')
    "no_activity_in_window": ["nap", "rest", "pray", "blocked", "free time", "kept free", "break"],
    "day_window": ["late start", "morning", "day start", "day_start", "day end", "day_end", "nothing before", "early start"],
    "budget_max": ["budget"], "min_count_category": ["museum", "gallery", "theatre", "show", "park", "zoo", "bar", "category"],
    "no_category": ["avoid", "museum", "bar", "excluded"], "no_flight_departure_before": ["early flight", "departure", "flight time"],
    "evening_meal_within_km_of_lodging": ["dinner", "near the lodging", "close to", "walking distance"],
    "priority_respected": ["priority", "location", "central"], "max_walk_leg": ["walk"], "nonstop_flights": ["nonstop", "connection"],
    "central_stay": ["central", "downtown", "location"], "party_size": ["travelers", "people", "party"], "car_included": ["car"],
    "near_cheapest": ["cheapest", "price"], "flag_unsupported": [],
}


def _hav(a, b) -> float:
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _items(rec):
    return [(d, it) for d in rec.get("days") or [] for it in d["items"]]


def _cat(rec, pid, facts, places):
    return (facts.get(pid) or {}).get("category") or (places.get(pid) or {}).get("category")


def _price_call(rec) -> Optional[dict]:
    pid = (rec.get("package") or {}).get("price_call_id")
    return next((e for e in rec.get("tool_log") or [] if e.get("call_id") == pid), None)


def check(rec: dict[str, Any], kr: dict[str, Any], city: str) -> tuple[Optional[bool], str]:
    """-> (met, detail). met None = cannot be evaluated (no plan)."""
    chk, p = kr["checker"], kr["params"]
    pkg = rec.get("package")
    if rec.get("status") != "OK_PLAN" or not pkg:
        return None, "no plan"
    facts, places = _facts(rec), _places(city)
    items = _items(rec)
    if chk == "budget_max":
        return pkg["total"] <= p["usd"] + 1e-9, f"total {pkg['total']} vs {p['usd']}"
    if chk == "no_activity_in_window":
        a, b = hm_to_min(p["start"]), hm_to_min(p["end"])
        bad = [f"{d['date']} {it['start']}-{it['end']}" for d, it in items if hm_to_min(it["start"]) < b and a < hm_to_min(it["end"])]
        return not bad, "; ".join(bad[:4]) or "free"
    if chk == "day_window":
        bad = [f"{d['date']} {it['start']}-{it['end']}" for d, it in items
               if ("start" in p and hm_to_min(it["start"]) < hm_to_min(p["start"])) or ("end" in p and hm_to_min(it["end"]) > hm_to_min(p["end"]))]
        return not bad, "; ".join(bad[:4]) or "inside"
    if chk == "min_count_category":
        n = sum(1 for _, it in items if it["kind"] == "activity" and _cat(rec, it["place_id"], facts, places) in set(p["categories"]))
        return n >= p["min"], f"{n} of {p['categories']} (need {p['min']})"
    if chk == "no_category":
        bad = [it.get("name") or it["place_id"] for _, it in items if _cat(rec, it["place_id"], facts, places) in set(p["categories"])]
        return not bad, ", ".join(bad[:4]) or "none"
    if chk == "no_flight_departure_before":
        deps = [iso_local_hm(pkg["flight_out"]["dep"]), iso_local_hm(pkg["flight_back"]["dep"])]
        return all(x >= p["time"] for x in deps), f"departures {deps}"
    if chk == "evening_meal_within_km_of_lodging":
        st = (pkg["stay"]["lat"], pkg["stay"]["lon"])
        dist = []
        for _, it in items:
            if it["kind"] == "meal" and hm_to_min(it["start"]) >= hm_to_min("17:00"):
                f = facts.get(it["place_id"]) or places.get(it["place_id"]) or {}
                if f:
                    dist.append(round(_hav(st, (float(f["lat"]), float(f["lon"]))), 2))
        return bool(dist) and max(dist) <= p["km"], f"dinner km {dist}" if dist else "no dinner scheduled"
    if chk == "priority_respected":
        vec = P.evaluate(p["soft_prefs"], city=city, req_start=pkg["flight_out"]["date"], req_end=pkg["flight_back"]["date"],
                         flight_out=pkg["flight_out"], flight_back=pkg["flight_back"], stay_km=pkg["stay"]["km_to_center"],
                         total=pkg["total"])
        sac = list(P.sacrificed(vec))
        return sac in [list(x) for x in p["acceptable_sacrifices"]], f"sacrificed {sac}; ok = {p['acceptable_sacrifices']}"
    if chk == "max_walk_leg":
        bad = [f"{d['date']} {it['travel_min']} min" for d, it in items if it["mode"] == "walk" and it["travel_min"] > p["minutes"]]
        return not bad, "; ".join(bad[:4]) or "ok"
    if chk == "nonstop_flights":
        ok = all(int(f.get("stops", 1)) == 0 for f in (pkg["flight_out"], pkg["flight_back"]))
        return ok, "nonstop" if ok else "connection"
    if chk == "central_stay":
        km = pkg["stay"]["km_to_center"]
        return km <= C.CENTRAL_RADIUS_KM[city], f"{km} km"
    if chk == "party_size":
        pc = _price_call(rec)
        n = (pc or {}).get("output", {}).get("travelers")
        return n == p["n"], f"priced for {n}"
    if chk == "car_included":
        has = bool((pkg.get("refs") or {}).get("car"))
        return has == p["wanted"], f"car={has}"
    if chk == "near_cheapest":
        return pkg["total"] <= p["cheapest_total"] * (1 + p["tolerance"]) + 1e-9, f"total {pkg['total']} vs cheapest {p['cheapest_total']}"
    if chk == "flag_unsupported":
        return False, "can only be met by flagging"
    raise ValueError(f"unknown checker {chk}")


def _flag_texts(rec) -> list[str]:
    req = rec.get("request") or {}
    return [t.lower() for t in (rec.get("tradeoffs") or []) + [rec.get("message") or ""]] + \
        [("not handled: " + u).lower() for u in req.get("unparsed_requirements") or []]


def flagged(rec, kr) -> bool:
    words = [w.lower() for w in (kr["params"].get("keywords") or FLAG_WORDS.get(kr["checker"], []))]
    for t in _flag_texts(rec):
        if any(m in t for m in NOT_HANDLED) and any(w in t for w in words):
            return True
    return False


def evaluate(rec: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    out = []
    for kr in case["gold"]["key_requirements"]:
        met, det = check(rec, kr, case["city"])
        fl = flagged(rec, kr)
        if kr["checker"] == "flag_unsupported":
            outcome = "met" if fl else "ignored"
        else:
            outcome = "met" if met else ("flagged" if fl else "ignored")
        out.append(dict(id=kr["id"], checker=kr["checker"], outcome=outcome, detail=det))
    n = len(out)
    return dict(requirements=out, n=n, met=sum(o["outcome"] == "met" for o in out), flagged=sum(o["outcome"] == "flagged" for o in out),
                ignored=sum(o["outcome"] == "ignored" for o in out), score=round(sum(o["outcome"] == "met" for o in out) / n, 4) if n else None)
