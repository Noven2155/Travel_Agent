"""Start both real services with one command, from any working directory."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import webbrowser


def main():
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    development = "--dev" in sys.argv or not (root / "frontend" / "dist" / "index.html").exists()
    if development and not (root / "frontend" / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=root / "frontend", check=True)
    children = []
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "travel_agent.api:app", "--host", "127.0.0.1", "--port", "8025"], cwd=root))
        if development:
            children.append(subprocess.Popen([npm, "run", "dev", "--", "--port", "5173"], cwd=root / "frontend"))
        url = "http://localhost:5173" if development else "http://localhost:8025"
        print("\nTravel comparison workspace: " + url + "\n", flush=True)
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()
