"""Internal managed-preview adapter. The same FastAPI routes and real comparison workers run here."""
import json
import os
from pathlib import Path
import time

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")


def main():
    from fastapi.testclient import TestClient
    from travel_agent.api import app
    from travel_agent.config import REPO_ROOT
    queue = REPO_ROOT / "frontend" / "runtime" / "preview-queue"
    queue.mkdir(parents=True, exist_ok=True)
    print("Comparison preview adapter ready", flush=True)
    with TestClient(app) as client:
        while True:
            for request_path in queue.glob("*.request.json"):
                try:
                    request = json.loads(request_path.read_text())
                    response = client.request(request["method"], request["path"], content=request.get("body", ""),
                                              headers={"content-type": "application/json"})
                    data = dict(status=response.status_code, body=response.text)
                except Exception:
                    data = dict(status=503, body=json.dumps({"detail": "Python request failed"}))
                target = request_path.with_name(request_path.name.replace(".request.json", ".response.json"))
                tmp = target.with_suffix(".tmp")
                tmp.write_text(json.dumps(data))
                tmp.replace(target)
                request_path.unlink(missing_ok=True)
            time.sleep(0.04)


if __name__ == "__main__":
    main()
