"""System A, strong rules baseline (default `--system rules`). No LLM, no replan, fully deterministic.

Same shared Flow steps as every system (intake -> weather -> exhaustive package enumeration); differs from the basic
rules baseline (`--system rules_basic`, rules.py) in two places:

1. Package choice + conflict rule (falls out of the enumeration in pipeline.build_candidates, which already tags every
   package with the soft preferences it sacrifices and keeps the cheapest package of every Pareto-optimal profile):
   - no soft preferences          -> cheapest valid package (as basic);
   - some package satisfies all   -> the cheapest such package;
   - none does (a true conflict)  -> a Pareto-optimal package: fewest sacrificed preferences, then cheapest; the plan
     states the conflict and names what was given up, what was kept and the alternative profile(s) (template text).
2. Itinerary rules (built into the builder instead of being checked afterwards):
   - relevance: places scored by interest tags and the interest's core categories (config.INTEREST_CORE_CATEGORIES),
     notable places first by real signals only (in Wikivoyage AND has a Wikidata item); every interest with a
     notable core place gets one when it fits; distance only as a tie-breaker / travel-cost penalty;
   - opening hours: real OSM opening_hours when parseable, otherwise the category window (config.TYPE_HOURS:
     bars / pubs / nightlife evenings only, theatres from 12:00, museums 09-18, ...) - for meals too;
   - no two activities of the same category back to back (a meal in between resets);
   - full days are filled up to the pace's day load (check_day_load limits): when nothing fits now the builder waits
     (15-min steps) for the next place to open instead of ending the day;
   - RAIN days: indoor places only (an extra indoor-only search widens the pool); HEAT: outdoor only early / late.
Ratings / review counts / price levels are synthetic and never used.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Optional

from .. import config as C
from .. import prefs as P
from .. import tools as T
from ..data_access import is_open
from ..models import DayPlan, Dropped, Item, Status, effective_request
from ..pipeline import StepOutcome, day_windows, travel_mode
from ..timeutil import hm_to_min, iso_local_hm, min_to_hm
from .base import Decision, RunContext, package_from_candidate, run_checks
from .rules import DINNER_LATEST_START, LUNCH_LATEST_START, ground_travel, weather_note

POOL_LIMIT = 60          # search_places limit per interest (wikivoyage first, then distance)
WAIT_STEP_MIN = 15       # when nothing fits now, wait this long and retry
KM_PENALTY = 0.3         # score points per km of the leg from the current location


# ----------------------------------------------------------------- package choice + conflict rule
def choose_package(ctx: RunContext) -> tuple[dict[str, Any], dict[str, Any]]:
    """-> (candidate, info). info: conflict (bool|None), front (list of profiles), alternatives."""
    req, cands = ctx.req, ctx.candidates
    if not req.soft_prefs or any("sacrificed_prefs" not in c for c in cands):
        return cands[0], dict(conflict=None)
    sac = lambda c: tuple(c["sacrificed_prefs"])          # noqa: E731
    front = P.pareto_front(sac(c) for c in cands)
    on_front = [c for c in cands if sac(c) in front]
    best = min(on_front, key=lambda c: (len(sac(c)), c["total"], c["refs"]["flight_out"], c["refs"]["stay"]))
    alts = []
    for v in front:
        if v == sac(best):
            continue
        alts.append(min((c for c in on_front if sac(c) == v), key=lambda c: c["total"]))
    return best, dict(conflict=bool(sac(best)), front=[list(v) for v in front], alternatives=alts)


def _pref_phrase(p: str, cand: dict[str, Any], req, rain_days: list[str]) -> str:
    fo, fb = cand["flight_out"], cand["flight_back"]
    if p == "central":
        return f"a central location (lodging {cand['km_to_center']:.1f} km from the center; central radius {C.CENTRAL_RADIUS_KM[req.city]:.0f} km)"
    if p == "nonstop":
        return f"nonstop flights (this itinerary has {cand['stops']} connection(s))"
    if p == "exact_dates":
        return (f"the exact dates (trip shifted to {cand.get('start_date', fo['date'])}..{cand.get('end_date', fb['date'])} "
                f"instead of {req.start_date}..{req.end_date}, within the date flex)")
    if p == "dry_days":
        return "dry days (rain forecast on " + (", ".join(rain_days) or "a trip day") + ")"
    if p == "long_days":
        return (f"long days in the city (arrival {iso_local_hm(fo['arr'])}, departure {iso_local_hm(fb['dep'])}; "
                f"wanted landing by {P.LONG_DAYS_ARRIVE_BY} and take-off from {P.LONG_DAYS_DEPART_FROM})")
    if p == "under_preferred_budget":
        return f"the preferred budget (${cand['total']:.2f} > preferred ${req.preferred_budget_usd:.0f})"
    return p


def conflict_text(ctx: RunContext, cand: dict[str, Any], info: dict[str, Any]) -> list[str]:
    req = ctx.req
    if info.get("conflict") is None:
        return []
    rain = P.rain_map(ctx.conditions)
    s0 = cand.get("start_date", req.start_date.isoformat())
    e0 = cand.get("end_date", req.end_date.isoformat())
    rain_days = sorted(d for d, v in rain.items() if v and s0 <= d < e0)     # trip days of this package, departure day excluded
    sac = cand["sacrificed_prefs"]
    n = cand.get("n_within_budget")
    if not info["conflict"]:
        return [f"all soft preferences satisfied ({', '.join(req.soft_prefs)}) by the cheapest such package (${cand['total']:.2f})"]
    kept = [p for p in req.soft_prefs if p not in sac]
    out = [f"Conflict detected: none of the {n} packages within the ${req.budget_usd} budget satisfies all soft preferences "
           f"({', '.join(req.soft_prefs)}).",
           "Trade-off: this plan gives up " + "; ".join(_pref_phrase(p, cand, req, rain_days) for p in sac)
           + (" and keeps " + ", ".join(kept) if kept else "") + f" - total ${cand['total']:.2f} (fewest sacrificed preferences, then cheapest)."]
    for a in info.get("alternatives", [])[:2]:
        out.append("Alternative (also Pareto-optimal): give up " + "; ".join(_pref_phrase(p, a, req, rain_days) for p in a["sacrificed_prefs"])
                   + f" - total ${a['total']:.2f}.")
    return out


# ----------------------------------------------------------------- place pool + scoring
def _core(p: dict[str, Any], interests: list[str]) -> set[str]:
    return {t for t in interests if t in p["tags"] and p["category"] in C.INTEREST_CORE_CATEGORIES.get(t, ())}


def _notable(p: dict[str, Any]) -> bool:
    return bool(p.get("in_wikivoyage")) and bool(p.get("has_wikidata"))


def value(p: dict[str, Any], interests: list[str]) -> float:
    """Interest relevance + notability from real signals (Wikivoyage / Wikidata presence). No ratings."""
    core = _core(p, interests)
    return (1.5 * len(core) + len(set(p["tags"]) & set(interests)) + (2.0 * len(core) + 1.0 if _notable(p) else 0.0)
            + (0.5 if p.get("in_wikivoyage") else 0.0))


def gather_places(ctx: RunContext, stay: dict[str, Any], rainy: bool) -> dict[str, dict[str, Any]]:
    req, log = ctx.req, ctx.log
    pool: dict[str, dict[str, Any]] = {}
    searches = [([t], False) for t in req.interests] + ([(list(req.interests), True)] if rainy else [])
    for tags, indoor in searches:
        out = T.search_places(log, req.city, tags, indoor_only=indoor, near=(stay["lat"], stay["lon"]), limit=POOL_LIMIT,
                              exclude_tags=req.avoid)
        if out.get("status") == "NEEDS_DATA":
            raise StepOutcome(Status.NEEDS_DATA, out["error"])
        for p in out["places"]:
            pool.setdefault(p["place_id"], p)
    return pool


def plausible(p: dict[str, Any], spec: str, date, start: int, end: int) -> bool:
    """Real opening_hours when parseable; else the category window (TYPE_HOURS); unknown category -> allowed."""
    ok = is_open(spec, date, start, end) if spec and spec != "unknown" else None
    if ok is None:
        w = C.TYPE_HOURS.get(p["category"])
        ok = True if w is None else (hm_to_min(w[0]) <= start and end <= hm_to_min(w[1]))
    return ok


# ----------------------------------------------------------------- itinerary builder
def build_days(ctx: RunContext, stay_ref: str, windows: dict[str, tuple[str, str]], pool: dict[str, dict[str, Any]]):
    req, log = ctx.req, ctx.log
    interests = list(req.interests)
    mode = travel_mode(req)
    cond = {c.date: c for c in ctx.conditions}
    stay_pt = T.resolve_point(stay_ref)
    use_meals = "food" in interests
    acts = [p for p in pool.values() if p["category"] not in C.MEAL_CATEGORIES]
    meals = [p for p in pool.values() if p["category"] in C.MEAL_CATEGORIES] if use_meals else []
    val = {p["place_id"]: value(p, interests) for p in pool.values()}
    pts = {p["place_id"]: (p["lat"], p["lon"]) for p in pool.values()}
    hours: dict[str, str] = {}

    def spec(p):
        if p["place_id"] not in hours:
            d = T.get_place_details(log, p["place_id"], req.city)
            hours[p["place_id"]] = d.get("opening_hours", "unknown")
        return hours[p["place_id"]]

    # one notable core place per interest = the "must-have" set (best value, then nearest to the lodging)
    must: dict[str, dict[str, Any]] = {}
    for t in interests:
        opts = [p for p in acts if t in _core(p, interests) and _notable(p)]
        if opts:
            must[t] = min(opts, key=lambda p: (-val[p["place_id"]], p.get("km_from_near", 0.0), p["place_id"]))
    remaining = sorted(acts, key=lambda p: (-val[p["place_id"]], p.get("km_from_near", 0.0), p["place_id"]))
    meals_left = sorted(meals, key=lambda p: (-val[p["place_id"]], p.get("km_from_near", 0.0), p["place_id"]))
    covered: set[str] = set()          # interests covered by any scheduled place (coverage check)
    relevant: set[str] = set()         # interests that got a notable core place (relevance)
    weather_blocked: set[str] = set()
    days: list[DayPlan] = []
    for d in req.days:
        ds = d.isoformat()
        w0, w1 = (hm_to_min(x) for x in windows[ds])
        c = cond.get(ds)
        flags = list(c.flags) if c else []
        edge = d in (req.start_date, req.end_date)
        items: list[dict[str, Any]] = []
        t, loc, loc_pt, last_cat = w0, stay_ref, stay_pt, None
        lunch_done = dinner_done = not meals_left

        def try_place(p, kind):
            leg = T.leg_estimate(loc_pt, pts[p["place_id"]], mode)
            start = t + leg["minutes"]
            if kind == "meal":
                lo, hi = (hm_to_min(C.LUNCH_WINDOW[0]), LUNCH_LATEST_START) if not lunch_done else \
                    (hm_to_min(C.DINNER_WINDOW[0]), DINNER_LATEST_START)
                start = max(start, lo)
                if start > hi:
                    return None, "NO_SLOT"
                dur = C.MEAL_MINUTES
            else:
                dur = p["typical_visit_minutes"]
                if p["category"] == last_cat:
                    return None, "SAME_KIND"
            end = start + dur
            if end > w1:
                return None, "NO_SLOT"
            outdoor = p["indoor"] != "true"
            if outdoor and "RAIN" in flags:
                return None, "WEATHER"
            if outdoor and "HEAT" in flags and not (end <= hm_to_min(C.HEAT_OUTDOOR_BEFORE) or start >= hm_to_min(C.HEAT_OUTDOOR_FROM)):
                return None, "HEAT"
            if kind == "activity" and meals_left:
                if not lunch_done and start < LUNCH_LATEST_START < end:
                    return None, "MEAL_CONFLICT"
                if not dinner_done and start < DINNER_LATEST_START < end:
                    return None, "MEAL_CONFLICT"
            if not plausible(p, spec(p), d, start, end):
                return None, "CLOSED"
            it = dict(place_id=p["place_id"], name=p["name"], kind=kind, start=min_to_hm(start), end=min_to_hm(end),
                      mode=leg["mode"], travel_min=leg["minutes"], from_id=loc)
            v, _ = T.day_load_violations(items + [it], req.pace, edge)
            if v:
                return None, "DAY_LOAD"
            return it, None

        def prio(p):
            core = _core(p, interests)
            bonus = (6.0 if _notable(p) and core - relevant else 0.0) + (4.0 if (set(p["tags"]) & set(interests)) - covered else 0.0)
            km = T.leg_estimate(loc_pt, pts[p["place_id"]], mode)["km"]
            return (-(val[p["place_id"]] + bonus - KM_PENALTY * km), p["place_id"])

        guard = 0
        while t < w1 and guard < 200:
            guard += 1
            placed = None
            if meals_left and ((not lunch_done and t >= hm_to_min(C.LUNCH_WINDOW[0]) - 30) or
                               (lunch_done and not dinner_done and t >= hm_to_min(C.DINNER_WINDOW[0]) - 30)):
                for p in sorted(meals_left, key=lambda p: (T.leg_estimate(loc_pt, pts[p["place_id"]], mode)["km"] - 0.5 * val[p["place_id"]], p["place_id"])):
                    it, _ = try_place(p, "meal")
                    if it:
                        placed = (p, it)
                        break
                if not lunch_done:
                    lunch_done = True
                else:
                    dinner_done = True
                if placed:
                    meals_left.remove(placed[0])
                    last_cat = None
            else:
                for p in sorted(remaining, key=prio):
                    it, why = try_place(p, "activity")
                    if it:
                        placed = (p, it)
                        break
                    if why == "WEATHER":
                        weather_blocked.add(p["place_id"])
                if placed:
                    remaining.remove(placed[0])
                    last_cat = placed[0]["category"]
                else:
                    t += WAIT_STEP_MIN          # nothing fits now: wait for the next opening / meal window
                    continue
            if not placed:
                continue
            p, it = placed
            items.append(it)
            covered |= set(p["tags"]) & set(interests)
            relevant |= _core(p, interests) if _notable(p) else set()
            t, loc, loc_pt = hm_to_min(it["end"]), p["place_id"], pts[p["place_id"]]
        days.append(DayPlan(date=ds, flags=flags, window=windows[ds],
                            items=[Item(**it, travel_call_id="", weather_note=weather_note(c)) for it in items]))
    rain_trip = any("RAIN" in (c.flags if c else []) for c in (cond.get(d.isoformat()) for d in req.days))
    dropped = [Dropped(place_id=p["place_id"], reason="WEATHER" if (p["place_id"] in weather_blocked and rain_trip) else "NO_SLOT")
               for t_, p in must.items() if t_ not in relevant and p in remaining]
    return days, dropped, covered, relevant, must


def decide_rules_strong(ctx: RunContext) -> Decision:
    cand, info = choose_package(ctx)
    pkg = package_from_candidate(cand)
    req = effective_request(ctx.req, pkg)
    sctx = dataclasses.replace(ctx, req=req) if req is not ctx.req else ctx
    windows = day_windows(req, cand["flight_out"], cand["flight_back"])
    rainy = any("RAIN" in c.flags for c in ctx.conditions if c.date in {d.isoformat() for d in req.days})
    pool = gather_places(sctx, cand["stay"], rainy)
    days, dropped, covered, relevant, must = build_days(sctx, cand["refs"]["stay"], windows, pool)
    ground_travel(sctx, days)
    report = run_checks(ctx, pkg, days, dropped)
    tradeoffs = conflict_text(ctx, cand, info)
    if info.get("conflict") is None:
        tradeoffs.append(f"cheapest valid package chosen (${pkg.total:.2f} of ${req.budget_usd})")
    missing = [t for t in req.interests if t not in covered]
    if missing:
        tradeoffs.append("not covered: " + ", ".join(missing))
    no_notable = [t for t in must if t not in relevant]
    if no_notable:
        tradeoffs.append("no notable place fitted for: " + ", ".join(no_notable))
    if dropped:
        tradeoffs.append(f"{len(dropped)} must-see place(s) not scheduled (" + ", ".join(sorted({x.reason for x in dropped})) + ")")
    status = Status.OK_PLAN if report.all_passed else Status.CONFLICT_UNRESOLVED
    msg = "" if report.all_passed else "failed checks: " + ", ".join(report.failures)
    return Decision(status=status, package=pkg, days=days, dropped=dropped, tradeoffs=tradeoffs, check_report=report,
                    rounds_used=1, message=msg)
