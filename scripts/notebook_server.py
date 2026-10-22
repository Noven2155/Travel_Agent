"""Start a private notebook server with bounded startup and Colab proxy options."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
import urllib.request


def start_server(project, work, *, previous=None, env=None, colab=False):
    if previous is not None and previous.poll() is None:
        previous.terminate()
        try:
            previous.wait(timeout=5)
        except subprocess.TimeoutExpired:
            previous.kill()
            previous.wait(timeout=3)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    project, work = Path(project), Path(work)
    log_path = work / "streamlit.log"
    command = [sys.executable, "-m", "streamlit", "run", str(project / "streamlit_app.py"),
               "--server.port", str(port), "--server.address", "127.0.0.1", "--server.headless", "true",
               "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]
    if colab:
        # Only the authenticated Colab proxy exposes this loopback server. Its
        # cross-origin iframe cannot reliably supply Streamlit's XSRF cookie.
        command += ["--server.enableCORS", "false", "--server.enableXsrfProtection", "false",
                    "--server.enableWebsocketCompression", "false"]
    server_env = dict(os.environ, OTEL_SDK_DISABLED="true", CREWAI_DISABLE_TELEMETRY="true")
    server_env.update(env or {})
    print("פותחת את שרת הממשק…", flush=True)
    with log_path.open("w") as handle:
        process = subprocess.Popen(command, cwd=project, env=server_env, stdout=handle,
                                   stderr=subprocess.STDOUT)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    next_status = 3
    try:
        while time.monotonic() - started < 30:
            if process.poll() is not None:
                raise RuntimeError("שרת הממשק נעצר לפני פתיחת החיבור.")
            try:
                with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=.5) as response:
                    if response.status == 200:
                        print(f"השרת מוכן אחרי {time.monotonic() - started:.1f} שניות. כעת נפתחת מסגרת התצוגה.", flush=True)
                        return process, port
            except OSError:
                pass
            elapsed = time.monotonic() - started
            if elapsed >= next_status:
                print(f"ממתינה לפתיחת השרת · {elapsed:.0f} שניות", flush=True)
                next_status += 3
            time.sleep(.2)
        raise TimeoutError("השרת לא נפתח בתוך 30 שניות.")
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        details = log_path.read_text(errors="replace")[-2500:]
        for name in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
            secret = server_env.get(name, "")
            if len(secret) > 7:
                details = details.replace(secret, "[REDACTED]")
        if details:
            print(details, flush=True)
        raise
