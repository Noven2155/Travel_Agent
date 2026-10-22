"""Community Cloud entry point; its requirements override legacy UI requirements."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), run_name="__main__")
