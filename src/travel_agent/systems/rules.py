"""System A - deterministic rules baseline (spec section 2). No LLM, no replan."""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Optional

from .. import config as C
from .. import tools as T
from ..data_access import is_open
from ..models import DayPlan, Dropped, Item, Status, effective_request
from ..pipeline import StepOutcome, day_windows, travel_mode
from ..timeutil import hm_to_min, min_to_hm
from .base import Decision, RunContext, package_from_candidate, run_checks

LUNCH_LATEST_START = hm_to_min(C.LUNCH_WINDOW[1]) - C.MEAL_MINUTES     # 13:30
DINNER_LATEST_START = hm_to_min(C.DINNER_WINDOW[1]) - C.MEAL_MINUTES   # 19:00


def weather_note(cond) -> Optional[str]:
    if cond is None or "OUT_OF_HORIZON" in cond.flags or "UNAVAILABLE" in cond.flags:
        return None
    parts = []
    if "RAIN" in cond.flags:
        parts.append(f"RAIN forecast ({cond.precip_mm} mm, {cond.precip_h} h) - indoor only")
    if "HEAT" in cond.flags:
        parts.append(f"HEAT (feels like {cond.apparent_max}°C) - outdoor only before 11:00 / from 17:00")
    if "WIND" in cond.flags:
        parts.append(f"WIND gusts {cond.gust_max} km/h")
    if not parts:
        parts.append("no weather flag")
    return "; ".join(parts) + f" [source: {cond.source}]"


def select_places(ctx: RunContext, stay: dict[str, Any], n_act: int, n_meal: int):
    """Score = |tags ∩ interests|; avoid-tagged places excluded; every interest gets >= 1 place (round-robin);
    then by score, in_wikivoyage, distance from the lodging. Ratings are synthetic and never used."""
    req, log = ctx.req, ctx.log
    pool: dict[str, dict[str, Any]] = {}
    for t in req.interests:
        out = T.search_places(log, req.city, [t], near=(stay["lat"], stay["lon"]), limit=40, exclude_tags=req.avoid)
        if out.get("status") == "NEEDS_DATA":
            raise StepOutcome(Status.NEEDS_DATA, out["error"])
        for p in out["places"]:
            pool.setdefault(p["place_id"], p)
    interests = set(req.interests)

    def score(p):
        return len(set(p["tags"]) & interests)

    def key(p):
        return (-score(p), 0 if p["in_wikivoyage"] else 1, p.get("km_from_near", 0.0), p["place_id"])

    meals = sorted([p for p in pool.values() if p["category"] in C.MEAL_CATEGORIES], key=key) if "food" in interests else []
    acts_all = sorted([p for p in pool.values() if p["category"] not in C.MEAL_CATEGORIES], key=key)
    chosen: list[dict[str, Any]] = []
    for t in req.interests:                       # round-robin: one per interest (food is covered by meals)
        if t == "food" and meals:
            continue
        p = next((p for p in acts_all if t in p["tags"] and p not in chosen), None)
        if p and len(chosen) < n_act:
            chosen.append(p)
    for p in acts_all:
        if len(chosen) >= n_act:
            break
        if p not in chosen:
            chosen.append(p)
    meals = meals[:n_meal]
    details = {}
    for p in chosen + meals:
        d = T.get_place_details(log, p["place_id"], req.city)
        details[p["place_id"]] = d.get("opening_hours", "unknown")
    return chosen, meals, details


