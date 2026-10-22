"""Deterministic tools over local files (spec 1.3). Identical for systems A, B and C.

Every tool takes the run's ToolLog as first argument, returns a JSON-serialisable dict that always contains
call_id, source, license and data_date, and records (args, output) in the log. Synthetic place fields
(rating, review_count, price_level) are never returned.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from . import config as C
from .data_access import clean_text, get_catalog, get_places, haversine_km, places_path
from .timeutil import hm_to_min, iso_local_hm
from .tool_log import ToolLog

CATALOG_SOURCE = "data/inventory.json (local catalog, 2022 dates)"


def _finish(log: ToolLog, tool: str, args: dict[str, Any], body: dict[str, Any], source: str, license: str,
            data_date: str) -> dict[str, Any]:
    call_id = log.new_call_id(tool)
    out = dict(call_id=call_id, source=source, license=license, data_date=data_date, **body)
    log.record(call_id, tool, args, out)
    return out


def _catalog_date() -> str:
    cat = get_catalog()
    return f"{cat.dates[0]}..{cat.dates[-1]}"


# ----------------------------------------------------------------- flights
def flight_option(f: dict[str, Any]) -> dict[str, Any]:
    return dict(ref=f["ref"], origin=f["origin"], destination=f["destination"], date=f["date"],
                arrival_date=f["arrivalDate"], dep=f["departure"], arr=f["arrival"], fare=f["fare"],
                stops=0 if f.get("nonstop") else 1, duration=f.get("duration", ""), seats=f["seats"],
                airline=f.get("airline"))


def search_flights(log: ToolLog, origin: str, airports: Sequence[str], date: str, min_seats: int,
                   direction: str = "out") -> dict[str, Any]:
    """direction='out': origin -> airport, departing and landing on `date`.
    direction='back': airport -> origin departing on `date`. seats==0 is unknown and filtered."""
    cat = get_catalog()
    opts = []
    for a in airports:
        recs = cat.flights_on(origin, a, date) if direction == "out" else cat.flights_on(a, origin, date)
        for f in recs:
            if f["seats"] <= 0 or f["seats"] < min_seats:
                continue
            if direction == "out" and f["arrivalDate"] != date:
                continue
            opts.append(flight_option(f))
    opts.sort(key=lambda o: (o["fare"], o["stops"], int(o["ref"][1:])))
    args = dict(origin=origin, airports=list(airports), date=date, min_seats=min_seats, direction=direction)
    return _finish(log, "search_flights", args, dict(options=opts, n=len(opts),
                   notes="fare is one-way per traveler; stops=1 means 'not nonstop' (catalog has only a nonstop flag)"),
                   CATALOG_SOURCE + " flights", C.LICENSES["catalog"], _catalog_date())


# ----------------------------------------------------------------- hotels
def stay_option(city: str, key: str, nights: int, ci: int) -> dict[str, Any]:
    cat = get_catalog()
    s = cat.stays[key]
    av, mn, mx = cat.decode(key)
    km = cat.stay_km_to_center(city, key)
    return dict(ref=key, title=clean_text(s.get("title", ""), 80), market=s["market"], price_per_night=s["price"],
                km_to_center=round(km, 2), lat=s["lat"], lon=s["lon"], capacity=s["capacity"],
                min_nights=mn[ci], max_nights=mx[ci], central=km <= C.CENTRAL_RADIUS_KM[city])


def search_hotels(log: ToolLog, city: str, check_in: str, check_out: str, guests: int,
                  central: bool = False) -> dict[str, Any]:
    """Hard filters: capacity >= guests; every night 'available' (decoded availabilityPacked);
    min_nights <= nights <= max_nights on check-in; <= 12 km from center; central -> radius per city."""
    cat = get_catalog()
    nights = (dt.date.fromisoformat(check_out) - dt.date.fromisoformat(check_in)).days
    opts = []
    if check_in in cat.date_index and nights > 0:
        ci = cat.date_index[check_in]
        for k in cat.city_stay_keys(city):
            s = cat.stays[k]
            if s.get("capacity") is None or s["capacity"] < guests:
                continue
            av, mn, mx = cat.decode(k)
            if not (mn[ci] > 0 and mx[ci] > 0 and mn[ci] <= nights <= mx[ci]):
                continue
            ok = True
            for j in range(nights):
                d = (dt.date.fromisoformat(check_in) + dt.timedelta(j)).isoformat()
                if d not in cat.date_index or av[cat.date_index[d]] != 2:
                    ok = False
                    break
            if not ok:
                continue
            km = cat.stay_km_to_center(city, k)
            if km > C.MAX_STAY_KM or (central and km > C.CENTRAL_RADIUS_KM[city]):
                continue
            opts.append(stay_option(city, k, nights, ci))
    opts.sort(key=lambda o: (o["price_per_night"], o["km_to_center"], o["ref"]))
    args = dict(city=city, check_in=check_in, check_out=check_out, guests=guests, central=central)
    return _finish(log, "search_hotels", args, dict(options=opts, n=len(opts), nights=nights,
                   central_radius_km=C.CENTRAL_RADIUS_KM[city], max_stay_km=C.MAX_STAY_KM,
                   notes="availability is synthetic (catalog); prices from Inside Airbnb Sep-2026 snapshots; rating not returned"),
                   CATALOG_SOURCE + " stays (Inside Airbnb)", C.LICENSES["catalog"], _catalog_date())


# ----------------------------------------------------------------- cars
def car_option(c: dict[str, Any], airport: str, rental_days: int) -> dict[str, Any]:
    return dict(ref="C" + c["id"], airport=airport, make=c.get("make", ""), model=c.get("model", ""),
                vehicle_type=c.get("type", ""), daily_rate=c["dailyRate"], rental_days=rental_days,
                estimated_capacity=c["capacityEstimate"], capacity_basis="estimate")


def search_cars(log: ToolLog, airport: str, start: str, end: str, travelers: int) -> dict[str, Any]:
    """Cars at `airport` with no blackout overlapping [start, end]. rental_days = nights + 1.
    Capacity is an ESTIMATE by vehicle type; MVP supports travelers <= 4, otherwise status NEEDS_DATA."""
    cat = get_catalog()
    rental_days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
    args = dict(airport=airport, start=start, end=end, travelers=travelers)
    if travelers > C.MAX_CAR_TRAVELERS:
        return _finish(log, "search_cars", args, dict(options=[], n=0, status="NEEDS_DATA",
                       reason=f"car requested for {travelers} travelers; capacity is only estimated, MVP limit is {C.MAX_CAR_TRAVELERS}"),
                       CATALOG_SOURCE + " cars", C.LICENSES["catalog"], _catalog_date())
    opts = []
    for cid in cat.cars_by_airport.get(airport, []):
        c = cat.cars[cid]
        if any(not (b[1] < start or b[0] > end) for b in c.get("blackouts", [])):
            continue
        if c["capacityEstimate"] < travelers:
            continue
        opts.append(car_option(c, airport, rental_days))
    opts.sort(key=lambda o: (o["daily_rate"], o["ref"]))
    return _finish(log, "search_cars", args, dict(options=opts, n=len(opts), status="OK",
                   notes="estimated_capacity is a heuristic by vehicle type (no verified seats); availability synthetic"),
                   CATALOG_SOURCE + " cars", C.LICENSES["catalog"], _catalog_date())


# ----------------------------------------------------------------- price / rank
def price_lines(refs: dict[str, Optional[str]], travelers: int, nights: int) -> dict[str, Any]:
    """Pure pricing (no logging). total = (fare_out + fare_back) x travelers + price x nights + dailyRate x (nights+1)."""
    cat = get_catalog()
    fo = cat.flight_by_ref[refs["flight_out"]]
    fb = cat.flight_by_ref[refs["flight_back"]]
    stay = cat.stays[refs["stay"]]
    lines = dict(flights=round((fo["fare"] + fb["fare"]) * travelers, 2), lodging=round(stay["price"] * nights, 2), car=0.0)
    rental_days = None
    if refs.get("car"):
        car = cat.cars[refs["car"].lstrip("C")]
        rental_days = nights + 1
        lines["car"] = round(car["dailyRate"] * rental_days, 2)
    total = round(lines["flights"] + lines["lodging"] + lines["car"], 2)
    return dict(lines=lines, total=total, rental_days=rental_days)


def calculate_price(log: ToolLog, refs: dict[str, Optional[str]], travelers: int, nights: int) -> dict[str, Any]:
    """The ONLY source of a package total (budget check compares against this call's output)."""
    args = dict(refs=dict(refs), travelers=travelers, nights=nights)
    try:
        p = price_lines(refs, travelers, nights)
    except KeyError as e:
        return _finish(log, "calculate_price", args, dict(error=f"unknown ref {e}", status="INVALID_REF"),
                       CATALOG_SOURCE, C.LICENSES["catalog"], _catalog_date())
    return _finish(log, "calculate_price", args, dict(refs=dict(refs), travelers=travelers, nights=nights, **p,
                   fees_complete=False, currency="USD"), CATALOG_SOURCE, C.LICENSES["catalog"], _catalog_date())


def rank_key(p: dict[str, Any]) -> tuple:
    r = p["refs"]
    return (p["total"], p["km_to_center"], p["stops"], r["flight_out"], r["flight_back"], r["stay"], r.get("car") or "")


def rank_packages(log: ToolLog, packages: list[dict[str, Any]], top_k: int = 5) -> dict[str, Any]:
    """Lexicographic order: price, lodging distance to center, total stops, refs. Returns the top_k."""
    ranked = sorted(packages, key=rank_key)
    args = dict(n_packages=len(packages), top_k=top_k)
    return _finish(log, "rank_packages", args, dict(ranked=ranked[:top_k], n_total=len(packages),
                   order="total, km_to_center, stops, ref"), "code (deterministic rule)", C.LICENSES["estimate"], _catalog_date())


# ----------------------------------------------------------------- places
def place_summary(r: dict[str, str]) -> dict[str, Any]:
    return dict(place_id=r["place_id"], name=clean_text(r["name"], 80), category=r["category"],
                tags=[t for t in r["tags"].split(";") if t], indoor=r["indoor"] if r["indoor"] in ("true", "false") else "unknown",
                lat=float(r["lat"]), lon=float(r["lon"]), neighborhood=clean_text(r.get("neighborhood", ""), 60),
                in_wikivoyage=r.get("in_wikivoyage") == "true", has_wikidata=bool(r.get("wikidata")), typical_visit_minutes=int(float(r["typical_visit_minutes"] or 60)),
                typical_visit_minutes_basis="estimate", source=r["source"], license=r["license"])


def _no_places(log: ToolLog, tool: str, args: dict[str, Any], city: str) -> dict[str, Any]:
    return _finish(log, tool, args, dict(status="NEEDS_DATA", places=[], n=0,
                   error=f"places data for {city} not available (data/places/{places_path(city).name} missing)"),
                   "data/places", C.LICENSES["places"], "")


def search_places(log: ToolLog, city: str, tags: Sequence[str], indoor_only: bool = False,
                  near: Optional[Sequence[float]] = None, limit: int = 30,
                  exclude_tags: Sequence[str] = ()) -> dict[str, Any]:
    """Places having at least one of `tags` and none of `exclude_tags`. Order: #matched tags desc,
    in_wikivoyage desc, distance to `near` asc, place_id. No rating / review_count (synthetic)."""
    args = dict(city=city, tags=list(tags), indoor_only=indoor_only, near=list(near) if near else None, limit=limit,
                exclude_tags=list(exclude_tags))
    db = get_places(city)
    if db is None:
        return _no_places(log, "search_places", args, city)
    want, excl = set(tags), set(exclude_tags)
    rows = []
    for r in db.rows:
        tg = set(db.tags(r))
        if want and not (tg & want):
            continue
        if tg & excl:
            continue
        if indoor_only and r["indoor"] != "true":
            continue
        d = haversine_km(near[0], near[1], float(r["lat"]), float(r["lon"])) if near else 0.0
        rows.append((-len(tg & want), 0 if r.get("in_wikivoyage") == "true" else 1, d, r["place_id"], r))
    rows.sort(key=lambda x: x[:4])
    places = []
    for x in rows[:limit]:
        ps = place_summary(x[4])
        if near:
            ps["km_from_near"] = round(x[2], 2)
        places.append(ps)
    return _finish(log, "search_places", args, dict(status="OK", places=places, n=len(places), n_matching=len(rows),
                   notes="typical_visit_minutes is an estimate (synthetic); ratings are synthetic and never returned"),
                   f"data/places/{C.CITIES[city]['key']}_places.csv (OpenStreetMap + Wikivoyage)", C.LICENSES["places"],
                   db.retrieved_at)


def get_place_details(log: ToolLog, place_id: str, city: Optional[str] = None) -> dict[str, Any]:
    args = dict(place_id=place_id)
    cities = [city] if city else list(C.CITIES)
    for c in cities:
        db = get_places(c)
        if db and place_id in db.by_id:
            r = db.by_id[place_id]
            body = dict(status="OK", place=place_summary(r), opening_hours=r.get("opening_hours") or "unknown",
                        website=r.get("website") or None, address=clean_text(r.get("address", ""), 120),
                        description_short=clean_text(r.get("description_short", ""), 200), source_url=r.get("source_url"))
            return _finish(log, "get_place_details", args, body, f"data/places/{C.CITIES[c]['key']}_places.csv",
                           r.get("license") or C.LICENSES["places"], r.get("retrieved_at", ""))
    return _finish(log, "get_place_details", args, dict(status="NOT_FOUND", error=f"unknown place_id {place_id}"),
                   "data/places", C.LICENSES["places"], "")


# ----------------------------------------------------------------- travel time
def resolve_point(pid: str) -> Optional[tuple[float, float]]:
    cat = get_catalog()
    if pid in cat.stays:
        s = cat.stays[pid]
        return float(s["lat"]), float(s["lon"])
    for c in C.CITIES:
        db = get_places(c)
        if db and pid in db.by_id:
            r = db.by_id[pid]
            return float(r["lat"]), float(r["lon"])
    if "," in pid:
        try:
            a, b = pid.split(",")
            return float(a), float(b)
        except ValueError:
            return None
    return None


def leg_estimate(a: tuple[float, float], b: tuple[float, float], mode: str) -> dict[str, Any]:
    km = haversine_km(a[0], a[1], b[0], b[1])
    m = "walk" if km <= C.WALK_MAX_KM else mode
    minutes = 0 if km < 1e-6 else int(math.ceil(km * C.DETOUR_FACTOR / C.SPEED_KMH[m] * 60 + C.OVERHEAD_MIN[m]))
    return dict(km=round(km, 3), mode=m, minutes=minutes)


def get_travel_time(log: ToolLog, pairs: Sequence[Sequence[str]], mode: str = "transit") -> dict[str, Any]:
    """Batch estimate for (from_id, to_id) pairs (place_id, stay ref or 'lat,lon').
    minutes = haversine x 1.3 / speed + overhead (drive: +10 min parking). Legs <= 1 km are walked."""
    if mode not in C.SPEED_KMH:
        mode = "transit"
    legs = []
    for p in pairs:
        a, b = resolve_point(p[0]), resolve_point(p[1])
        if a is None or b is None:
            legs.append(dict(from_id=p[0], to_id=p[1], error="unknown point"))
            continue
        legs.append(dict(from_id=p[0], to_id=p[1], **leg_estimate(a, b, mode)))
    args = dict(pairs=[list(p) for p in pairs], mode=mode)
    return _finish(log, "get_travel_time", args, dict(legs=legs, requested_mode=mode, method="estimate",
                   detour_factor=C.DETOUR_FACTOR, speeds_kmh=C.SPEED_KMH, overhead_min=C.OVERHEAD_MIN,
                   parking_overhead_min=C.OVERHEAD_MIN["drive"]), "code (haversine estimate)", C.LICENSES["estimate"],
                   dt.date.today().isoformat())


# ----------------------------------------------------------------- day load
def day_load_violations(items: Iterable[dict[str, Any]], pace: str, edge_day: bool = False) -> tuple[list[str], dict[str, Any]]:
    lim = C.DAY_LOAD[pace]
    items = list(items)
    n_act = sum(1 for i in items if i.get("kind", "activity") == "activity")
    n_meal = sum(1 for i in items if i.get("kind") == "meal")
    minutes = sum(hm_to_min(i["end"]) - hm_to_min(i["start"]) for i in items)
    travel = sum(int(i.get("travel_min") or 0) for i in items)
    max_act = min(lim["max_activities"], C.EDGE_DAY_MAX_ACTIVITIES) if edge_day else lim["max_activities"]
    v = []
    if n_act > max_act:
        v.append(f"activities {n_act} > {max_act}{' (arrival/departure day)' if edge_day else ''}")
    if minutes > lim["max_hours"] * 60:
        v.append(f"activity time {minutes / 60:.1f}h > {lim['max_hours']}h")
    if travel > lim["max_travel_min"]:
        v.append(f"travel {travel} min > {lim['max_travel_min']} min")
    if n_meal > C.MAX_MEALS_PER_DAY:
        v.append(f"meals {n_meal} > {C.MAX_MEALS_PER_DAY}")
    return v, dict(activities=n_act, meals=n_meal, activity_minutes=minutes, travel_min=travel, max_activities=max_act,
                   max_hours=lim['max_hours'], max_travel_min=lim['max_travel_min'])


def check_day_load(log: ToolLog, day_items: list[dict[str, Any]], pace: str, edge_day: bool = False) -> dict[str, Any]:
    v, stats = day_load_violations(day_items, pace, edge_day)
    args = dict(n_items=len(day_items), pace=pace, edge_day=edge_day)
    return _finish(log, "check_day_load", args, dict(ok=not v, violations=v, stats=stats), "code (spec 6.3 thresholds)",
                   C.LICENSES["estimate"], dt.date.today().isoformat())


# ----------------------------------------------------------------- weather
def classify(precip_mm: Optional[float], precip_h: Optional[float], apparent_max: Optional[float],
             gust_max: Optional[float]) -> list[str]:
    fl = []
    if (precip_mm or 0) >= C.RAIN_MM or (precip_h or 0) >= C.RAIN_H:
        fl.append("RAIN")
    if (apparent_max or -99) >= C.HEAT_C:
        fl.append("HEAT")
    if (gust_max or 0) >= C.WIND_KMH:
        fl.append("WIND")
    return fl


def _fixture_day(city: str, date: str) -> Optional[dict[str, Any]]:
    key = C.CITIES[city]["key"]
    p = C.WEATHER_DIR / f"{key}_{date}.json"
    if p.exists():
        d = json.loads(p.read_text())
        return dict(values=d["daily"], source=d["source"].split(" (")[0] + f" [fixture {p.name}]", license=d["license"], fetched_at=d["retrieved_at"])
    ps = C.WEATHER_DIR / f"{key}_2022_season.json"
    if ps.exists():
        d = json.loads(ps.read_text())
        daily = d["api_response"]["daily"]
        if date in daily["time"]:
            i = daily["time"].index(date)
            return dict(values={k: v[i] for k, v in daily.items()}, source=d["source"].split(" (")[0] + f" [season fixture {ps.name}]",
                        license=d["license"], fetched_at=d["retrieved_at"])
    return None


def _live_day(city: str, date: str) -> Optional[dict[str, Any]]:
    lat, lon = C.CITIES[city]["center"]
    daily = "precipitation_sum,precipitation_hours,apparent_temperature_max,wind_gusts_10m_max,temperature_2m_max"
    base = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    q = dict(latitude=lat, longitude=lon, start_date=date, end_date=date, daily=daily, timezone="auto")
    with urllib.request.urlopen(base + "?" + urllib.parse.urlencode(q), timeout=15) as r:
        d = json.loads(r.read())["daily"]
    return dict(values={k: v[0] for k, v in d.items()}, source="Open-Meteo Historical Forecast API (live)",
                license=C.LICENSES["weather"], fetched_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"))


def get_forecast(log: ToolLog, city: str, dates: Sequence[str], as_of: str, mode: Optional[str] = None) -> dict[str, Any]:
    """Flow step (not an agent tool). Days with lead_days <= 7 get a forecast (fixture by default, live optional
    via WEATHER_MODE=live); farther days are OUT_OF_HORIZON. Failure never fails the run (UNAVAILABLE)."""
    mode = mode or os.environ.get("WEATHER_MODE", "fixture")
    days = []
    any_fc, any_fail = False, False
    for d in dates:
        lead = (dt.date.fromisoformat(d) - dt.date.fromisoformat(as_of)).days
        if lead > C.HORIZON_DAYS:
            days.append(dict(date=d, lead_days=lead, flags=["OUT_OF_HORIZON"], source="", fetched_at=""))
            continue
        rec = None
        try:
            rec = _live_day(city, d) if mode == "live" else _fixture_day(city, d)
        except Exception:  # noqa: BLE001 - weather never fails the run
            rec = None
        if rec is None and mode == "live":
            rec = _fixture_day(city, d)
        if rec is None:
            any_fail = True
            days.append(dict(date=d, lead_days=lead, flags=["UNAVAILABLE"], source="", fetched_at=""))
            continue
        v = rec["values"]
        any_fc = True
        days.append(dict(date=d, lead_days=lead, precip_mm=v.get("precipitation_sum"), precip_h=v.get("precipitation_hours"),
                         apparent_max=v.get("apparent_temperature_max"), gust_max=v.get("wind_gusts_10m_max"),
                         flags=classify(v.get("precipitation_sum"), v.get("precipitation_hours"),
                                        v.get("apparent_temperature_max"), v.get("wind_gusts_10m_max")),
                         source=rec["source"], fetched_at=rec["fetched_at"]))
    status = "UNAVAILABLE" if any_fail and not any_fc else ("FORECAST" if any_fc else "OUT_OF_HORIZON")
    args = dict(city=city, dates=list(dates), as_of=as_of, mode=mode)
    return _finish(log, "get_forecast", args, dict(days=days, weather_status=status,
                   thresholds=dict(rain_mm=C.RAIN_MM, rain_h=C.RAIN_H, heat_c=C.HEAT_C, wind_kmh=C.WIND_KMH)),
                   "Open-Meteo Historical Forecast API", C.LICENSES["weather"], as_of)
