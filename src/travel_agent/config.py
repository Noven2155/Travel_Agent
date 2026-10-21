"""Paths, thresholds and constants. Mirrors system_definition_HE.md (sections 1 and 6.3)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("TRAVEL_AGENT_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = REPO_ROOT / "data"
INVENTORY_PATH = DATA_DIR / "inventory.json"
PLACES_DIR = DATA_DIR / "places"
WEATHER_DIR = DATA_DIR / "weather"
EVAL_DIR = REPO_ROOT / "eval"
CASES_PATH = EVAL_DIR / "cases" / "eval_cases.json"
RESULTS_DIR = EVAL_DIR / "results"

CITIES = {
    "Chicago": dict(key="chicago", airports=["ORD"], center=(41.8819, -87.6278), center_name="Loop (State & Madison)",
                    tz="America/Chicago"),
    "New York": dict(key="nyc", airports=["JFK", "LGA", "EWR"], center=(40.7580, -73.9855), center_name="Times Square",
                     tz="America/New_York"),
}
CENTRAL_RADIUS_KM = {"Chicago": 5.0, "New York": 6.0}
MAX_STAY_KM = 12.0
MAX_CAR_TRAVELERS = 4
MAX_TRAVELERS = 6
CATALOG_FIRST, CATALOG_LAST = "2022-04-17", "2022-11-19"

VOCAB = ["food", "culture", "attractions", "nightlife", "family", "nature", "shows", "shopping", "extreme/adventure"]
MEAL_CATEGORIES = {"restaurant", "cafe", "fast_food", "food_court"}

# weather (spec 1.2)
HORIZON_DAYS = 7
RAIN_MM, RAIN_H, HEAT_C, WIND_KMH = 5.0, 3.0, 35.0, 60.0
HEAT_OUTDOOR_BEFORE, HEAT_OUTDOOR_FROM = "11:00", "17:00"

# day load (spec 6.3): max activities (meals excluded), max activity hours (meals included), max travel minutes
DAY_LOAD = {
    "relaxed": dict(max_activities=2, max_hours=6.0, max_travel_min=60),
    "normal": dict(max_activities=3, max_hours=8.0, max_travel_min=90),
    "packed": dict(max_activities=5, max_hours=10.0, max_travel_min=120),
}
EDGE_DAY_MAX_ACTIVITIES = 1          # arrival / departure day
MAX_MEALS_PER_DAY = 2
COVERAGE_MIN = 0.75

DAY_START, DAY_END = "09:30", "20:00"
ARRIVAL_BUFFER_MIN = 90               # items only after landing + 90 min
DEPARTURE_BUFFER_MIN = 180            # items only before take-off - 180 min
LUNCH_WINDOW = ("11:30", "14:30")
DINNER_WINDOW = ("17:30", "20:00")
MEAL_MINUTES = 60                     # fixed meal duration (team decision, not from data)

# travel-time estimate (spec 1.3): haversine x 1.3 / speed + overhead
DETOUR_FACTOR = 1.3
SPEED_KMH = {"walk": 4.8, "transit": 18.0, "drive": 25.0}
OVERHEAD_MIN = {"walk": 0, "transit": 5, "drive": 10}   # drive overhead = parking
WALK_MAX_KM = 1.0                     # legs <= 1 km are always walked

# limits (spec 1.5)
MAX_ROUNDS = 3
DEADLINE_S = 270
METRIC_TIME_LIMIT_S = 300

LICENSES = {
    "catalog": "Flights: dilwong/FlightPrices (Kaggle, from Expedia); lodging: Inside Airbnb CC BY 4.0 (availability synthetic); "
               "cars: Cornell Car Rental (Kaggle; availability synthetic)",
    "places": "ODbL 1.0 (© OpenStreetMap contributors) / CC BY-SA (Wikivoyage)",
    "weather": "CC BY 4.0 (Open-Meteo)",
    "estimate": "n/a (deterministic estimate computed in code)",
}
