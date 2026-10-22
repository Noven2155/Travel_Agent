"""LLM parser for free-text trip requests (hybrid system, and the free-text intake of systems B and C).

One LLM call (plus at most one repair call when the JSON does not validate): the model gets the request text, the
as_of date, the closed vocabularies and the JSON schema of the TripRequest fields, and must answer with JSON only.
The answer is validated with pydantic (TripRequest); request_id / as_of / request_text are set by code, not the
model. The model is told to put every requirement it understood but could not map into unparsed_requirements.
Same LLM settings as B and C (systems/llm.py, from .env). Tests inject a fake LLM; no real LLM is called in tests.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from ..config import CITIES, VOCAB
from ..models import FreeTextRequest, PRIORITY_KEYS, TripRequest
from . import ParseResult

FIELDS = """{
 "city": "Chicago" | "New York",
 "origin": IATA code of the home airport, one of %(origins)s (New York origin: JFK, LGA or EWR as written; Chicago: ORD),
 "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"  (year = the as_of year unless written),
 "travelers": int 1-6 (count every person incl. children),
 "budget_usd": int, hard maximum for flights + lodging (+ car) for the whole party,
 "preferred_budget_usd": int | null  (a softer target below the hard budget, only if stated),
 "wants_car": bool,
 "pace": "relaxed" | "normal" | "packed",
 "interests": 1-4 of %(vocab)s,
 "avoid": list from the same vocabulary (things the traveler does NOT want),
 "hotel_preference": "any" | "central"  ("central" only when central lodging is a must),
 "soft_prefs": list of "central","nonstop","exact_dates","dry_days","long_days","under_preferred_budget" (wishes that may be traded off),
 "depart_flex_days": 0|1, "return_flex_days": 0|1  (1 = dates may move by one day),
 "priority_weights": {key: weight} with keys in %(prio)s, e.g. {"central": 2} = location matters more than price/other wishes,
 "daily_blocked_windows": [{"start":"HH:MM","end":"HH:MM","label":"..."}]  (daily times with nothing planned: nap, rest, prayer),
 "max_walk_minutes": int | null, "day_start": "HH:MM" | null, "day_end": "HH:MM" | null,
 "accessibility": bool (step-free / wheelchair needs), "no_early_flight_before": "HH:MM" | null (no flight departs before),
 "unparsed_requirements": [short strings] - every requirement you understood but could NOT express with the fields above
}"""

PROMPT = """You convert a traveler's free-text request into JSON fields for a trip planner.
Answer with ONE JSON object only (no prose, no markdown). Use only these fields:
%(fields)s
Do not invent requirements that the text does not state or clearly imply. Map indirect phrasing to the fields when the
meaning is clear (e.g. "the kid naps after lunch" -> a daily blocked window; "we are not morning people" -> day_start).
as_of (today) = %(as_of)s.
REQUEST TEXT:
%(text)s
"""


def _json(s: str) -> dict[str, Any]:
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
    i = s.find("{")
    return json.JSONDecoder().raw_decode(s[i:])[0]


def parse(ft: FreeTextRequest, llm=None) -> ParseResult:
    from ..data_access import get_catalog
    from ..systems.llm import make_llm, usage_of
    llm = llm or make_llm("parser")
    before = usage_of(llm)
    fields = FIELDS % dict(origins=", ".join(get_catalog().origins), vocab=json.dumps(VOCAB), prio=json.dumps(list(PRIORITY_KEYS)))
    msgs = [{"role": "user", "content": PROMPT % dict(fields=fields, as_of=ft.as_of.isoformat(), text=ft.request_text)}]
    err, out, n_calls, raw = "", None, 0, ""
    for attempt in range(2):
        try:
            n_calls += 1
            raw = llm.call(msgs)
            d = _json(raw if isinstance(raw, str) else json.dumps(raw))
            d = {k: v for k, v in d.items() if k in TripRequest.model_fields and k not in ("request_id", "as_of", "request_text")}
            d.update(request_id=ft.request_id, as_of=ft.as_of, request_text=ft.request_text, free_text=ft.request_text)
            d = {k: v for k, v in d.items() if v is not None or k in ("preferred_budget_usd",)}
            TripRequest.model_validate(d)
            out = d
            break
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            err = f"{type(e).__name__}: {str(e)[:400]}"
            msgs = msgs + [{"role": "assistant", "content": str(raw)},
                           {"role": "user", "content": "That JSON is invalid: " + err + "\nAnswer again with ONE corrected JSON object."}]
    after = usage_of(llm)
    calls = max(after[0] - before[0], n_calls)
    return ParseResult("llm", out, [], error="" if out is not None else "LLM parse failed: " + err,
                       llm_calls=calls, tokens_in=max(0, after[1] - before[1]), tokens_out=max(0, after[2] - before[2]))


__all__ = ["parse", "CITIES"]
