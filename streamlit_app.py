"""Entry point: python -m streamlit run streamlit_app.py"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from travel_agent.streamlit_view import main

main(ROOT)
