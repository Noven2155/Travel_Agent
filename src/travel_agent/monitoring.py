"""Observed execution metadata; never exports model prompts or reasoning."""
from __future__ import annotations

import datetime as dt
import json
import os

UTC = dt.timezone.utc
TOOLS = {"search_flights": "חיפוש טיסות", "search_stays": "חיפוש לינה", "search_cars": "חיפוש רכבים",
         "price_package": "חישוב מחיר חבילה", "search_places": "חיפוש מקומות", "get_place_details": "בדיקת פרטי מקום",
         "get_travel_time": "חישוב זמן מעבר", "check_day_load": "בדיקת עומס יומי", "get_weather": "בדיקת מזג אוויר"}
STAGES = {"intake": "בדיקת הבקשה", "catalog": "חיפוש ובדיקת חלופות בקטלוג",
          "initializing_agents": "טעינת סביבת הסוכנים", "planning": "בניית תוכנית", "trip_manager": "בחירת חבילה",
          "places": "בחירת מקומות", "itinerary": "בניית מסלול"}


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        secret = os.environ.get(name, "")
        if len(secret) > 7:
            text = text.replace(secret, "[REDACTED]")
    return json.loads(text)


def timestamp(value):
    if not value:
        return None
    date = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return date.replace(tzinfo=UTC) if date.tzinfo is None else date


def seconds(now, then):
    value = timestamp(then)
    return round(max(0, (now - value).total_seconds()), 1) if value else None


def describe(event):
    kind = event.get("kind")
    if kind == "llm_start": return "נשלחה קריאה למודל"
    if kind == "llm_end": return "התקבלה תשובת מודל"
    if kind == "llm_error": return "קריאת מודל נכשלה"
    if kind == "tool_start": return "התחילה " + TOOLS.get(event.get("tool"), event.get("tool", "קריאת כלי"))
    if kind == "tool": return "הסתיימה " + TOOLS.get(event.get("tool"), event.get("tool", "קריאת כלי"))
    if kind == "retry": return "ניסיון חוזר לאחר שגיאה"
    if kind == "stage": return STAGES.get(event.get("stage"), event.get("stage", "שלב עבודה"))
    if kind == "agent": return "הופעל סוכן: " + event.get("actor", "")
    if kind == "candidates": return f'נמצאו {event.get("count", 0):,} צירופי חבילות בתקציב'
    if kind == "checks": return "בדיקות התוכנית עברו" if event.get("passed") else "נמצאו אילוצים לתיקון"
    if kind == "rate_wait": return "Waiting for Gemini request quota"
    return str(kind or "עדכון")


def progress(slot, now=None, deadline_s=270):
    now = now or dt.datetime.now(UTC)
    events = sorted(slot.get("events", []), key=lambda e: timestamp(e.get("ts")) or dt.datetime.min.replace(tzinfo=UTC))
    calls, tool_starts, tools_done = {}, {}, set()
    recent, errors = [], []
    for index, event in enumerate(events):
        kind, call_id = event.get("kind"), str(event.get("call_id") or f"event-{index}")
        if kind in ("llm_start", "llm_end", "llm_error"):
            call = calls.setdefault(call_id, {"id": call_id, "started_at": None, "finished_at": None,
                                             "status": "running", "model": event.get("model"), "actor": event.get("actor")})
            if kind == "llm_start": call["started_at"] = event.get("ts")
            else:
                call.update(finished_at=event.get("ts"), status="failed" if kind == "llm_error" else "complete")
                if event.get("usage"):
                    call["usage"] = event["usage"]
            if event.get("error"):
                call["error"] = event["error"]
        elif kind == "tool_start": tool_starts[call_id] = event
        elif kind == "tool": tools_done.add(call_id)
        if event.get("error"): errors.append(str(event["error"]))
        recent.append(dict(time=event.get("ts"), actor=event.get("actor"), action=describe(event),
                           duration_s=event.get("duration_s"), detail=str(event.get("error") or event.get("status") or "")[:1600]))
    terminal = slot.get("state") == "complete"
    for call in calls.values():
        call["duration_s"] = seconds(timestamp(call["finished_at"]) or now, call["started_at"])
        if terminal and call["status"] == "running": call["status"] = "unfinished"
    started = [c for c in calls.values() if c["started_at"]]
    pending = [c for c in calls.values() if c["status"] == "running"]
    pending_tools = [v for k, v in tool_starts.items() if k not in tools_done]
    last = events[-1] if events else {}
    elapsed = seconds(timestamp(slot.get("finished_at")) or now, slot.get("started_at"))
    action = STAGES.get(slot.get("stage"), "המערכת פועלת")
    active_since = last.get("ts") or slot.get("started_at")
    if last.get("kind") == "rate_wait":
        action = "Waiting for Gemini request quota"
    if pending:
        action, active_since = "ממתינה לתשובת המודל", pending[-1]["started_at"]
    elif pending_tools:
        action = TOOLS.get(pending_tools[-1].get("tool"), pending_tools[-1].get("tool", "הפעלת כלי"))
        active_since = pending_tools[-1].get("ts")
    if slot.get("state") == "waiting": action = "ממתינה לתורה בהרצה"
    if terminal: action = "ההרצה הסתיימה"
    error = (slot.get("result") or {}).get("message") or slot.get("error") or (errors[-1] if errors else "")
    usages = [c.get("usage", {}) for c in calls.values() if c.get("usage")]
    inputs = [u.get("prompt_tokens", u.get("input_tokens")) for u in usages]
    outputs = [u.get("completion_tokens", u.get("output_tokens")) for u in usages]
    input_tokens = sum(inputs) if inputs and all(v is not None for v in inputs) else None
    output_tokens = sum(outputs) if outputs and all(v is not None for v in outputs) else None
    return redact(dict(state=slot.get("state"), actor=slot.get("actor"), stage=slot.get("stage"), events=len(events),
        result_status=(slot.get("result") or {}).get("status"),
        elapsed_s=elapsed, remaining_s=max(0, deadline_s - elapsed) if elapsed is not None and not terminal else None,
        current_action=action, action_elapsed_s=seconds(now, active_since) if not terminal else None,
        last_update_at=last.get("ts") or slot.get("started_at"),
        idle_s=seconds(timestamp(slot.get("finished_at")) or now, last.get("ts") or slot.get("started_at")),
        llm_started=len(started), llm_completed=sum(c["status"] == "complete" for c in calls.values()),
        llm_failed=sum(c["status"] == "failed" for c in calls.values()), llm_in_flight=len(pending),
        llm_unfinished=sum(c["status"] == "unfinished" for c in calls.values()), calls=list(calls.values()),
        tools_started=len(tool_starts), tools_completed=len(tools_done),
        tokens_in_observed=input_tokens if usages else None, tokens_out_observed=output_tokens if usages else None,
        retries=sum(e.get("kind") == "retry" for e in events),
        round=max([e.get("round", 0) or 0 for e in events] or [0]),
        recent=recent[-35:], error_detail=error))
