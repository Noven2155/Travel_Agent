"""Per-run tool-call log. Every tool output carries call_id/source/license/data_date and is stored here,
so grounding is a code check over the log (instructor feedback #3)."""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Optional


class ToolLog:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._n = 0
        self.actor: str = "code"          # who is calling: code / agent name (set by the systems)

    def new_call_id(self, tool: str) -> str:
        with self._lock:
            self._n += 1
            return f"{tool}#{self._n:03d}"

    def record(self, call_id: str, tool: str, args: dict[str, Any], output: dict[str, Any]) -> None:
        with self._lock:
            self.entries.append(dict(call_id=call_id, tool=tool, actor=self.actor, args=args,
                                     ts=dt.datetime.now().isoformat(timespec="milliseconds"), output=output))

    def get(self, call_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not call_id:
            return None
        return next((e for e in self.entries if e["call_id"] == call_id), None)

    def by_tool(self, tool: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e["tool"] == tool]

    def dump(self) -> list[dict[str, Any]]:
        return json.loads(json.dumps(self.entries, default=str))

    def save(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.dump(), ensure_ascii=False, indent=1, default=str))
        return str(path)
