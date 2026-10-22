"""Bounded notebook installation with live status, diagnostics and cancellation."""
from __future__ import annotations

from pathlib import Path
import os
import re
import signal
import subprocess
import sys
import time


def _tail(path, lines=1):
    with Path(path).open("rb") as handle:
        handle.seek(max(0, Path(path).stat().st_size - 8000))
        text = handle.read().decode("utf-8", errors="replace")
    text = re.sub(r"https?://\S+", "[כתובת הורדה]", text)
    return "\n".join(text.splitlines()[-lines:])


def _stop(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)


def run_logged(command, log_path, *, timeout_s=600, report_every_s=10):
    """Return after success; never leave a silent or orphaned installer."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    next_report = 0
    print("מתחילה התקנת הספריות. תוצג התקדמות כל עשר שניות.", flush=True)
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=(os.name == "posix"))
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= timeout_s:
                    raise TimeoutError("ההתקנה עברה את מגבלת הזמן ונעצרה. השורות האחרונות:\n" + _tail(log_path, 15))
                if elapsed >= next_report:
                    last = _tail(log_path)[-200:]
                    print(f"חלפו {elapsed:.0f} שניות · " + (last or "מאתרת את הספריות הנדרשות…"), flush=True)
                    next_report = elapsed + report_every_s
                time.sleep(min(.25, max(.01, report_every_s)))
            if process.returncode:
                raise RuntimeError("ההתקנה נכשלה. השגיאה האחרונה:\n" + _tail(log_path, 20))
        except BaseException:
            _stop(process)
            raise
    print(f"הספריות הותקנו בהצלחה בתוך {time.monotonic() - started:.0f} שניות. אפשר לעבור לתא פתיחת הממשק.", flush=True)


def install(requirements, log_path):
    command = [sys.executable, "-u", "-m", "pip", "install", "--disable-pip-version-check",
               "--progress-bar", "off", "--prefer-binary", "--timeout", "30", "--retries", "1",
               "-r", str(requirements)]
    return run_logged(command, log_path)
