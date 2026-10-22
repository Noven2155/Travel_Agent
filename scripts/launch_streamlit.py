"""Create an isolated local UI environment and open Streamlit in the browser."""
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (3, 10) <= sys.version_info[:2] < (3, 14):
        raise SystemExit("Install Python 3.12, then open START_STREAMLIT.bat again.")
    folder = ROOT / ".streamlit-venv"
    python = folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(folder)
    requirements = ROOT / "requirements-streamlit.txt"
    marker = folder / ".travel-requirements"
    content = requirements.read_text()
    if not marker.is_file() or marker.read_text() != content:
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True)
        marker.write_text(content)
    raise SystemExit(subprocess.call([str(python), "-m", "streamlit", "run", str(ROOT / "streamlit_app.py")], cwd=ROOT))


if __name__ == "__main__":
    main()
