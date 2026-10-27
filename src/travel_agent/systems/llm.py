"""LLM configuration for systems B and C (same model, temperature=0, same max_tokens/seed for both).

Configured only through environment variables (see .env.example). Zero-cost options only:
  * default: local model through Ollama   (LLM_MODEL=ollama/qwen2.5:7b-instruct, OLLAMA_HOST=http://localhost:11434)
  * optional: a free-tier provider, e.g. LLM_MODEL=gemini/gemini-2.0-flash (+ GEMINI_API_KEY, native in CrewAI) or
    LLM_MODEL=groq/llama-3.3-70b-versatile (+ GROQ_API_KEY, routed through LiteLLM: pip install litellm)
Keys are never committed. If no LLM is reachable, B/C return TECHNICAL_ERROR with a clear message.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Optional

_LLM_FACTORY = None   # tests can inject a fake LLM factory: callable(role:str) -> BaseLLM


def set_llm_factory(factory) -> None:
    global _LLM_FACTORY
    _LLM_FACTORY = factory


def load_dotenv(path: Optional[Path] = None) -> None:
    """Minimal .env loader (no extra dependency). Existing environment variables win."""
    from ..config import REPO_ROOT
    p = path or REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def settings() -> dict[str, Any]:
    load_dotenv()
    return dict(model=os.environ.get("LLM_MODEL", "ollama/qwen2.5:7b-instruct"),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0")),
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2048")),
                seed=int(os.environ.get("LLM_SEED", "42")),
                base_url=os.environ.get("OLLAMA_HOST") or os.environ.get("LLM_BASE_URL"),
                timeout=float(os.environ.get("LLM_TIMEOUT_S", "120")),
                rpm=float(os.environ.get("LLM_RPM", "12")))


def availability() -> tuple[bool, str]:
    """Cheap pre-flight check so the harness never hangs on a missing LLM."""
    if _LLM_FACTORY is not None:
        return True, "injected LLM factory"
    s = settings()
    model = s["model"]
    provider = model.split("/", 1)[0] if "/" in model else "openai"
    try:
        import crewai  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"crewai is not installed ({e}); pip install -r requirements.txt"
    if provider in ("ollama", "ollama_chat"):
        host = (s["base_url"] or "http://localhost:11434").rstrip("/").removesuffix("/v1")
        try:
            with urllib.request.urlopen(host + "/api/tags", timeout=2) as r:
                tags = json.loads(r.read())
            names = [m.get("name", "") for m in tags.get("models", [])]
            want = model.split("/", 1)[1]
            if not any(n == want or n.split(":")[0] == want.split(":")[0] for n in names):
                return False, f"Ollama is running at {host} but model '{want}' is not pulled (ollama pull {want})"
            return True, f"Ollama at {host}, model {want}"
        except Exception as e:  # noqa: BLE001
            return False, f"LLM not available: no Ollama server at {host} ({type(e).__name__}). Install Ollama and run " \
                          f"'ollama pull {model.split('/', 1)[1]}', or set LLM_MODEL to a free-tier provider in .env"
    key_env = {"gemini": "GEMINI_API_KEY", "google": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY",
               "cerebras": "CEREBRAS_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider)
    if key_env and not os.environ.get(key_env):
        return False, f"LLM not available: {key_env} is not set for model {model}"
    if provider == "groq":
        try:
            import litellm  # noqa: F401
        except Exception:  # noqa: BLE001
            return False, "LLM not available: groq/* models are routed through LiteLLM (pip install litellm)"
    return True, f"model {model}"


def make_llm(role: str = "default"):
    if _LLM_FACTORY is not None:
        return _LLM_FACTORY(role)
    from crewai import LLM
    s = settings()
    kw: dict[str, Any] = dict(model=s["model"], temperature=s["temperature"], max_tokens=s["max_tokens"], seed=s["seed"],
                              timeout=s["timeout"])
    if s["model"].split("/", 1)[0] in ("gemini", "google"):
        from .gemini import ConfiguredGeminiCompletion
        return ConfiguredGeminiCompletion(
            model=s["model"].split("/", 1)[1], provider="gemini",
            temperature=s["temperature"], max_tokens=s["max_tokens"],
            max_output_tokens=s["max_tokens"], seed=s["seed"],
            api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            client_params={"http_options": {"timeout": int(s["timeout"] * 1000), "retry_options": {"attempts": 1}}},
            requests_per_minute=s["rpm"],
            thinking_config={"include_thoughts": False},
        )
    if s["base_url"] and s["model"].startswith("ollama"):
        kw["base_url"] = s["base_url"].rstrip("/") + ("" if s["base_url"].rstrip("/").endswith("/v1") else "/v1")
    elif s["base_url"]:
        kw["base_url"] = s["base_url"]
    return LLM(**kw)


def usage_of(llm) -> tuple[int, int, int]:
    """(calls, prompt_tokens, completion_tokens) cumulative for this LLM instance."""
    try:
        u = llm.get_token_usage_summary()
        return int(u.successful_requests), int(u.prompt_tokens), int(u.completion_tokens)
    except Exception:  # noqa: BLE001
        return 0, 0, 0
