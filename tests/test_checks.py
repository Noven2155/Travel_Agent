import copy

import pytest

from travel_agent.checks import final_checks
from travel_agent.models import Dropped, Item, TripRequest
from travel_agent.systems import run


def _rerun_checks(res, days=None, package=None, dropped=None):
    from travel_agent.tool_log import ToolLog
    log = ToolLog(res.run_id)
    log.entries = copy.deepcopy(res.tool_log)
    return final_checks(log, res.request, package or res.package, days if days is not None else res.days,
                        dropped if dropped is not None else res.dropped, res.day_conditions)


@pytest.fixture(scope="module")
def a01(cases):
    r = run("rules", TripRequest.from_case(cases["A01"]))
    assert r.status.value == "OK_PLAN"
    return r


def _first_item(res):
    for d in res.days:
        if d.items:
            return d, d.items[0]
    raise AssertionError("no items")


def test_untouched_plan_passes(a01):
    assert _rerun_checks(a01).all_passed


def test_budget_detects_wrong_total(a01):
    pkg = a01.package.model_copy(update=dict(total=a01.package.total - 1))
    rep = _rerun_checks(a01, package=pkg)
    assert "budget" in rep.failures


def test_budget_detects_over_budget(a01):
    req = a01.request.model_copy(update=dict(budget_usd=int(a01.package.total) - 5))
    from travel_agent.tool_log import ToolLog
    log = ToolLog("x")
    log.entries = copy.deepcopy(a01.tool_log)
    rep = final_checks(log, req, a01.package, a01.days, a01.dropped, a01.day_conditions)
    assert "budget" in rep.failures


def test_travel_detects_changed_minutes(a01):
    days = copy.deepcopy(a01.days)
    d, it = _first_item(type("R", (), {"days": days})())
    it.travel_min += 3
    assert "travel" in _rerun_checks(a01, days=days).failures


def test_grounding_detects_invented_place(a01):
    days = copy.deepcopy(a01.days)
    d, it = _first_item(type("R", (), {"days": days})())
    d.items.append(Item(place_id="osm:node/123456789", name="Invented", start="19:00", end="19:30", mode="walk",
                        travel_min=0, travel_call_id=it.travel_call_id, from_id=it.place_id))
    rep = _rerun_checks(a01, days=days)
    assert "grounding" in rep.failures


def test_grounding_rejects_synthetic_rating(a01):
    pkg = a01.package.model_copy(update=dict(stay=dict(a01.package.stay, rating=4.9)))
    assert "grounding" in _rerun_checks(a01, package=pkg).failures


def test_car_rule_drive_without_car(a01):
    days = copy.deepcopy(a01.days)
    for d in days:
        for it in d.items:
            if it.mode == "transit":
                it.mode = "drive"
                break
    rep = _rerun_checks(a01, days=days)
    assert "car" in rep.failures


def test_day_load_detects_overload(a01):
    days = copy.deepcopy(a01.days)
    full = days[1]
    base = full.items[0]
    full.items = [base.model_copy(update=dict(kind="activity")) for _ in range(6)]
    assert "day_load" in _rerun_checks(a01, days=days).failures


def test_coverage_and_avoid(cases):
    r = run("rules", TripRequest.from_case(cases["A05"]))     # avoid nightlife
    assert r.status.value == "OK_PLAN"
    req = r.request.model_copy(update=dict(avoid=[]))
    # pretend the user avoided a tag that the plan uses -> coverage check must fail
    used = set()
    for e in r.tool_log:
        if e["tool"] == "search_places":
            for p in e["output"]["places"]:
                used |= set(p["tags"])
    from travel_agent.tool_log import ToolLog
    log = ToolLog("x")
    log.entries = copy.deepcopy(r.tool_log)
    rep = final_checks(log, req.model_copy(update=dict(interests=["family"], avoid=["attractions"])), r.package, r.days,
                       r.dropped, r.day_conditions)
    assert "coverage" in rep.failures


def test_weather_rule_rain_day_outdoor(cases):
    r = run("rules", TripRequest.from_case(cases["D01"]))     # 2 rain days
    assert r.status.value == "OK_PLAN"
    rain_day = next(d for d in r.days if "RAIN" in d.flags)
    # find an outdoor place returned by the tools and put it on the rain day
    outdoor = next(p for e in r.tool_log if e["tool"] == "search_places" for p in e["output"]["places"] if p["indoor"] != "true")
    days = copy.deepcopy(r.days)
    rd = next(d for d in days if d.date == rain_day.date)
    rd.items = [Item(place_id=outdoor["place_id"], name=outdoor["name"], start="12:00", end="12:30", mode="transit",
                     travel_min=0, travel_call_id="x", from_id=r.package.refs["stay"])]
    rep = _rerun_checks(r, days=days)
    assert "weather_rule" in rep.failures
    assert any(x.reason == "WEATHER" for x in r.dropped)


def test_weather_dropped_without_rain_is_flagged(a01):
    rep = _rerun_checks(a01, dropped=[Dropped(place_id="x", reason="WEATHER")])
    assert "weather_rule" in rep.failures
