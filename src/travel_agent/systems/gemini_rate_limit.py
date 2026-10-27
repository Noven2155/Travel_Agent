"""Coordinate local Gemini request pacing and provider-specified cooldowns."""
from __future__ import annotations

from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import re
import sqlite3
import time
from pathlib import Path


class RateLimiter:
    """One model bucket shared by the local B/C worker processes; no credentials stored."""

    def __init__(self, path: Path, model: str, rpm: float, observe=None):
        if not 0 < rpm <= 60000:
            raise ValueError("LLM_RPM must be positive and at most 60000.")
        self.path, self.model, self.rpm, self.observe = Path(path), model, rpm, observe
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS pacing (model TEXT PRIMARY KEY, next_at REAL NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def acquire(self) -> None:
        while True:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT next_at FROM pacing WHERE model=?", (self.model,)).fetchone()
                now = time.time()
                wait = max(0., (row[0] if row else now) - now)
                if wait <= 0:
                    db.execute("INSERT OR REPLACE INTO pacing VALUES (?, ?)", (self.model, now + 60 / self.rpm + .05))
                db.commit()
            if wait <= 0:
                return
            if self.observe:
                self.observe(dict(kind="rate_wait", actor="model", model=self.model, seconds=round(wait, 3)))
            time.sleep(min(wait, 10.))

    def defer(self, delay: float) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT next_at FROM pacing WHERE model=?", (self.model,)).fetchone()
            next_at = max(row[0] if row else 0., time.time() + delay + 1.)
            db.execute("INSERT OR REPLACE INTO pacing VALUES (?, ?)", (self.model, next_at))
            db.commit()


def retry_delay(exc: Exception) -> float | None:
    """Honor RetryInfo/Retry-After; daily or zero quotas require external action."""
    if getattr(exc, "code", None) != 429:
        return None
    payload = getattr(exc, "details", {})
    body = payload.get("error", payload) if isinstance(payload, dict) else {}
    details = body.get("details", [])
    for detail in details:
        for violation in detail.get("violations", []):
            quota_id = str(violation.get("quotaId", "")).lower()
            if "perday" in quota_id or str(violation.get("quotaValue")) == "0":
                return None
    delays = []
    for detail in details:
        value = detail.get("retryDelay")
        if isinstance(value, dict):
            delays.append(float(value.get("seconds", 0)) + float(value.get("nanos", 0)) / 1e9)
        elif isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?s", value):
            delays.append(float(value[:-1]))
    response = getattr(exc, "response", None)
    value = getattr(response, "headers", {}).get("retry-after")
    if value:
        try:
            delays.append(float(value))
        except ValueError:
            try:
                delays.append(parsedate_to_datetime(value).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    if not delays:
        match = re.search(r"retry in\s+(\d+(?:\.\d+)?)(ms|s)", str(getattr(exc, "message", "")), re.I)
        if match:
            delays.append(float(match[1]) / (1000 if match[2].lower() == "ms" else 1))
    return max(1., *delays) if delays else 60.
