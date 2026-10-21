"""A scripted, deterministic fake LLM for wiring tests of systems B and C (no network, no model).

It speaks CrewAI's ReAct text protocol: it reads the CONTEXT JSON in the task prompt, calls real tools through
'Action:' lines (so tool wrappers + the run's ToolLog are exercised) and answers with JSON for the expected schema.
With bad_first=True the first package answer has a wrong total, so the code checks fail and the Flow router must
send the run back for a replan.
"""
from __future__ import annotations

import json
import re
from typing import Any

from crewai import BaseLLM


def _text(messages) -> str:
    if isinstance(messages, str):
        return messages
    return "\n".join(str(m.get("content", "")) for m in messages)


def _context(text: str) -> dict[str, Any]:
    i = text.rfind("CONTEXT:\n")
    return json.JSONDecoder().raw_decode(text[i + len("CONTEXT:\n"):])[0] if i >= 0 else {}


def _observations(text: str) -> list[dict[str, Any]]:
    obs = []
    for m in re.finditer(r"Observation: ", text):
        try:
            obs.append(json.JSONDecoder().raw_decode(text[m.end():])[0])
        except Exception:  # noqa: BLE001
            pass
    return obs


def _hm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _min(s: str) -> int:
    return int(s[:2]) * 60 + int(s[3:5])


class ScriptedLLM(BaseLLM):
    bad_first: bool = False
    calls: int = 0

    def supports_function_calling(self) -> bool:
        return False

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None,
             response_model=None, **kw):
        self.calls += 1
        self._track_token_usage_internal({"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
        text = _text(messages)
        ctx = _context(text)
        obs = _observations(text)
        feedback = "FAILED these code checks" in text
        if "Trip planner for one traveler" in text:
            return self._single(ctx, obs, feedback)
        if "Trip manager who builds the package" in text:
            return self._final(self._package(ctx["top5_candidates"][0], feedback))
        if "Local guide who matches places" in text:
            if not obs:
                lod = ctx["lodging"]
                return self._action("search_places", dict(city=ctx["city"], tags=ctx["interests"], indoor_only=True,
                                                          near_lat=lod["lat"], near_lon=lod["lon"], limit=12, exclude_tags=ctx["avoid"]))
            places = self._cover(obs[-1]["places"], ctx["interests"], 8)
            return self._final(dict(places=[dict(place_id=p["place_id"], matched_prefs=sorted(set(p["tags"]) & set(ctx["interests"])),
                                                 reason="matches interest", source_call_id=obs[-1]["call_id"]) for p in places]))
        if "Scheduler who balances days" in text:
            return self._schedule(ctx["lodging_ref"], ctx["day_windows"], ctx["places"], ctx["travel_mode"], obs, final_only=True)
        return self._final({})

    # ---- helpers
    @staticmethod
    def _action(name: str, args: dict[str, Any]) -> str:
        return f"Thought: I need {name}\nAction: {name}\nAction Input: {json.dumps(args)}"

    @staticmethod
    def _final(obj: dict[str, Any]) -> str:
        return "Thought: I now know the final answer\nFinal Answer: " + json.dumps(obj)

    def _package(self, c: dict[str, Any], feedback: bool) -> dict[str, Any]:
        total = c["total"] + (1.0 if self.bad_first and not feedback else 0.0)
        r = c["refs"]
        return dict(flight_out_ref=r["flight_out"], flight_back_ref=r["flight_back"], hotel_ref=r["stay"], car_ref=r["car"],
                    price_call_id=c["price_call_id"], total_price=total, tradeoffs=["cheapest candidate"], rationale="fake")

    @staticmethod
    def _cover(places: list[dict[str, Any]], interests: list[str], n: int) -> list[dict[str, Any]]:
        out = []
        for t in interests:
            p = next((p for p in places if t in p["tags"] and p not in out), None)
            if p:
                out.append(p)
        out += [p for p in places if p not in out]
        return out[:n]

    def _schedule(self, lodging: str, windows: dict[str, list[str]], places: list[dict[str, Any]], mode: str,
                  obs: list[dict[str, Any]], final_only: bool, package: dict[str, Any] | None = None,
                  wrap: bool = False):
        # one activity per day (always within any pace limit), first legs from the lodging
        plan = []
        pool = list(places)
        for d, (a, b) in windows.items():
            if not pool:
                break
            p = pool[0]
            dur = p.get("minutes") or p.get("typical_visit_minutes") or 60
            if _min(b) - _min(a) < dur + 60:
                continue
            pool.pop(0)
            plan.append((d, a, p, dur))
        tt = next((o for o in obs if o.get("method") == "estimate"), None)
        if tt is None:
            return self._action("get_travel_time", dict(pairs=[[lodging, p["place_id"]] for _, _, p, _ in plan], mode=mode))
        legs = {(l["from_id"], l["to_id"]): l for l in tt["legs"]}
        days = []
        for d, a, p, dur in plan:
            leg = legs[(lodging, p["place_id"])]
            s = _min(a) + leg["minutes"]
            days.append(dict(date=d, items=[dict(place_id=p["place_id"], start=_hm(s), end=_hm(s + dur), mode=leg["mode"],
                                                 travel_min=leg["minutes"], travel_call_id=tt["call_id"], from_id=lodging)]))
        itin = dict(status="OK", days=days, dropped=[], explanation="one place per day")
        if wrap:
            return self._final(dict(package=package, places=dict(places=[dict(place_id=p["place_id"]) for p in places]), itinerary=itin))
        return self._final(itin)

    def _single(self, ctx: dict[str, Any], obs: list[dict[str, Any]], feedback: bool) -> str:
        c = ctx["top5_candidates"][0]
        req = ctx["request"]
        places_obs = next((o for o in obs if "places" in o), None)
        if places_obs is None:
            return self._action("search_places", dict(city=req["city"], tags=req["interests"], indoor_only=True,
                                                      near_lat=c["stay_lat"], near_lon=c["stay_lon"], limit=12,
                                                      exclude_tags=req["avoid"]))
        places = self._cover(places_obs["places"], req["interests"], 8)
        return self._schedule(c["refs"]["stay"], c["day_windows"], places, ctx["travel_mode"], obs, final_only=False,
                              package=self._package(c, feedback), wrap=True)
