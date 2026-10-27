# Travel Agent — Comparing Three Trip Planning Systems

[Hebrew README](README.md)

A capstone project for the BIU DS23 Agentic AI course, Team 8. The project compares three approaches to planning a short group trip in **Chicago or New York**: selecting flights, accommodation and an optional rental car, then building a daily itinerary around budget, dates, group size and preferences. It recommends plans; it does not make bookings or process payments.

## Systems and comparison rules

| System | Run ID | Implementation |
|---|---|---|
| **A — Rules** | `rules` | Deterministic search, pricing, ranking and scheduling. `rules_strong.py` is the default; `rules_basic` remains a reference variant. No LLM. |
| **B — Single agent** | `single` | One CrewAI TripPlanner with all eight shared tools. |
| **C — Multi-agent** | `multi` | Exactly three CrewAI agents: **Trip Manager → Places → Itinerary**, coordinated by a Flow with code-based validation and repair routing. |

The systems use the same catalog, shared tools, approved constraints and final checks. B and C use the same model and generation settings. Each system has **at most three planning rounds in total and a 270-second process deadline**. Model calls and provider/guardrail retries may exceed three; their time counts toward the deadline. No GM or reviewer agent is part of the approved scope.

Use isolated execution for measurement; parallel execution is available for presentation. Multi-agent performance benefits are a hypothesis to test.

## Quick start

### Google Colab

1. Open the [main Streamlit notebook](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_streamlit_colab.ipynb).
2. Add `GEMINI_API_KEY` to **Colab Secrets** and enable **Notebook access**. Keep the key out of notebook cells, chat messages and Git.
3. Select **Runtime → Run all**, then choose a scenario in the interface and run the comparison. No GPU is required. System A can run without a model key.

The default source is GitHub (`main`). Optional Drive mode reads your existing `travel/project` and `travel/data` folders; it does not update them from GitHub. Export results before the temporary Colab runtime ends.

### Local Streamlit

Python 3.10–3.13 is required; local and Colab checks have used Python 3.12/3.13. Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-streamlit.txt
python -m streamlit run streamlit_app.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. Configure Gemini through the interface or environment variables. `.env.example` documents configuration; `.env` and `.streamlit/secrets.toml` are ignored by Git.

### React and FastAPI

With Node.js 20+ and the Python environment activated:

```bash
python -m pip install -e ".[agents,api,dev]"
python scripts/start.py
```

The API uses port 8025. The launcher starts Vite when a frontend build is unavailable; `--dev` explicitly selects development mode. Build manually with `npm install` and `npm run build` inside `frontend/`. The generated `frontend/dist` folder is not committed.

## Real-model execution evidence

The [dedicated B/C proof notebook](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_task2_bc_colab.ipynb) runs both systems sequentially on the existing Chicago scenario, S01. It exports the approved input, model/settings, package versions, source/data hashes, outputs, tool/model events, timing and repeated final checks in a downloadable ZIP.

Current proof settings: Gemini `gemini-3.1-flash-lite`, temperature 0, seed 42, output limit 8,192 tokens, HTTP timeout 60 seconds and shared local pacing of 12 requests per minute. Provider-directed cooldowns count toward the system deadline. A shared seed does not guarantee deterministic responses, and local pacing cannot account for other applications using the same provider project.

### Status — October 27, 2026

- **Two real runs:** C returned `OK_PLAN` in one round both times (74.906 and 106.076 seconds); all 10 existing plan checks passed. B first stopped on request-quota errors (429), then reached the 270-second deadline after plan-validation failures. No 429 errors were observed in the second run.
- B now uses a single-agent structured Task/Crew path, full repair feedback and logged evidence. Interrupted runs retain draft plans, tool logs and observed counters. The main notebook uses this shared runtime. **The latest changes still require real-model verification. Task 2 remains open.**
- The old timeout export zeroed B's counters and omitted identity fields, despite the second run containing 28 completed model responses. Original evidence is retained; the reporting defect is fixed for future runs.
- Manual review found meals lasting 75–90 minutes despite the 60-minute instruction. Existing validators did not detect this. All scenario dates were outside the forecast horizon; rainy-day scheduling was not verified.
- **139 local tests passed.** Scripted LLM and simulated SDK/process tests are local checks. They do not prove Gemini success, and no general quality or speed advantage has been established.

See the [latest report](docs/TASK2_SECOND_RUN_HE.md), [first-run report](docs/TASK2_FIRST_RUN_HE.md) and [second-run evidence](evidence/task2/20261027T141444Z/). Reports are in Hebrew; execution records are JSON.

## Data and limitations

The planners read the historical catalog in `data/inventory.json`, local place catalogs and weather fixtures. Flight records originate from Expedia/Kaggle; lodging from Inside Airbnb; rental-car data from Cornell; places from OpenStreetMap/Wikivoyage; weather fixtures from Open-Meteo.

Lodging/car availability includes simulation, car capacity is estimated, and travel/visit durations may be estimates. Synthetic place ratings are not genuine reviews. Package prices exclude unrecorded fees, meals and attraction tickets. Historical and simulated records must not be presented as current bookable offers. Full provenance and limitations are in [data/README.md](data/README.md).

## Repository guide

| Path | Purpose |
|---|---|
| `src/travel_agent/` | Models, shared tools/checks, systems A/B/C, orchestration, API and Streamlit |
| `notebooks/`, `scripts/` | Colab entry points, launchers and execution helpers |
| `frontend/`, `web/` | Hebrew RTL React interface and shared scenario definitions |
| `data/` | Working catalog, places, weather and source documentation |
| `eval/`, `tests/` | Evaluation cases/reports and automated tests |
| `evidence/`, `docs/` | Run evidence, scope, specifications and handoff documents |
| `archive/` | Historical material outside the active implementation |

For tests and the model-free API smoke check, install development/API dependencies in addition to the Streamlit requirements:

```bash
python -m pip install -e ".[api,dev]"
python -m pytest -q
python scripts/smoke_comparison.py
python -m eval.run_eval --help
```

Raw evaluation runs under `eval/results/` are ignored by Git; reports live under `eval/reports/`. Saved fixtures and model-free smoke results must not be labeled as live agent execution.

Team: **Ran, Galit, Shmuel and Daniel**. See the [approved scope and responsibilities](docs/TEAM_SCOPE_HE.md) and [active agent specifications](docs/agent_specs/README.md).
