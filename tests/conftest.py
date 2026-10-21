import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ["WEATHER_MODE"] = "fixture"


@pytest.fixture(scope="session")
def cases():
    data = json.loads((ROOT / "eval" / "cases" / "eval_cases.json").read_text())
    return {c["id"]: c for c in data["cases"]}
