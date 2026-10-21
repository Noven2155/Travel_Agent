import pytest

from travel_agent.models import TripRequest
from travel_agent.systems import run


@pytest.mark.parametrize("cid", ["A01", "A05", "B01", "B03", "B05", "C01", "D01", "D02", "E01", "E02", "V05"])
def test_rules_status_matches_expected(cases, cid):
    c = cases[cid]
    r = run("rules", TripRequest.from_case(c))
    assert r.status.value == c["expected_status"], r.message
    assert r.llm_calls == 0 and r.tokens_in == 0
    if r.status.value == "OK_PLAN":
        assert r.all_checks_passed
        assert abs(r.package.total - c["oracle_package"]["cheapest_total"]) < 0.01   # A = cheapest valid package
        assert r.package.total <= c["budget_usd"]
        assert sum(len(d.items) for d in r.days) > 0
    else:
        assert not r.days


def test_nyc_without_places_is_needs_data(cases, monkeypatch, tmp_path):
    import shutil

    from travel_agent import config as C
    for p in C.PLACES_DIR.glob("*.csv"):
        if not p.name.startswith("nyc"):
            shutil.copy(p, tmp_path / p.name)
    monkeypatch.setattr(C, "PLACES_DIR", tmp_path)
    r = run("rules", TripRequest.from_case(cases["A08"]))
    assert r.status.value == "NEEDS_DATA" and "places data" in r.message


def test_invalid_request():
    r = run("rules", dict(request_id="X", city="Chicago", origin="LGA", start_date="2022-10-26", end_date="2022-10-25",
                          travelers=1, budget_usd=500, wants_car=False, interests=["food"], as_of="2022-10-01"))
    assert r.status.value == "INVALID_REQUEST"
    r = run("rules", dict(request_id="X", city="Chicago", origin="ORD", start_date="2022-10-26", end_date="2022-10-28",
                          travelers=1, budget_usd=500, wants_car=False, interests=["food"], as_of="2022-10-01"))
    assert r.status.value == "INVALID_REQUEST"
