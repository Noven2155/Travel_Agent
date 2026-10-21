#!/usr/bin/env python3
"""Fetch weather fixtures ONCE from the Open-Meteo Historical Forecast API (free, no key, CC BY 4.0).

Writes:
  data/weather/{city}_{date}.json        one file per date needed by the eval cases (weather_fixture_files)
  data/weather/{city}_2022_season.json   whole catalog season (fallback for ad-hoc UI requests)
Each file records source, license, retrieved_at and the request URL. Re-running overwrites the files;
the eval uses the committed files and never calls the network.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travel_agent import config as C  # noqa: E402

API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
DAILY = "precipitation_sum,precipitation_hours,apparent_temperature_max,wind_gusts_10m_max,temperature_2m_max"
SOURCE = "Open-Meteo Historical Forecast API (https://open-meteo.com/en/docs/historical-forecast-api)"
LICENSE = "CC BY 4.0 (Open-Meteo, https://open-meteo.com/en/license)"


def fetch(city: str, start: str, end: str) -> tuple[str, dict]:
    lat, lon = C.CITIES[city]["center"]
    q = dict(latitude=lat, longitude=lon, start_date=start, end_date=end, daily=DAILY, timezone="auto")
    url = API + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=60) as r:
        return url, json.loads(r.read())


def main() -> None:
    cases = json.loads(C.CASES_PATH.read_text())["cases"]
    need: dict[str, set[str]] = defaultdict(set)
    key2city = {v["key"]: k for k, v in C.CITIES.items()}
    for c in cases:
        for f in c["weather_fixture_files"]:
            stem = Path(f).stem
            key, date = stem.rsplit("_", 1)
            need[key2city[key]].add(date)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    C.WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    for city, cfg in C.CITIES.items():
        url, data = fetch(city, C.CATALOG_FIRST, C.CATALOG_LAST)
        daily = data["daily"]
        season = dict(source=SOURCE, license=LICENSE, retrieved_at=now, city=city, point=cfg["center"],
                      request_url=url, api_response=data)
        (C.WEATHER_DIR / f"{cfg['key']}_2022_season.json").write_text(json.dumps(season, indent=1))
        for i, d in enumerate(daily["time"]):
            if d not in need.get(city, set()):
                continue
            one = {k: v[i] for k, v in daily.items()}
            rec = dict(source=SOURCE, license=LICENSE, retrieved_at=now, city=city, date=d, point=cfg["center"],
                       request_url=url, timezone=data.get("timezone"), daily_units=data.get("daily_units"), daily=one)
            (C.WEATHER_DIR / f"{cfg['key']}_{d}.json").write_text(json.dumps(rec, indent=1))
        print(city, "season days:", len(daily["time"]), "per-date fixtures:", len(need.get(city, ())))


if __name__ == "__main__":
    main()