def schedule(ctx: RunContext, stay_ref: str, windows: dict[str, tuple[str, str]], acts: list[dict[str, Any]],
             meals: list[dict[str, Any]], hours: dict[str, str]):
    """Greedy nearest-neighbour per day, preferring places that cover a not-yet-covered interest.
    Items enter only if check_day_load passes and opening hours fit (when known). RAIN: indoor only
    (unknown = outdoor) - outdoor places move to the next dry day or are dropped (WEATHER). HEAT: outdoor
    only before 11:00 or from 17:00. WIND: flag only."""
    req = ctx.req
    mode = travel_mode(req)
    cond = {c.date: c for c in ctx.conditions}
    remaining = list(acts)
    meals_left = list(meals)
    weather_blocked: set[str] = set()
    covered: set[str] = set()
    pts = {p["place_id"]: (p["lat"], p["lon"]) for p in acts + meals}
    stay_pt = T.resolve_point(stay_ref)
    days: list[DayPlan] = []
    for d in req.days:
        ds = d.isoformat()
        w0, w1 = (hm_to_min(x) for x in windows[ds])
        c = cond.get(ds)
        flags = list(c.flags) if c else []
        edge = d in (req.start_date, req.end_date)
        items: list[dict[str, Any]] = []
        t, loc, loc_pt = w0, stay_ref, stay_pt
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
            end = start + dur
            if end > w1:
                return None, "NO_SLOT"
            outdoor = p["indoor"] != "true"
            if outdoor and "RAIN" in flags:
                return None, "WEATHER"
            if outdoor and "HEAT" in flags and not (end <= hm_to_min(C.HEAT_OUTDOOR_BEFORE) or start >= hm_to_min(C.HEAT_OUTDOOR_FROM)):
                return None, "HEAT"
            if kind == "activity" and meals_left:
                if not lunch_done and start < LUNCH_LATEST_START < end and end > LUNCH_LATEST_START:
                    return None, "MEAL_CONFLICT"
                if not dinner_done and start < DINNER_LATEST_START < end:
                    return None, "MEAL_CONFLICT"
            if is_open(hours.get(p["place_id"], ""), d, start, end) is False:
                return None, "CLOSED"
            it = dict(place_id=p["place_id"], name=p["name"], kind=kind, start=min_to_hm(start), end=min_to_hm(end),
                      mode=leg["mode"], travel_min=leg["minutes"], from_id=loc, tags=p["tags"])
            v, _ = T.day_load_violations(items + [it], req.pace, edge)
            if v:
                return None, "DAY_LOAD"
            return it, None

        guard = 0
        while guard < 50:
            guard += 1
            placed = None
            # meals at lunch / dinner time
            if meals_left and ((not lunch_done and t >= hm_to_min(C.LUNCH_WINDOW[0]) - 30) or
                               (lunch_done and not dinner_done and t >= hm_to_min(C.DINNER_WINDOW[0]) - 30)):
                for p in sorted(meals_left, key=lambda p: (T.leg_estimate(loc_pt, pts[p["place_id"]], mode)["km"], p["place_id"])):
                    it, why = try_place(p, "meal")
                    if it:
                        placed = (p, it)
                        break
                if placed:
                    meals_left.remove(placed[0])
                else:
                    pass
                if not lunch_done:
                    lunch_done = True
                else:
                    dinner_done = True
                if not placed:
                    continue
            else:
                order = sorted(remaining, key=lambda p: (0 if (set(p["tags"]) & set(req.interests)) - covered else 1,
                                                         T.leg_estimate(loc_pt, pts[p["place_id"]], mode)["km"], p["place_id"]))
                for p in order:
                    it, why = try_place(p, "activity")
                    if it:
                        placed = (p, it)
                        break
                    if why == "WEATHER":
                        weather_blocked.add(p["place_id"])
                if placed:
                    remaining.remove(placed[0])
                else:
                    # nothing fits now: jump to the next meal window, else end the day
                    if meals_left and not lunch_done and t < hm_to_min(C.LUNCH_WINDOW[0]):
                        t = hm_to_min(C.LUNCH_WINDOW[0]) - 30
                        continue
                    if meals_left and not lunch_done:
                        lunch_done = True
                        continue
                    if meals_left and not dinner_done and t < hm_to_min(C.DINNER_WINDOW[0]):
                        t = hm_to_min(C.DINNER_WINDOW[0]) - 30
                        continue
                    if meals_left and not dinner_done:
                        dinner_done = True
                        continue
                    break
            p, it = placed
            items.append(it)
            covered |= set(p["tags"]) & set(req.interests)
            t, loc, loc_pt = hm_to_min(it["end"]), p["place_id"], pts[p["place_id"]]
        days.append(DayPlan(date=ds, flags=flags, window=windows[ds],
                            items=[Item(**{k: v for k, v in it.items() if k != "tags"}, travel_call_id="",
                                        weather_note=weather_note(c)) for it in items]))
    dropped = [Dropped(place_id=p["place_id"], reason="WEATHER" if p["place_id"] in weather_blocked else "NO_SLOT")
               for p in remaining]
    return days, dropped


