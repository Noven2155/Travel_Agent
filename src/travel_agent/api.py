"""Local Python API for the comparison workspace. Run via scripts/start.py."""
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import comparison as comparisons
from .config import CITIES, REPO_ROOT, VOCAB
from .data_access import get_catalog, get_places
from .models import TripRequest
from .systems.llm import availability, settings

app = FastAPI(title="Travel Comparison API", version="1.0.0")
origins = os.environ.get("TRAVEL_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173,http://terminal.local:4173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


class Pricing(BaseModel):
    input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float | None = Field(default=None, ge=0)


class ComparisonInput(BaseModel):
    request: TripRequest
    request_text: str = Field(default="", max_length=6000)
    title: str = Field(default="בקשה אישית", max_length=150)
    mode: Literal["demo_parallel", "benchmark_isolated"] = "demo_parallel"
    input_mode: Literal["structured", "natural"] = "structured"
    pricing: Pricing = Field(default_factory=Pricing)


@app.get("/api/health")
def health():
    ok, reason = availability()
    catalog = get_catalog()
    return dict(api="ready", llm_ready=ok, llm_message=reason, model=settings()["model"],
                counts=dict(flights=len(catalog.flights), stays=len(catalog.stays), cars=len(catalog.cars),
                            places=sum(len(get_places(c).rows) for c in CITIES)),
                input_modes=["structured", "natural"], active=comparisons.ACTIVE_LOCK.locked())


@app.get("/api/scenarios")
def scenarios():
    return json.loads((REPO_ROOT / "web" / "scenarios.json").read_text())


@app.get("/api/catalog")
def catalog():
    cat = get_catalog()
    return dict(cities=list(CITIES), origins=cat.origins, interests=VOCAB, first=cat.dates[0], last=cat.dates[-1])


@app.post("/api/comparisons", status_code=202)
def create_comparison(body: ComparisonInput):
    if body.input_mode == "natural" and not body.request_text.strip():
        raise HTTPException(422, "Natural input mode requires request_text")
    try:
        return comparisons.start(body.request.model_dump(mode="json"), body.request_text, body.title,
                                 body.mode, body.input_mode, body.pricing.model_dump())
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/comparisons")
def list_comparisons():
    return comparisons.history()


@app.get("/api/comparisons/{comparison_id}")
def get_comparison(comparison_id: str):
    result = comparisons.get(comparison_id)
    if not result:
        raise HTTPException(404, "Comparison not found")
    return result


@app.get("/api/comparisons/{comparison_id}/export")
def export_comparison(comparison_id: str):
    data = get_comparison(comparison_id)
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="comparison-{comparison_id}.json"'})


class ModelSettings(BaseModel):
    provider: Literal["ollama", "gemini", "openai"]
    model: str = Field(min_length=1, max_length=150, pattern=r"^[a-zA-Z0-9:._/\-]+$")
    api_key: str = Field(default="", max_length=1000)


@app.post("/api/model")
def configure_model(body: ModelSettings):
    # Local service only. Credentials remain in RAM and never enter results or the database.
    if comparisons.ACTIVE_LOCK.locked():
        raise HTTPException(409, "Wait for the active comparison before changing the model")
    if body.provider != "ollama" and not body.api_key.strip():
        raise HTTPException(422, "An API key is required")
    os.environ["LLM_MODEL"] = f"{body.provider}/{body.model.removeprefix(body.provider + '/')}"
    if body.provider == "ollama":
        os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
    else:
        os.environ.pop("OLLAMA_HOST", None)
        os.environ["GEMINI_API_KEY" if body.provider == "gemini" else "OPENAI_API_KEY"] = body.api_key.strip()
    return health()


@app.get("/api/summary")
def summary():
    rows = comparisons.history(1000)
    totals = {}
    for system in comparisons.SYSTEMS:
        measured = []
        for row in rows:
            if row["mode"] != "benchmark_isolated" or row["status"] != "complete":
                continue
            slot = comparisons.get(row["id"])["runs"][system]
            result = slot.get("result", {})
            if result.get("status") in ("TECHNICAL_ERROR", "TIMEOUT"):
                # Timeouts ARE failures; missing model configuration is reported separately below.
                if result.get("status") == "TECHNICAL_ERROR" and "LLM not available" in result.get("message", ""):
                    continue
            measured.append(slot.get("metrics", {}))
        totals[system] = dict(n=len(measured), valid_plans=sum(m.get("valid_plan", False) for m in measured),
                              valid_plan_rate=(sum(m.get("valid_plan", False) for m in measured)/len(measured)) if measured else None)
    return dict(systems=totals, explanation="Observed isolated runs only; no comparative advantage is presumed.")


# A prebuilt React bundle is included in the release ZIP. End users need only Python;
# Node/Vite are required for frontend development, not for running that release.
from fastapi.staticfiles import StaticFiles

ui_dist = REPO_ROOT / "frontend" / "dist"
if ui_dist.is_dir():
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="comparison-ui")
