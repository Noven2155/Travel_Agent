"""Session-isolated UI jobs using the existing comparison engine and validators."""
from __future__ import annotations

import copy
import csv
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


LABELS = {"rules": "A · קוד", "single": "B · סוכן יחיד", "multi": "C · שלושה סוכנים"}


def locate_data(root: Path) -> Path:
    candidates = [os.environ.get("TRAVEL_DATA_DIR"), root / "data", root.parent / "data"]
    for item in candidates:
        if item and (Path(item) / "inventory.json").is_file():
            return Path(item).absolute()
    raise FileNotFoundError("לא נמצאה תיקיית data. שמרי את תיקיות project ו־data יחד בתוך travel.")


def metric_rows(data):
    rows = []
    for key, label in LABELS.items():
        slot = data.get("runs", {}).get(key)
        if not slot:
            rows.append(dict(system=key, system_name=label, status="NOT_RUN", valid_plan=None))
            continue
        result = slot.get("result") or {}
        row = dict(system=key, system_name=label, status=result.get("status"), **slot.get("metrics", {}))
        if row["status"] == "TECHNICAL_ERROR" and not row.get("llm_calls"):
            row["model_execution"] = "not_confirmed"
        rows.append(row)
    return rows


def metrics_csv(results):
    rows = [dict(comparison_id=r["id"], scenario=r["title"], **row) for r in results for row in metric_rows(r)]
    if not rows:
        return b""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=sorted({k for row in rows for k in row}))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


class ComparisonJob:
    """One viewer's job; no Streamlit calls or shared environment mutation."""

    def __init__(self, project: Path, data_dir: Path):
        self.project = Path(project).absolute()
        self.data_dir = Path(data_dir).absolute()
        self.workspace = Path(tempfile.mkdtemp(prefix="travel_streamlit_"))
        self._lock = threading.Lock()
        self._state = dict(state="idle", progress={}, result=None, error=None, partial=None)
        self._thread = None
        self._process = None
        self._cancel = threading.Event()
        self.results = []

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self, *, request, request_text, title, credentials=None, mode="demo_parallel",
              input_mode="structured", pricing=None, only_rules=False):
        with self._lock:
            if self._state["state"] == "running":
                raise RuntimeError("ההשוואה הקודמת עדיין פועלת.")
            self._state = dict(state="running", progress={}, result=None, error=None, started=time.monotonic(),
                partial=dict(id="pending", title=title, mode=mode, input_mode=input_mode, runs={}))
        self._cancel.clear()
        body = dict(id=str(uuid.uuid4()), request=copy.deepcopy(request), request_text=request_text, title=title,
                    mode=mode, input_mode=input_mode, pricing=pricing or {}, only_rules=only_rules)
        self._thread = threading.Thread(target=self._run, args=(body, dict(credentials or {})), daemon=True)
        self._thread.start()

    def _prepare_data(self):
        # Only catalog inputs are staged. CSV exports remain available in the data browser.
        for source in [self.data_dir / "inventory.json", *sorted((self.data_dir / "places").glob("*.csv")),
                       *sorted((self.data_dir / "weather").glob("*.json"))]:
            target = self.workspace / "data" / source.relative_to(self.data_dir)
            if not target.exists() or (target.stat().st_size, target.stat().st_mtime_ns) != (source.stat().st_size, source.stat().st_mtime_ns):
                target.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(source, target)

    def _run(self, body, credentials):
        try:
            self._prepare_data()
            output = self.workspace / (body["id"] + ".json")
            body["output_path"] = str(output)
            env = dict(os.environ)
            env.update(LLM_MODEL="openai/__MODEL_NOT_CONFIGURED__", GEMINI_API_KEY="", OPENAI_API_KEY="")
            env.update(credentials)
            env.update(TRAVEL_AGENT_ROOT=str(self.workspace), TRAVEL_RUNTIME_DIR=str(self.workspace / "runtime"),
                       PYTHONPATH=str(self.project / "src"), PYTHONIOENCODING="utf-8", WEATHER_MODE="fixture",
                       CREWAI_DISABLE_TELEMETRY="true", OTEL_SDK_DISABLED="true")
            env.setdefault("LLM_TIMEOUT_S", "60")
            env.setdefault("LLM_MAX_TOKENS", "4096")
            diagnostic = self.workspace / (body["id"] + ".log")
            with diagnostic.open("w", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-m", "travel_agent.ui_worker"], cwd=self.project,
                    env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
                    bufsize=1, start_new_session=(os.name == "posix"))
                with self._lock:
                    self._process = process
                if self._cancel.is_set():
                    self._terminate(process)
                else:
                    process.stdin.write(json.dumps(body, ensure_ascii=False))
                    process.stdin.close()
                    for line in process.stdout:
                        if line.startswith("TRAVEL_UI "):
                            event = json.loads(line[len("TRAVEL_UI "):])
                            if event["kind"] == "progress":
                                with self._lock:
                                    self._state["progress"] = event["systems"]
                                    self._state["partial"]["id"] = event.get("comparison_id", body["id"])
                                    self._state["partial"]["runs"].update(event.get("completed", {}))
                code = process.wait(timeout=10)
            if self._cancel.is_set():
                with self._lock:
                    self._state.update(state="cancelled", error=None)
                return
            if code or not output.is_file():
                raise RuntimeError("ההרצה נעצרה. בדקי שהספריות הותקנו ושפרטי הבקשה תקינים.")
            result = json.loads(output.read_text(encoding="utf-8"))
            with self._lock:
                self.results.append(result)
                self._state.update(state="complete", result=result, partial=result,
                                   progress={key: slot.get("monitoring", self._state["progress"].get(key, {}))
                                             for key, slot in result.get("runs", {}).items()})
        except Exception as exc:
            with self._lock:
                self._state.update(state="cancelled" if self._cancel.is_set() else "error",
                                   error=None if self._cancel.is_set() else str(exc))
        finally:
            with self._lock:
                self._process = None

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # The worker can finish between poll() and killpg().
        else:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)

    def cancel(self):
        self._cancel.set()
        with self._lock:
            process = self._process
        if process:
            self._terminate(process)

    def wait(self, timeout=60):
        if self._thread:
            self._thread.join(timeout)
        return self.snapshot()
