"""Verify main-notebook source refresh and shared settings without starting a server."""
import json
from pathlib import Path
from types import SimpleNamespace

from travel_agent.config import REPO_ROOT


def test_main_notebook_refreshes_new_provider_modules_and_passes_shared_settings(tmp_path, monkeypatch):
    nb = json.loads((REPO_ROOT / "notebooks/travel_streamlit_colab.ipynb").read_text(encoding="utf-8"))
    code = "".join(nb["cells"][6]["source"])
    source = tmp_path / "source"
    package = source / "src/travel_agent/systems"
    package.mkdir(parents=True)
    for filename in ("llm.py", "gemini.py", "gemini_rate_limit.py"):
        (package / filename).write_text("# Current source version\n", encoding="utf-8")
    (source / "web").mkdir()
    (source / "web/scenarios.json").write_text("[]", encoding="utf-8")
    (source / "scripts").mkdir()
    (source / "scripts/notebook_server.py").write_text("# Server entry point\n", encoding="utf-8")
    runtime = tmp_path / "runtime/project"
    captured = {}
    def start_server(project, work, **kwargs):
        captured.update(kwargs["env"])
        return None, 8501
    monkeypatch.setattr("runpy.run_path", lambda path: {"start_server": start_server})
    namespace = dict(PROJECT=runtime, PROJECT_SRC=source, SOURCE=source, SOURCE_MODE="drive",
                     WORK=runtime.parent, IN_COLAB=False)
    exec(compile(code, "main-notebook-start-cell", "exec"), namespace)
    for filename in ("llm.py", "gemini.py", "gemini_rate_limit.py"):
        assert (runtime / "src/travel_agent/systems" / filename).read_text() == "# Current source version\n"
    assert captured["LLM_RPM"] == "12" and captured["LLM_MAX_TOKENS"] == "8192"
    assert namespace["_model_env"] == {}
