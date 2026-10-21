import datetime as dt

from travel_agent import config as C
from travel_agent import tools as T
from travel_agent.data_access import get_catalog, is_open, parse_opening_hours
from travel_agent.tool_log import ToolLog

META = {"call_id", "source", "license", "data_date"}


def test_every_tool_returns_meta_and_is_logged():
    log = ToolLog("t")
    outs = [
        T.search_flights(log, "LGA", ["ORD"], "2022-10-26", 1, "out"),
        T.search_hotels(log, "Chicago", "2022-10-26", "2022-10-29", 1),
        T.search_cars(log, "ORD", "2022-10-26", "2022-10-29", 2),
        T.search_places(log, "Chicago", ["culture"], limit=3),
        T.get_travel_time(log, [["41.88,-87.63", "41.89,-87.62"]], "transit"),
        T.check_day_load(log, [], "normal"),
        T.get_forecast(log, "Chicago", ["2022-05-05"], "2022-05-03"),
    ]
    for o in outs:
        assert META <= set(o)
    assert [e["call_id"] for e in log.entries] == [o["call_id"] for o in outs]


def test_search_flights_filters_seats_and_same_day_arrival():
    log = ToolLog("t")
    out = T.search_flights(log, "LGA", ["ORD"], "2022-10-26", 1, "out")
    assert out["options"], "A01 outbound exists"
    for o in out["options"]:
        assert o["seats"] >= 1 and o["arrival_date"] == "2022-10-26" and o["destination"] == "ORD"
    cat = get_catalog()
    many = T.search_flights(log, "LGA", ["ORD"], "2022-10-26", 99, "out")
    assert many["n"] == 0
    assert all(f["seats"] > 0 for f in [cat.flight_by_ref[o["ref"]] for o in out["options"]])


def test_search_hotels_central_radius_and_no_rating():
    log = ToolLog("t")
    anyh = T.search_hotels(log, "Chicago", "2022-11-02", "2022-11-05", 2)["options"]
    cen = T.search_hotels(log, "Chicago", "2022-11-02", "2022-11-05", 2, central=True)["options"]
    assert len(cen) <= len(anyh)
    assert all(h["km_to_center"] <= C.CENTRAL_RADIUS_KM["Chicago"] for h in cen)
    assert all(h["km_to_center"] <= C.MAX_STAY_KM for h in anyh)
    assert all("rating" not in h for h in anyh)


def test_search_cars_estimate_and_limit():
    log = ToolLog("t")
    ok = T.search_cars(log, "ORD", "2022-09-07", "2022-09-11", 2)
    assert ok["status"] == "OK" and ok["options"]
    assert all(c["capacity_basis"] == "estimate" and c["rental_days"] == 5 for c in ok["options"])
    over = T.search_cars(log, "ORD", "2022-09-07", "2022-09-11", 5)
    assert over["status"] == "NEEDS_DATA" and over["options"] == []


def test_calculate_price_formula():
    log = ToolLog("t")
    cat = get_catalog()
    car = cat.cars_by_airport["ORD"][0]
    refs = dict(flight_out="F8790", flight_back="F257", stay="CHICAGO:54167860", car="C" + car)
    out = T.calculate_price(log, refs, 2, 3)
    fo, fb, st, c = cat.flight_by_ref["F8790"], cat.flight_by_ref["F257"], cat.stays["CHICAGO:54167860"], cat.cars[car]
    expect = (fo["fare"] + fb["fare"]) * 2 + st["price"] * 3 + c["dailyRate"] * 4
    assert abs(out["total"] - round(expect, 2)) < 0.02
    assert out["fees_complete"] is False
    assert T.calculate_price(log, dict(refs, stay="nope"), 1, 1)["status"] == "INVALID_REF"


def test_travel_time_walk_threshold_and_parking():
    a, near, far = (41.88, -87.63), (41.884, -87.63), (41.95, -87.65)
    assert T.leg_estimate(a, near, "drive")["mode"] == "walk"
    d = T.leg_estimate(a, far, "drive")
    t = T.leg_estimate(a, far, "transit")
    assert d["mode"] == "drive" and t["mode"] == "transit"
    km = d["km"]
    assert d["minutes"] == -(-int(km * 1.3 / 25 * 60 * 1000 + 10 * 1000) // 1000) or abs(d["minutes"] - (km * 1.3 / 25 * 60 + 10)) < 1.01


def test_search_places_excludes_avoid_and_synthetic_fields():
    log = ToolLog("t")
    out = T.search_places(log, "Chicago", ["family", "attractions"], exclude_tags=["nightlife"], limit=30)
    assert out["places"]
    for p in out["places"]:
        assert "nightlife" not in p["tags"] and ({"family", "attractions"} & set(p["tags"]))
        assert not ({"rating", "review_count", "price_level"} & set(p))
        assert p["typical_visit_minutes_basis"] == "estimate"
    indoor = T.search_places(log, "Chicago", ["nature"], indoor_only=True, limit=50)
    assert all(p["indoor"] == "true" for p in indoor["places"])


def test_missing_city_places_is_needs_data(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "PLACES_DIR", tmp_path)
    out = T.search_places(ToolLog("t"), "New York", ["culture"])
    assert out["status"] == "NEEDS_DATA" and out["places"] == []


def test_place_details_and_opening_hours():
    log = ToolLog("t")
    p = T.search_places(log, "Chicago", ["culture"], limit=1)["places"][0]
    d = T.get_place_details(log, p["place_id"])
    assert d["status"] == "OK" and "opening_hours" in d
    assert T.get_place_details(log, "osm:node/0")["status"] == "NOT_FOUND"
    oh = parse_opening_hours("Mo-Fr 10:00-17:00; Sa 11:00-16:00; Su off")
    assert oh[0] == [(600, 1020)] and oh[6] == []
    monday, sunday = dt.date(2022, 10, 24), dt.date(2022, 10, 23)
    assert is_open("Mo-Fr 10:00-17:00", monday, 600, 700) is True
    assert is_open("Mo-Fr 10:00-17:00", sunday, 600, 700) is False
    assert is_open("", monday, 0, 10) is None and is_open("sunrise-sunset", monday, 0, 10) is None


def test_forecast_fixture_and_horizon():
    log = ToolLog("t")
    out = T.get_forecast(log, "Chicago", ["2022-05-05", "2022-05-06", "2022-05-20"], "2022-05-03")
    flags = {d["date"]: d["flags"] for d in out["days"]}
    assert "RAIN" in flags["2022-05-05"] and "RAIN" in flags["2022-05-06"]
    assert flags["2022-05-20"] == ["OUT_OF_HORIZON"]
    assert out["weather_status"] == "FORECAST"
    assert "CC BY 4.0" in out["license"]


def test_weather_fixtures_match_eval_expectations(cases):
    for c in cases.values():
        out = T.get_forecast(ToolLog("t"), c["city"], list(c["weather_expected"]), c["as_of"])
        got = {d["date"]: (d["flags"] or ["NONE"]) for d in out["days"]}
        assert got == c["weather_expected"], c["id"]


def test_day_load_thresholds():
    items = [dict(kind="activity", start="10:00", end="11:00", travel_min=10)] * 3
    assert T.day_load_violations(items, "normal")[0] == []
    assert T.day_load_violations(items, "relaxed")[0]
    assert T.day_load_violations(items[:2], "normal", edge_day=True)[0]
    meals = [dict(kind="meal", start="12:00", end="13:00", travel_min=0)] * 3
    assert any("meals" in v for v in T.day_load_violations(meals, "packed")[0])
