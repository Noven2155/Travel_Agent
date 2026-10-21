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


SoftPref = Literal["central", "nonstop", "exact_dates", "dry_days", "long_days", "under_preferred_budget"]
Interest = Literal["food", "culture", "attractions", "nightlife", "family", "nature", "shows", "shopping", "extreme/adventure"]


MAX_FLEX_NIGHTS_CHANGE = 1


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
    # ---- eval v2 extensions (all optional; defaults reproduce v1 behaviour exactly)
    depart_flex_days: int = Field(default=0, ge=0, le=1)     # outbound may leave start_date +- this many days
    return_flex_days: int = Field(default=0, ge=0, le=1)     # return may leave end_date +- this many days
    soft_prefs: list[SoftPref] = Field(default_factory=list)  # preferences that may be traded off (see prefs.py)
    preferred_budget_usd: Optional[int] = Field(default=None, gt=0)   # soft target below the hard budget_usd

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
        if len(set(self.soft_prefs)) != len(self.soft_prefs):
            raise ValueError("duplicate soft_prefs")
        if self.preferred_budget_usd is not None and self.preferred_budget_usd > self.budget_usd:
            raise ValueError("preferred_budget_usd must be <= budget_usd")
        if "under_preferred_budget" in self.soft_prefs and self.preferred_budget_usd is None:
            raise ValueError("soft pref under_preferred_budget needs preferred_budget_usd")
        if self.has_flex and (self.end_date - self.start_date).days < 2:
            raise ValueError("date flexibility needs a trip of >= 2 nights")
        return self

    @property
    def has_flex(self) -> bool:
        return bool(self.depart_flex_days or self.return_flex_days)

    def date_pairs(self) -> list[tuple[dt.date, dt.date]]:
        """All (start, end) pairs allowed by the flex fields; the requested pair first. Each end moves by at most its
        flex, and the trip length changes by at most MAX_FLEX_NIGHTS_CHANGE night (a shift, not a different trip)."""
        lo, hi = dt.date.fromisoformat(CATALOG_FIRST), dt.date.fromisoformat(CATALOG_LAST)
        pairs = [(self.start_date, self.end_date)]
        for a in range(-self.depart_flex_days, self.depart_flex_days + 1):
            for b in range(-self.return_flex_days, self.return_flex_days + 1):
                s, e = self.start_date + dt.timedelta(a), self.end_date + dt.timedelta(b)
                if (s, e) not in pairs and lo <= s and e <= hi and (e - s).days >= 1 and \
                        abs((e - s).days - self.nights) <= MAX_FLEX_NIGHTS_CHANGE:
                    pairs.append((s, e))
        return pairs

    def with_dates(self, start: str | dt.date, end: str | dt.date) -> "TripRequest":
        s = dt.date.fromisoformat(start) if isinstance(start, str) else start
        e = dt.date.fromisoformat(end) if isinstance(end, str) else end
        if (s, e) == (self.start_date, self.end_date):
            return self
        return self.model_copy(update=dict(start_date=s, end_date=e))

    def all_dates(self) -> list[dt.date]:
        """Every date any allowed (start, end) pair can touch (for the weather step)."""
        s0 = self.start_date - dt.timedelta(self.depart_flex_days)
        e0 = self.end_date + dt.timedelta(self.return_flex_days)
        return [s0 + dt.timedelta(i) for i in range((e0 - s0).days + 1)]

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def days(self) -> list[dt.date]:
        return [self.start_date + dt.timedelta(i) for i in range(self.nights + 1)]

    @classmethod
    def from_case(cls, case: dict[str, Any]) -> "TripRequest":
        keys = ["city", "origin", "start_date", "end_date", "travelers", "budget_usd", "wants_car", "pace",
                "interests", "avoid", "hotel_preference", "as_of", "free_text", "depart_flex_days", "return_flex_days",
                "soft_prefs", "preferred_budget_usd"]
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


def effective_request(req: TripRequest, package: Optional["Package"]) -> TripRequest:
    """With date flexibility the trip dates are those of the chosen flights (if they are within the flex window);
    otherwise the request itself. Used by final_checks and the schedulers."""
    if package is None or not req.has_flex or not package.flight_out or not package.flight_back:
        return req
    s, e = package.flight_out.get("date"), package.flight_back.get("date")
    try:
        sd, ed = dt.date.fromisoformat(s), dt.date.fromisoformat(e)
    except (TypeError, ValueError):
        return req
    if (sd, ed) in req.date_pairs():
        return req.with_dates(sd, ed)
    return req


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
