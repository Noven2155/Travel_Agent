# Weather fixtures (`data/weather/`)

Fetched once on 2026-10-21 by `scripts/fetch_weather.py` from the **Open-Meteo Historical Forecast API**
(https://open-meteo.com/en/docs/historical-forecast-api) – free, no key, **CC BY 4.0** (Open-Meteo, https://open-meteo.com/en/license).

- `{city}_{date}.json` – one file per date needed by the eval cases (`weather_fixture_files` in `eval_cases.json`):
  daily `precipitation_sum`, `precipitation_hours`, `apparent_temperature_max`, `wind_gusts_10m_max`, `temperature_2m_max`
  at the city center point (Chicago Loop 41.8819,-87.6278; Times Square 40.7580,-73.9855). Each file records
  `source`, `license`, `retrieved_at` and the request URL.
- `{city}_2022_season.json` – the whole catalog season (2022-04-17..2022-11-19), used only as a fallback for ad-hoc
  UI requests on dates without a per-date file.

Classification (code, spec 1.2): RAIN if ≥ 5 mm or ≥ 3 h of precipitation; HEAT if apparent max ≥ 35 °C; WIND if
gusts ≥ 60 km/h; days more than 7 days after `as_of` are `OUT_OF_HORIZON`. The flags reproduce `weather_expected`
in the frozen eval set for all 48 cases (tested). Caveat: historical-forecast data is stitched from the first hours
of each model run, so it is closer to observations than a real 1–7 day forecast. `WEATHER_MODE=live` queries the API
instead (demo only); a weather failure never fails a run (`weather_status=UNAVAILABLE`).