def ground_travel(ctx: RunContext, days: list[DayPlan]) -> None:
    """One get_travel_time batch per day and one check_day_load per day (logged); travel_min comes from the tool."""
    req = ctx.req
    for d in days:
        if not d.items:
            continue
        out = T.get_travel_time(ctx.log, [(it.from_id, it.place_id) for it in d.items], travel_mode(req))
        for it, leg in zip(d.items, out["legs"]):
            it.travel_min, it.mode, it.travel_call_id = leg["minutes"], leg["mode"], out["call_id"]
        T.check_day_load(ctx.log, [it.model_dump() for it in d.items], req.pace,
                         d.date in (req.start_date.isoformat(), req.end_date.isoformat()))


def slots(ctx: RunContext, windows: dict[str, tuple[str, str]]) -> tuple[int, int]:
    req = ctx.req
    n_act = n_meal = 0
    for d in req.days:
        a, b = (hm_to_min(x) for x in windows[d.isoformat()])
        if b - a < 45:
            continue
        edge = d in (req.start_date, req.end_date)
        n_act += C.EDGE_DAY_MAX_ACTIVITIES if edge else C.DAY_LOAD[req.pace]["max_activities"]
        n_meal += C.MAX_MEALS_PER_DAY
    return n_act, n_meal


def decide_rules(ctx: RunContext) -> Decision:
    cand = ctx.candidates[0]                       # cheapest valid package (rank_packages order)
    pkg = package_from_candidate(cand)
    req = effective_request(ctx.req, pkg)          # with date flexibility: the dates of the chosen flights
    sctx = dataclasses.replace(ctx, req=req) if req is not ctx.req else ctx
    windows = day_windows(req, cand["flight_out"], cand["flight_back"])
    n_act, n_meal = slots(sctx, windows)
    acts, meals, hours = select_places(sctx, cand["stay"], n_act, n_meal)
    days, dropped = schedule(sctx, cand["refs"]["stay"], windows, acts, meals, hours)
    ground_travel(sctx, days)
    report = run_checks(ctx, pkg, days, dropped)
    tradeoffs = []
    covered = set()
    for d in days:
        for it in d.items:
            covered |= set(next((p["tags"] for p in acts + meals if p["place_id"] == it.place_id), [])) & set(req.interests)
    missing = [t for t in req.interests if t not in covered]
    if missing:
        tradeoffs.append("not covered: " + ", ".join(missing))
    if dropped:
        tradeoffs.append(f"{len(dropped)} selected place(s) not scheduled (" +
                         ", ".join(sorted({x.reason for x in dropped})) + ")")
    tradeoffs.append(f"cheapest valid package chosen (${pkg.total:.2f} of ${req.budget_usd}); rules do not trade price for location")
    status = Status.OK_PLAN if report.all_passed else Status.CONFLICT_UNRESOLVED
    msg = "" if report.all_passed else "failed checks: " + ", ".join(report.failures)
    return Decision(status=status, package=pkg, days=days, dropped=dropped, tradeoffs=tradeoffs, check_report=report,
                    rounds_used=1, message=msg)
