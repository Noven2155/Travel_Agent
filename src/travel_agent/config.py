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
CASES_PATH = EVAL_DIR / "cases" / "eval_cases.json"            # v1 (frozen, kept for history)
CASES_PATH_V2 = EVAL_DIR / "cases" / "eval_cases_v2.json"      # v2 (true-conflict cases; default for run_eval)
CASES_PATH_V3 = EVAL_DIR / "cases" / "eval_cases_v3.json"      # v3 (free-text segment, additive; systems see only the text)
CASES_PATHS = {"v1": CASES_PATH, "v2": CASES_PATH_V2, "v3": CASES_PATH_V3}
FROZEN_FILES = {"v1": EVAL_DIR / "cases" / "FROZEN.sha256", "v2": EVAL_DIR / "cases" / "FROZEN_v2.sha256",
                "v3": EVAL_DIR / "cases" / "FROZEN_v3.sha256"}
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

# System A strong (rules): plausible visiting hours by OSM category, used only when a place has no parseable
# opening_hours (real OSM hours always win). Team decision from common opening patterns; bars / nightlife evenings only.
TYPE_HOURS = {
    "bar": ("16:00", "26:00"), "pub": ("16:00", "26:00"), "nightclub": ("20:00", "28:00"),
    "theatre": ("12:00", "23:59"),
    "museum": ("09:00", "18:00"), "gallery": ("10:00", "18:00"), "arts_centre": ("09:00", "22:00"),
    "park": ("06:00", "21:30"), "viewpoint": ("06:00", "22:00"), "zoo": ("09:00", "18:00"), "aquarium": ("09:00", "18:00"),
    "restaurant": ("11:00", "23:00"), "cafe": ("07:00", "19:00"), "fast_food": ("10:00", "23:00"), "food_court": ("10:00", "21:00"),
    "shopping": ("10:00", "21:00"),
}
# the categories that best represent an interest (a "core" match); notable = in Wikivoyage and has a Wikidata item
INTEREST_CORE_CATEGORIES = {
    "culture": {"museum", "gallery"}, "nature": {"park", "viewpoint", "zoo"}, "shows": {"theatre", "arts_centre"},
    "attractions": {"attraction", "viewpoint", "aquarium", "zoo", "museum", "historic", "theme_park"},
    "family": {"zoo", "aquarium", "theme_park", "museum"}, "nightlife": {"bar", "pub", "nightclub"}, "shopping": {"shopping"},
}

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
