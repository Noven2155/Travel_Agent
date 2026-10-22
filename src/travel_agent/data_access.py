"""Read-only access to the local data files (catalog, places). Loaded once per process and cached."""
from __future__ import annotations

import base64
import csv
import datetime as dt
import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from . import config as C


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.radians
    x = math.sin(p(lat2 - lat1) / 2) ** 2 + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(x))


class Catalog:
    """inventory.json: flights (one-way records), stays (Airbnb, packed availability), cars."""

    def __init__(self, path: Path = C.INVENTORY_PATH):
        inv = json.loads(Path(path).read_text())
        self.path = Path(path)
        self.dates: list[str] = inv["dates"]
        self.date_index = {d: i for i, d in enumerate(self.dates)}
        self.flights: list[dict[str, Any]] = inv["flights"]
        for i, f in enumerate(self.flights):
            f["ref"] = f"F{i}"
        self.flight_by_ref = {f["ref"]: f for f in self.flights}
        self.stays = {s["key"]: s for s in inv["stays"]}
        self.stays_by_airport: dict[str, list[str]] = inv["staysByAirport"]
        self.cars = {c["id"]: c for c in inv["cars"]}
        self.cars_by_airport: dict[str, list[str]] = inv["carsByAirport"]
        self.origins = [o["code"] for o in inv["originAirports"]]
        self.data_notes = inv.get("dataNotes", {})
        self._decoded: dict[str, tuple[list[int], tuple[int, ...], tuple[int, ...]]] = {}
        self._by_route: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for f in self.flights:
            self._by_route.setdefault((f["origin"], f["destination"], f["date"]), []).append(f)

    # --- flights
    def flights_on(self, origin: str, dest: str, date: str) -> list[dict[str, Any]]:
        return self._by_route.get((origin, dest, date), [])

    # --- stays
    def decode(self, key: str):
        if key not in self._decoded:
            s, n = self.stays[key], len(self.dates)
            b = base64.b64decode(s["availabilityPacked"])
            av = [(b[i // 4] >> (2 * (i % 4))) & 3 for i in range(n)]   # 0 unknown, 1 unavailable, 2 available
            mn = struct.unpack("<%dH" % n, base64.b64decode(s["minNightsPacked"]))
            mx = struct.unpack("<%dH" % n, base64.b64decode(s["maxNightsPacked"]))
            self._decoded[key] = (av, mn, mx)
        return self._decoded[key]

    def city_stay_keys(self, city: str) -> list[str]:
        out: list[str] = []
        for a in C.CITIES[city]["airports"]:
            for k in self.stays_by_airport.get(a, []):
                if k not in out:
                    out.append(k)
        return out

    def stay_km_to_center(self, city: str, key: str) -> float:
        s = self.stays[key]
        lat, lon = C.CITIES[city]["center"]
        return haversine_km(lat, lon, s["lat"], s["lon"])

    def stay_city(self, key: str) -> Optional[str]:
        for city in C.CITIES:
            if key in self.city_stay_keys(city):
                return city
        return None


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return Catalog()


# ----------------------------------------------------------------- places
PLACE_FIELDS_PUBLIC = ["place_id", "name", "category", "subcategory", "tags", "indoor", "lat", "lon", "neighborhood",
                       "in_wikivoyage", "has_wikidata", "typical_visit_minutes", "source", "license"]
SYNTHETIC_NEVER_EXPOSED = ["rating", "review_count", "price_level"]


class PlacesDB:
    def __init__(self, city: str, rows: list[dict[str, str]], path: Path):
        self.city, self.path = city, path
        self.rows = rows
        self.by_id = {r["place_id"]: r for r in rows}
        self.retrieved_at = max((r.get("retrieved_at", "") for r in rows), default="")

    @staticmethod
    def tags(r: dict[str, str]) -> list[str]:
        return [t for t in (r.get("tags") or "").split(";") if t]


def places_path(city: str) -> Path:
    return C.PLACES_DIR / f"{C.CITIES[city]['key']}_places.csv"


def get_places(city: str) -> Optional[PlacesDB]:
    """Returns None when the city's places file does not exist (e.g. NYC is still being built)."""
    p = places_path(city)
    if not p.exists():
        return None
    return _load_places(str(p), p.stat().st_mtime, city)


@lru_cache(maxsize=4)
def _load_places(path: str, mtime: float, city: str) -> PlacesDB:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return PlacesDB(city, rows, Path(path))


def clean_text(s: str, n: int = 200) -> str:
    """Free text from sources is cleaned before it reaches an agent (no markup / control chars, bounded)."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


# ----------------------------------------------------------------- opening hours (subset of the OSM syntax)
_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def parse_opening_hours(spec: str) -> Optional[dict[int, list[tuple[int, int]]]]:
    """Parse common OSM opening_hours forms into {weekday: [(start_min, end_min)]}. Returns None if unknown/unparseable."""
    if not spec or not spec.strip():
        return None
    spec = spec.strip()
    if spec == "24/7":
        return {d: [(0, 24 * 60)] for d in range(7)}
    out: dict[int, list[tuple[int, int]]] = {}
    for rule in [r.strip() for r in spec.split(";") if r.strip()]:
        m = re.match(r"^((?:(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)(?:\s*,\s*(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)?\s*(.*)$", rule)
        if not m:
            return None
        days_part, times_part = m.group(1), m.group(2).strip()
        if days_part:
            days: list[int] = []
            for chunk in re.split(r"\s*,\s*", days_part):
                if "-" in chunk:
                    a, b = chunk.split("-")
                    ia, ib = _DAYS.index(a), _DAYS.index(b)
                    rng = list(range(ia, ib + 1)) if ia <= ib else list(range(ia, 7)) + list(range(0, ib + 1))
                    days.extend(rng)
                else:
                    days.append(_DAYS.index(chunk))
        else:
            days = list(range(7))
        if times_part in ("off", "closed"):
            for d in days:
                out[d] = []
            continue
        intervals = []
        for t in re.split(r"\s*,\s*", times_part):
            mt = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\+?$", t)
            if not mt:
                return None
            a = int(mt.group(1)) * 60 + int(mt.group(2))
            b = int(mt.group(3)) * 60 + int(mt.group(4))
            if b <= a:
                b += 24 * 60
            intervals.append((a, b))
        for d in days:
            out[d] = intervals
    return out


def is_open(spec: str, date: dt.date, start_min: int, end_min: int) -> Optional[bool]:
    """True/False if the opening hours are known and parseable, None if unknown (unknown never blocks)."""
    parsed = parse_opening_hours(spec)
    if parsed is None:
        return None
    wd = date.weekday()
    if wd not in parsed:          # OSM semantics: days not listed are closed
        return False
    return any(a <= start_min and end_min <= b for a, b in parsed[wd])
