"""Soft preferences (eval v2): evaluated per package, identical for the oracle (eval/cases/build_eval_cases_v2.py),
the shared candidate step and the scorer. Hard constraints (budget, dates within flex, capacity, car, ...) stay in
final_checks; a soft preference may be sacrificed, but a good plan should only sacrifice what it must and say so.

Preferences (all booleans; None = cannot be evaluated, e.g. no forecast):
  central                 lodging within the city's central radius (CENTRAL_RADIUS_KM)
  nonstop                 both flights nonstop
  exact_dates             outbound / return on the requested dates (only meaningful with depart/return flex)
  dry_days                no RAIN flag on any trip day except the departure day (needs a forecast, lead <= 7)
  long_days               land by LONG_DAYS_ARRIVE_BY and take off from LONG_DAYS_DEPART_FROM (local) - more usable
                          time on arrival / departure day for the interests at the requested pace
  under_preferred_budget  total <= preferred_budget_usd (a softer target below the hard budget)
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Optional

from . import config as C
from .timeutil import hm_to_min, iso_local_hm

SOFT_PREFS = ["central", "nonstop", "exact_dates", "dry_days", "long_days", "under_preferred_budget"]
LONG_DAYS_ARRIVE_BY = "13:00"
LONG_DAYS_DEPART_FROM = "16:00"

# words that show a preference was named in an explanation (tradeoffs / message); used by eval/score.py
PREF_KEYWORDS = {
    "central": ["central", "center", "centre", "downtown", "km from", "location", "far from"],
    "nonstop": ["nonstop", "non-stop", "connection", "connecting", "layover", "stop"],
    "exact_dates": ["date", "day earlier", "day later", "shift", "flex"],
    "dry_days": ["rain", "weather", "dry", "forecast"],
    "long_days": ["arriv", "depart", "early flight", "late flight", "time in the city", "time in city", "landing", "take-off", "takeoff"],
    "under_preferred_budget": ["preferred budget", "target budget", "spend", "over the preferred", "under the preferred", "budget"],
}


def _nonstop(f: dict[str, Any]) -> bool:
    if "nonstop" in f:
        return bool(f["nonstop"])
    return int(f.get("stops", 1)) == 0


def _arr(f: dict[str, Any]) -> str:
    return f.get("arr") or f.get("arrival")


def _dep(f: dict[str, Any]) -> str:
    return f.get("dep") or f.get("departure")


def evaluate(prefs: Iterable[str], *, city: str, req_start: str, req_end: str, flight_out: dict[str, Any],
             flight_back: dict[str, Any], stay_km: float, total: float, preferred_budget: Optional[float] = None,
             rain_by_date: Optional[dict[str, Optional[bool]]] = None) -> dict[str, Optional[bool]]:
    """rain_by_date: date -> True (RAIN) / False (dry) / None (no forecast)."""
    out: dict[str, Optional[bool]] = {}
    start, end = flight_out["date"], flight_back["date"]
    for p in prefs:
        if p == "central":
            out[p] = stay_km <= C.CENTRAL_RADIUS_KM[city]
        elif p == "nonstop":
            out[p] = _nonstop(flight_out) and _nonstop(flight_back)
        elif p == "exact_dates":
            out[p] = start == req_start and end == req_end
        elif p == "dry_days":
            days = [(dt.date.fromisoformat(start) + dt.timedelta(i)).isoformat()
                    for i in range((dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days)]   # departure day excluded
            vals = [(rain_by_date or {}).get(d) for d in days]
            out[p] = None if any(v is None for v in vals) else not any(vals)
        elif p == "long_days":
            out[p] = hm_to_min(iso_local_hm(_arr(flight_out))) <= hm_to_min(LONG_DAYS_ARRIVE_BY) and \
                hm_to_min(iso_local_hm(_dep(flight_back))) >= hm_to_min(LONG_DAYS_DEPART_FROM)
        elif p == "under_preferred_budget":
            out[p] = None if preferred_budget is None else total <= preferred_budget + 1e-9
        else:
            raise ValueError(f"unknown soft preference {p}")
    return out


def rain_map(conditions: Iterable[Any]) -> dict[str, Optional[bool]]:
    """DayCondition objects or dicts -> date -> RAIN? (None when out of horizon / unavailable)."""
    m: dict[str, Optional[bool]] = {}
    for c in conditions:
        d = c if isinstance(c, dict) else c.model_dump()
        fl = d.get("flags") or []
        m[d["date"]] = None if ("OUT_OF_HORIZON" in fl or "UNAVAILABLE" in fl) else ("RAIN" in fl)
    return m


def sacrificed(vec: dict[str, Optional[bool]]) -> tuple[str, ...]:
    return tuple(sorted(p for p, v in vec.items() if v is False))


def pareto_front(vectors: Iterable[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """vectors = sacrificed-preference sets; a set dominates another if it is a strict subset."""
    vs = sorted(set(vectors), key=lambda s: (len(s), s))
    return [v for v in vs if not any(set(w) < set(v) for w in vs)]


def satisfaction(vec: dict[str, Optional[bool]]) -> Optional[float]:
    vals = [v for v in vec.values() if v is not None]
    return (sum(vals) / len(vals)) if vals else None
