"""Private subprocess entry point for the Streamlit UI. Credentials stay in env."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


def emit(kind, **data):
    from .monitoring import redact
    print("TRAVEL_UI " + json.dumps(redact(dict(kind=kind, **data)), ensure_ascii=False), flush=True)


def main():
    from . import comparison as comparison
    from .models import TripRequest
    from .monitoring import progress

    body = json.load(sys.stdin)
    req = TripRequest.model_validate(body["request"])
    if body.get("only_rules"):
        from .systems import run
        from .events import sink
        slot = dict(state="running", started_at=comparison.utc_now(), events=[])
        last_sent = [0.]
        def observe(event):
            if event.get("kind") in ("checkpoint", "tool_record"):
                return
            slot["events"].append(dict(ts=comparison.utc_now(), **event))
            if event.get("stage"): slot["stage"] = event["stage"]
            if time.monotonic() - last_sent[0] > .3:
                emit("progress", systems={"rules": progress(slot)})
                last_sent[0] = time.monotonic()
        token = sink.set(observe)
        result = run("rules", req).model_dump(mode="json")
        sink.reset(token)
        slot.update(state="complete", finished_at=comparison.utc_now(), result=result,
                    metrics=comparison.metrics(result, body.get("pricing") or {}))
        slot["monitoring"] = progress(slot)
        data = dict(id=body["id"], title=body["title"], status="complete", mode="baseline_check",
                    input_mode="structured", model="not_used", request=req.model_dump(mode="json"),
                    request_text=body["request_text"], runs={"rules": slot})
        emit("progress", systems={"rules": slot["monitoring"]}, completed={"rules": slot})
    else:
        data = comparison.start(req.model_dump(mode="json"), body["request_text"], body["title"],
                                body["mode"], body["input_mode"], body.get("pricing"))
        previous, last_sent, delivered = None, 0., set()
        while True:
            data = comparison.get(data["id"])
            signature = [(k, s["state"], len(s.get("events", []))) for k, s in data["runs"].items()]
            if signature != previous or time.monotonic() - last_sent >= 1:
                snapshot = {key: progress(slot) for key, slot in data["runs"].items()}
                completed = {key: slot for key, slot in data["runs"].items() if slot["state"] == "complete" and key not in delivered}
                emit("progress", systems=snapshot, completed=completed, comparison_id=data["id"])
                delivered.update(completed)
                previous, last_sent = signature, time.monotonic()
            if data["status"] == "complete":
                break
            time.sleep(.3)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(name, "")
        if len(secret) > 7:
            text = text.replace(secret, "[REDACTED]")
    Path(body["output_path"]).write_text(text, encoding="utf-8")
    emit("complete")


if __name__ == "__main__":
    main()
