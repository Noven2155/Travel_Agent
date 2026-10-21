"""LLM-as-judge for free-text plans (eval v3, second evaluation layer; the deterministic key-requirement score in
keyreq.py is the first). Not run in tests or in this commit with a real model.

    python -m eval.judge <results dir> [--out FILE.jsonl] [--limit N]

* One plan per call, temperature 0, short rubric: every criterion scored 1-5 with a one-sentence justification.
* The judge sees a COMPACT summary (summarize(): request text, chosen package + price, day-by-day time / place /
  kind / category, trade-off text; ~1k tokens), never the ~170 KB raw result. It does not see the hidden gold.
* The judge model must differ from the agents' model: JUDGE_MODEL in .env (refuses to run if it equals LLM_MODEL,
  unless JUDGE_ALLOW_SAME_MODEL=1). Budget: ~80 judgments x ~1.8k tokens = ~150k tokens (fits free tiers).
* Calibration: the team blind-rates ~20 of the same summaries with the same rubric (judge_calibration.csv) and we
  report agreement (Spearman / mean absolute difference) before using judge scores.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from . import __name__ as _pkg  # noqa: F401
from travel_agent import config as C  # noqa: E402
from travel_agent.timeutil import iso_local_hm  # noqa: E402

from .quality import _facts, _places  # noqa: E402

RUBRIC = {
    "request_fit": "Does the plan honor what the traveler asked for (explicit and implied needs, negations, priorities)?",
    "itinerary_quality": "Is the day-by-day plan sensible (realistic times, variety, not empty, not overloaded, fits the party)?",
    "honesty": "Does the plan say clearly what it could not do or had to trade off, without claiming things it did not do?",
    "overall": "Overall, would this traveler be satisfied with this plan as a first proposal?",
}
JUDGE_PROMPT = """You are an impartial evaluator of travel plans. Score the plan below against the traveler's request.
For EACH criterion give an integer score 1-5 (1 = very poor, 3 = acceptable, 5 = excellent) and ONE short sentence of
justification. Judge only from the request text and the plan summary. Answer with ONE JSON object only:
{"request_fit": {"score": n, "why": "..."}, "itinerary_quality": {...}, "honesty": {...}, "overall": {...}}
Criteria:
%(criteria)s

%(summary)s
"""


class Score(BaseModel):
    score: int = Field(ge=1, le=5)
    why: str = Field(max_length=400)


class Judgment(BaseModel):
    request_fit: Score
    itinerary_quality: Score
    honesty: Score
    overall: Score


def summarize(rec: dict[str, Any], request_text: Optional[str] = None, max_items_per_day: int = 8) -> str:
    """Compact, model-agnostic plan summary (~<1k tokens)."""
    text = request_text or (rec.get("request") or {}).get("request_text") or (rec.get("case") or {}).get("request_text") or ""
    lines = ["REQUEST: " + text.strip(), f"STATUS: {rec.get('status')}" + (f" ({rec.get('message')[:160]})" if rec.get("message") else "")]
    pkg = rec.get("package")
    if pkg:
        fo, fb, st = pkg.get("flight_out") or {}, pkg.get("flight_back") or {}, pkg.get("stay") or {}
        lines.append(f"PACKAGE: total ${pkg['total']:.2f}"
                     + (f" for {(rec.get('request') or {}).get('travelers')} traveler(s)" if rec.get("request") else ""))
        if fo:
            lines.append(f"  outbound {fo.get('date')} dep {iso_local_hm(fo['dep'])} arr {iso_local_hm(fo['arr'])} {'nonstop' if not fo.get('stops') else 'with connection'}")
        if fb:
            lines.append(f"  return {fb.get('date')} dep {iso_local_hm(fb['dep'])} {'nonstop' if not fb.get('stops') else 'with connection'}")
        if st:
            lines.append(f"  lodging {st.get('km_to_center')} km from the center, ${st.get('price_per_night')}/night")
        if (pkg.get("refs") or {}).get("car"):
            lines.append("  rental car included")
    facts = _facts(rec)
    places = _places((rec.get("request") or {}).get("city") or (rec.get("case") or {}).get("city") or "Chicago")
    for d in rec.get("days") or []:
        its = d["items"][:max_items_per_day]
        cells = []
        for it in its:
            cat = (facts.get(it["place_id"]) or {}).get("category") or (places.get(it["place_id"]) or {}).get("category") or "?"
            cells.append(f"{it['start']}-{it['end']} {it['kind']} {(it.get('name') or it['place_id'])[:40]} [{cat}, {it['mode']} {it['travel_min']} min]")
        flags = [f for f in d.get("flags") or [] if f != "OUT_OF_HORIZON"]
        lines.append(f"DAY {d['date']}" + (f" ({','.join(flags)})" if flags else "") + ": " + ("; ".join(cells) or "(nothing planned)"))
    trade = rec.get("tradeoffs") or []
    if trade:
        lines.append("TRADE-OFFS / NOTES: " + " | ".join(t[:300] for t in trade[:8]))
    return "\n".join(lines)


def judge_settings() -> dict[str, Any]:
    from travel_agent.systems.llm import load_dotenv, settings
    load_dotenv()
    s = settings()
    jm = os.environ.get("JUDGE_MODEL")
    if not jm:
        raise RuntimeError("JUDGE_MODEL is not set (.env); it must differ from LLM_MODEL")
    if jm == s["model"] and os.environ.get("JUDGE_ALLOW_SAME_MODEL") != "1":
        raise RuntimeError(f"JUDGE_MODEL {jm} equals the agents' LLM_MODEL; use a different model")
    return dict(model=jm, temperature=0.0, max_tokens=int(os.environ.get("JUDGE_MAX_TOKENS", "600")), seed=s["seed"], timeout=s["timeout"])


def make_judge_llm():
    from crewai import LLM
    return LLM(**judge_settings())


def _json(s: str) -> dict[str, Any]:
    i = s.find("{")
    return json.JSONDecoder().raw_decode(s[i:])[0]


def judge_one(rec: dict[str, Any], llm=None, request_text: Optional[str] = None) -> dict[str, Any]:
    llm = llm or make_judge_llm()
    summary = summarize(rec, request_text)
    prompt = JUDGE_PROMPT % dict(criteria="\n".join(f"- {k}: {v}" for k, v in RUBRIC.items()), summary=summary)
    err = ""
    for _ in range(2):
        raw = llm.call([{"role": "user", "content": prompt}])
        try:
            j = Judgment.model_validate(_json(raw if isinstance(raw, str) else json.dumps(raw)))
            return dict(id=(rec.get("case") or {}).get("id") or rec.get("request_id"), system=rec.get("system"), variant=rec.get("variant"),
                        scores={k: getattr(j, k).score for k in RUBRIC}, why={k: getattr(j, k).why for k in RUBRIC},
                        summary_chars=len(summary), prompt_chars=len(prompt))
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            err = str(e)[:300]
            prompt += "\n\nYour previous answer was not valid JSON for the schema (" + err + "). Answer again with ONE JSON object."
    return dict(id=(rec.get("case") or {}).get("id"), system=rec.get("system"), error="judge answer invalid: " + err)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    d = Path(a.dir)
    recs = [json.loads(p.read_text()) for p in sorted(d.glob("*.json")) if p.name != "run_meta.json"]
    if a.limit:
        recs = recs[:a.limit]
    llm = make_judge_llm()
    out = Path(a.out) if a.out else d / "judgments.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(judge_one(r, llm), ensure_ascii=False) + "\n")
    print("written", out)


if __name__ == "__main__":
    main()
