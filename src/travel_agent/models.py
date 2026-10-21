"""Pydantic models shared by all three systems (spec 1.1, 1.5 and the agent outputs in section 4)."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import CATALOG_FIRST, CATALOG_LAST, CITIES, MAX_TRAVELERS, VOCAB


class Status(str, Enum):
    OK_PLAN = "OK_PLAN"
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_PACKAGE_IN_CATALOG = "NO_PACKAGE_IN_CATALOG"
    NEEDS_DATA = "NEEDS_DATA"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"
    CONFLICT_UNRESOLVED = "CONFLICT_UNRESOLVED"
    TIMEOUT = "TIMEOUT"


class WeatherStatus(str, Enum):
    FORECAST = "FORECAST"
    OUT_OF_HORIZON = "OUT_OF_HORIZON"
    UNAVAILABLE = "UNAVAILABLE"


Interest = Literal["food", "culture", "attractions", "nightlife", "family", "nature", "shows", "shopping", "extreme/adventure"]


class TripRequest(BaseModel):
    request_id: str = "ADHOC"
    city: Literal["Chicago", "New York"]
    origin: str = Field(min_length=3, max_length=3)
    start_date: dt.date
    end_date: dt.date
    travelers: int = Field(ge=1, le=MAX_TRAVELERS)
    budget_usd: int = Field(gt=0)
    wants_car: bool
    pace: Literal["relaxed", "normal", "packed"] = "normal"
    interests: list[Interest] = Field(min_length=1, max_length=4)
    avoid: list[Interest] = Field(default_factory=list)
    hotel_preference: Literal["any", "central"] = "any"
    as_of: dt.date
    free_text: Optional[str] = None

    @field_validator("origin")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check(self) -> "TripRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        lo, hi = dt.date.fromisoformat(CATALOG_FIRST), dt.date.fromisoformat(CATALOG_LAST)
        if not (lo <= self.start_date <= hi and lo <= self.end_date <= hi):
            raise ValueError(f"dates must be within the catalog range {CATALOG_FIRST}..{CATALOG_LAST}")
        if set(self.interests) & set(self.avoid):
            raise ValueError("avoid must be disjoint from interests")
        if len(set(self.interests)) != len(self.interests):
            raise ValueError("duplicate interests")
        return self

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def days(self) -> list[dt.date]:
        return [self.start_date + dt.timedelta(i) for i in range(self.nights + 1)]

    @classmethod
    def from_case(cls, case: dict[str, Any]) -> "TripRequest":
        keys = ["city", "origin", "start_date", "end_date", "travelers", "budget_usd", "wants_car", "pace",
                "interests", "avoid", "hotel_preference", "as_of", "free_text"]
        return cls(request_id=case["id"], **{k: case[k] for k in keys if k in case})


# ----------------------------------------------------------------- tool outputs
class ToolMeta(BaseModel):
    call_id: str
    source: str
    license: str
    data_date: str


class FlightOption(BaseModel):
    ref: str
    origin: str
    destination: str
    date: str
    arrival_date: str
    dep: str
    arr: str
    fare: float
    stops: int
    duration: str
    seats: int
    airline: Optional[str] = None


class StayOption(BaseModel):
    ref: str
    title: str
    market: str
    price_per_night: float
    km_to_center: float
    lat: float
    lon: float
    capacity: int
    min_nights: int
    max_nights: int
    central: bool


class CarOption(BaseModel):
    ref: str
    airport: str
    make: str
    model: str
    vehicle_type: str
    daily_rate: float
    rental_days: int
    estimated_capacity: int
    capacity_basis: Literal["estimate"] = "estimate"


class PlaceSummary(BaseModel):
    place_id: str
    name: str
    category: str
    tags: list[str]
    indoor: Literal["true", "false", "unknown"]
    lat: float
    lon: float
    neighborhood: str = ""
    in_wikivoyage: bool = False
    typical_visit_minutes: int
    typical_visit_minutes_basis: Literal["estimate"] = "estimate"
    source: str
    license: str


class DayCondition(BaseModel):
    date: str
    lead_days: int
    precip_mm: Optional[float] = None
    precip_h: Optional[float] = None
    apparent_max: Optional[float] = None
    gust_max: Optional[float] = None
    flags: list[str] = Field(default_factory=list)   # RAIN / HEAT / WIND / OUT_OF_HORIZON / UNAVAILABLE
    source: str = ""
    fetched_at: str = ""


# ----------------------------------------------------------------- decisions
class PackageDecision(BaseModel):
    flight_out_ref: str
    flight_back_ref: str
    hotel_ref: str
    car_ref: Optional[str] = None
    price_call_id: str
    total_price: float
    tradeoffs: list[str] = Field(default_factory=list)
    relaxed_constraint: Optional[str] = None
    rationale: str = Field(default="", max_length=600)


class PlaceChoice(BaseModel):
    place_id: str
    category: str = ""
    indoor: str = "unknown"
    est_duration_min: int = 60
    matched_prefs: list[str] = Field(default_factory=list)
    reason: str = ""
    source_call_id: str = ""


class PlaceShortlist(BaseModel):
    places: list[PlaceChoice]
    uncovered_prefs: list[str] = Field(default_factory=list)


class Item(BaseModel):
    place_id: str
    name: str = ""
    kind: Literal["activity", "meal"] = "activity"
    start: str            # HH:MM local city time
    end: str
    mode: Literal["walk", "transit", "drive"]
    travel_min: int
    travel_call_id: str
    from_id: str = ""     # previous location (stay ref or place_id); used by the travel check
    weather_note: Optional[str] = None


class DayPlan(BaseModel):
    date: str
    items: list[Item] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    window: Optional[tuple[str, str]] = None


class Dropped(BaseModel):
    place_id: str
    reason: str          # WEATHER / NO_SLOT / DAY_LOAD / CLOSED / ...


class ItineraryPlan(BaseModel):
    status: Literal["OK", "CANNOT_SCHEDULE"] = "OK"
    days: list[DayPlan] = Field(default_factory=list)
    dropped: list[Dropped] = Field(default_factory=list)
    cannot_reason: Optional[Literal["DAY_LOAD", "TRAVEL_TIME", "WEATHER", "HOTEL_TOO_FAR"]] = None
    explanation: str = ""


class TripPlan(BaseModel):
    """System B single-agent structured output."""
    package: PackageDecision
    places: PlaceShortlist
    itinerary: ItineraryPlan


class Package(BaseModel):
    refs: dict[str, Optional[str]]          # flight_out, flight_back, stay, car
    price_lines: dict[str, float]
    total: float
    price_call_id: str
    flight_out: Optional[dict[str, Any]] = None
    flight_back: Optional[dict[str, Any]] = None
    stay: Optional[dict[str, Any]] = None
    car: Optional[dict[str, Any]] = None
    fees_complete: bool = False


class CheckResult(BaseModel):
    name: str
    passed: bool
    details: list[str] = Field(default_factory=list)


class CheckReport(BaseModel):
    checks: list[CheckResult] = Field(default_factory=list)
    coverage: Optional[float] = None
    rain_days: list[str] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]

    def get(self, name: str) -> Optional[CheckResult]:
        return next((c for c in self.checks if c.name == name), None)


class RunResult(BaseModel):
    run_id: str
    system: Literal["A", "B", "C"]
    request_id: str
    status: Status
    message: str = ""
    request: Optional[TripRequest] = None
    package: Optional[Package] = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)
    dropped: list[Dropped] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    weather_status: WeatherStatus = WeatherStatus.OUT_OF_HORIZON
    day_conditions: list[DayCondition] = Field(default_factory=list)
    check_report: Optional[CheckReport] = None
    all_checks_passed: bool = False
    rounds_used: int = 0
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    wall_time_s: float = 0.0
    tool_log_path: Optional[str] = None
    tool_log: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
