# Travel Comparison Studio

User-approved scope: build A deterministic code, B one CrewAI agent and C three CrewAI agents, plus a Hebrew React comparison interface. This is a small course capstone, not a booking product. Retain the existing core instead of replacing agents with scripts.

UI direction: preserve the selected open white, navy and restrained-blue design. One request and one run action; detail lives under package/itinerary/evidence tabs. Never label saved or scripted results as actual agent execution.

Read-only source data: inventory.json; two cities of OSM/Wikivoyage places; cached weather. Availability and car capacity are synthetic/estimated and must stay labeled. No invented ratings.

Live runs: src/travel_agent/api.py and comparison.py; each system runs in its own process with a 270-second deadline; SQLite persists actual events and results. Same validators and inputs by default. Parallel mode is for presentation; isolated mode is for measurement. No inferred success percentages. Model configuration remains outside source; missing configuration is a visible state.

web/scenarios.json and recorded_baseline.json are built by scripts/build_demo_scenarios.py. Demo scenarios use four travelers and data-verified alternatives/no-package cases. Never feed oracle plans into systems. Changes to the request invalidate fixture proof.

Frontend: frontend/src/. Build with npm run build from frontend. Backend tests: .venv/bin/python -m pytest. A full model-free API smoke run: .venv/bin/python scripts/smoke_comparison.py. Agent wiring tests use a fake only inside tests; real-model performance needs a configured model.
