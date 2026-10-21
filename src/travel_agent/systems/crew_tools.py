"""CrewAI wrappers around the deterministic tools. Each wrapper is bound to the run's ToolLog, so every
agent tool call is logged with a call_id exactly like the code's own calls (grounding stays a code check)."""
from __future__ import annotations

import json
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from .. import tools as T
from ..tool_log import ToolLog

try:
    from crewai.tools import BaseTool
except Exception:  # noqa: BLE001 - crewai optional for system A
    BaseTool = object  # type: ignore[misc,assignment]


def _dump(out: dict[str, Any], max_chars: int = 12000) -> str:
    s = json.dumps(out, ensure_ascii=False, default=str)
    if len(s) > max_chars:
        s = s[:max_chars] + ' ... [truncated; narrow the query]"}'
    return s


class _Bound(BaseTool):  # type: ignore[misc]
    log: Any = None
    model_config = {"arbitrary_types_allowed": True}


class FlightsArgs(BaseModel):
    origin: str = Field(description="origin IATA code")
    airports: list[str] = Field(description="destination-city airports, e.g. ['ORD']")
    date: str = Field(description="YYYY-MM-DD")
    min_seats: int
    direction: str = Field(description="'out' (origin->city) or 'back' (city->origin)")


class SearchFlightsTool(_Bound):
    name: str = "search_flights"
    description: str = "Search one-way catalog flights. Returns options with ref, dep, arr, fare (per traveler, one way), stops, seats, and a call_id."
    args_schema: Type[BaseModel] = FlightsArgs

    def _run(self, origin: str, airports: list[str], date: str, min_seats: int, direction: str = "out") -> str:
        return _dump(T.search_flights(self.log, origin, airports, date, min_seats, direction))


class HotelsArgs(BaseModel):
    city: str
    check_in: str
    check_out: str
    guests: int
    central: bool = False


class SearchHotelsTool(_Bound):
    name: str = "search_hotels"
    description: str = "Search lodging that is available every night and fits guests / min-nights / distance rules. Returns ref, price_per_night, km_to_center, call_id."
    args_schema: Type[BaseModel] = HotelsArgs

    def _run(self, city: str, check_in: str, check_out: str, guests: int, central: bool = False) -> str:
        return _dump(T.search_hotels(self.log, city, check_in, check_out, guests, central))


class CarsArgs(BaseModel):
    airport: str
    start: str
    end: str
    travelers: int


class SearchCarsTool(_Bound):
    name: str = "search_cars"
    description: str = "Search rental cars at an airport (capacity is an ESTIMATE; >4 travelers -> NEEDS_DATA). Returns ref (C...), daily_rate, rental_days, call_id."
    args_schema: Type[BaseModel] = CarsArgs

    def _run(self, airport: str, start: str, end: str, travelers: int) -> str:
        return _dump(T.search_cars(self.log, airport, start, end, travelers))


class PriceArgs(BaseModel):
    flight_out: str
    flight_back: str
    stay: str
    car: Optional[str] = None
    travelers: int
    nights: int


class CalculatePriceTool(_Bound):
    name: str = "calculate_price"
    description: str = "The ONLY way to get a package total. Returns lines{flights,lodging,car}, total and the call_id to cite as price_call_id."
    args_schema: Type[BaseModel] = PriceArgs

    def _run(self, flight_out: str, flight_back: str, stay: str, travelers: int, nights: int, car: Optional[str] = None) -> str:
        return _dump(T.calculate_price(self.log, dict(flight_out=flight_out, flight_back=flight_back, stay=stay, car=car), travelers, nights))


class PlacesArgs(BaseModel):
    city: str
    tags: list[str] = Field(description="interest tags from the closed vocabulary")
    indoor_only: bool = False
    near_lat: Optional[float] = None
    near_lon: Optional[float] = None
    limit: int = 15
    exclude_tags: list[str] = Field(default_factory=list)


class SearchPlacesTool(_Bound):
    name: str = "search_places"
    description: str = "Search places by tags (no ratings - they are synthetic). Returns place_id, name, category, tags, indoor (true/false/unknown), lat, lon, typical_visit_minutes (estimate), call_id."
    args_schema: Type[BaseModel] = PlacesArgs

    def _run(self, city: str, tags: list[str], indoor_only: bool = False, near_lat: Optional[float] = None,
             near_lon: Optional[float] = None, limit: int = 15, exclude_tags: Optional[list[str]] = None) -> str:
        near = (near_lat, near_lon) if near_lat is not None and near_lon is not None else None
        return _dump(T.search_places(self.log, city, tags, indoor_only, near, min(limit, 30), exclude_tags or []))


class DetailsArgs(BaseModel):
    place_id: str


class PlaceDetailsTool(_Bound):
    name: str = "get_place_details"
    description: str = "Opening hours (or 'unknown'), website and a short description for one place_id."
    args_schema: Type[BaseModel] = DetailsArgs

    def _run(self, place_id: str) -> str:
        return _dump(T.get_place_details(self.log, place_id))


class TravelArgs(BaseModel):
    pairs: list[list[str]] = Field(description="list of [from_id, to_id]; ids are place_id or the lodging ref")
    mode: str = Field(description="walk | transit | drive (legs <= 1 km are always walk)")


class TravelTimeTool(_Bound):
    name: str = "get_travel_time"
    description: str = "Batch travel-time estimate for a day's legs. Use the returned minutes, mode and call_id verbatim (travel_min, mode, travel_call_id)."
    args_schema: Type[BaseModel] = TravelArgs

    def _run(self, pairs: list[list[str]], mode: str = "transit") -> str:
        return _dump(T.get_travel_time(self.log, pairs, mode))


class DayLoadArgs(BaseModel):
    day_items: list[dict[str, Any]] = Field(description="items with kind (activity|meal), start, end (HH:MM), travel_min")
    pace: str
    edge_day: bool = False


class DayLoadTool(_Bound):
    name: str = "check_day_load"
    description: str = "Check one day against the pace limits (activities, hours, travel minutes; arrival/departure day max 1 activity)."
    args_schema: Type[BaseModel] = DayLoadArgs

    def _run(self, day_items: list[dict[str, Any]], pace: str, edge_day: bool = False) -> str:
        return _dump(T.check_day_load(self.log, day_items, pace, edge_day))


TOOL_CLASSES = {c.model_fields["name"].default: c for c in
                [SearchFlightsTool, SearchHotelsTool, SearchCarsTool, CalculatePriceTool, SearchPlacesTool,
                 PlaceDetailsTool, TravelTimeTool, DayLoadTool]} if BaseTool is not object else {}

ALL_AGENT_TOOLS = ["search_flights", "search_hotels", "search_cars", "calculate_price", "search_places",
                   "get_place_details", "get_travel_time", "check_day_load"]


def make_tools(log: ToolLog, names: list[str]) -> list[Any]:
    return [TOOL_CLASSES[n](log=log) for n in names]
