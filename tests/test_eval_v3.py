"""Eval v3 (free-text segment): request extensions, keyword parser, strong rules honoring the new fields, hybrid
(LLM parser + strong rules) and B/C on free text with fake LLMs, key-requirement scorer, LLM-judge plumbing.
No real LLM is called."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from eval import judge as J
from eval import keyreq as K
from travel_agent.models import FreeTextRequest, TripRequest
from travel_agent.parsing.parse_rules import parse as kw_parse
from travel_agent.pipeline import build_candidates, day_windows, weather_step
from travel_agent.systems import run
from travel_agent.systems.llm import set_llm_factory
from travel_agent.tool_log import ToolLog

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "eval" / "cases" / "eval_cases_v3.json"
CASES = {c["id"]: c for c in json.loads(V3.read_text())["cases"]}
V2 = {c["id"]: c for c in json.loads((ROOT / "eval/cases/eval_cases_v2.json").read_text())["cases"]}


def ft(cid):
    c = CASES[cid]
    return dict(request_id=cid, request_text=c["request_text"], as_of=c["as_of"])


def rec_of(r, cid):
    rec = json.loads(r.model_dump_json())
    rec["case"] = dict(id=cid, city=CASES[cid]["city"], request_text=CASES[cid]["request_text"])
    return rec


class ParserLLM:
    """Fake LLM for the parser: answers with the given fields as JSON (first answer optionally invalid)."""
    def __init__(self, fields, bad_first=False):
        self.fields, self.bad_first, self.calls, self.prompts = fields, bad_first, 0, []

    def call(self, messages, **kw):
        self.calls += 1
        self.prompts.append(messages[-1]["content"])
        if self.bad_first and self.calls == 1:
            return '{"city": "Paris"}'
        return "```json\n" + json.dumps(self.fields, default=str) + "\n```"


def gold_fields(cid):
    g = dict(CASES[cid]["gold"]["request"])
    g.pop("as_of", None)
    return g


# ----------------------------------------------------------------- case set
def test_v3_frozen_and_counts():
    assert hashlib.sha256(V3.read_bytes()).hexdigest() == (ROOT / "eval/cases/FROZEN_v3.sha256").read_text().split()[0]
    ev = [c for c in CASES.values() if c["split"] == "eval"]
    assert len(ev) == 20 and len(CASES) == 24
    assert sum(c["phrasing_type"] == "direct" for c in ev) == 10 and sum(c["city"] == "Chicago" for c in ev) == 10
    for c in CASES.values():
        assert 2 <= len(c["gold"]["key_requirements"]) <= 3
        assert c["oracle"]["n_feasible_packages"] >= 10 and c["oracle"]["pipeline_agrees"] and c["oracle"]["places_status"] == "PASS"
        TripRequest.model_validate(dict(c["gold"]["request"], request_id=c["id"]))


def test_v2_v1_unchanged_and_backward_compatible(cases):
    assert hashlib.sha256((ROOT / "eval/cases/eval_cases_v2.json").read_bytes()).hexdigest() == \
        (ROOT / "eval/cases/FROZEN_v2.sha256").read_text().split()[0]
    r = TripRequest.from_case(cases["A01"])
    assert r.daily_blocked_windows == [] and r.day_start is None and r.priority_weights == {} and not r.accessibility


def test_new_field_validation():
    base = dict(CASES["G01"]["gold"]["request"], request_id="x")
    with pytest.raises(ValueError):
        TripRequest.model_validate(dict(base, daily_blocked_windows=[dict(start="15:00", end="13:00")]))
    with pytest.raises(ValueError):
        TripRequest.model_validate(dict(base, priority_weights={"beauty": 1}))
    with pytest.raises(ValueError):
        TripRequest.model_validate(dict(base, day_start="25:00"))


# ----------------------------------------------------------------- keyword parser
def test_keyword_parser_dev_text():
    p = kw_parse(FreeTextRequest(**ft("G01")))
    g = CASES["G01"]["gold"]["request"]
    f = p.fields
    for k in ("city", "origin", "travelers", "budget_usd", "no_early_flight_before"):
        assert str(f[k]) == str(g[k]), k
    assert str(f["start_date"]) == g["start_date"] and f["daily_blocked_windows"][0]["start"] == "13:00"


def test_keyword_parser_unparsed_and_negation():
    t = ("Two of us from Boston to Chicago, October 3-6, max $2,000. We're vegetarian. No bars please, museums yes. "
         "My dad uses a wheelchair.")
    f = kw_parse(FreeTextRequest(request_text=t, as_of="2022-09-10")).fields
    assert "nightlife" in f["avoid"] and "culture" in f["interests"] and f["accessibility"]
    assert "dietary requirement" in f["unparsed_requirements"]


def test_keyword_parser_missing_fields():
    p = kw_parse(FreeTextRequest(request_text="We want a nice weekend somewhere warm, no idea when.", as_of="2022-09-10"))
    assert p.fields is None and "city" in p.error


# ----------------------------------------------------------------- pipeline / strong rules honor the new fields
def test_no_early_flight_and_day_window_fields():
    req = TripRequest.model_validate(dict(CASES["F01"]["gold"]["request"], request_id="x"))
    log = ToolLog("t")
    conds, _ = weather_step(log, req)
    cands = build_candidates(log, req, conditions=conds)
    assert all(c["flight_out"]["dep"][11:16] >= "09:00" and c["flight_back"]["dep"][11:16] >= "09:00" for c in cands)
    c = cands[0]
    w = day_windows(req.model_copy(update=dict(day_start="11:00", day_end="22:00")), c["flight_out"], c["flight_back"])
    mid = [v for k, v in w.items() if k not in (str(req.start_date), str(req.end_date))]
    assert mid and all(v == ("11:00", "22:00") for v in mid)


def test_rules_free_text_blocked_window_and_gold_checks():
    r = run("rules", ft("G01"))
    assert r.status.value == "OK_PLAN" and r.parser == "keyword" and r.llm_calls == 0
    for d in r.days:
        for it in d.items:
            assert not (it.start < "15:00" and "13:00" < it.end), (d.date, it.start, it.end)
    ev = K.evaluate(rec_of(r, "G01"), CASES["G01"])
    assert ev["met"] == ev["n"]


def test_priority_weights_choose_profile():
    c = V2["B07"]                               # true conflict central vs nonstop (both Pareto profiles in the candidates)
    for pref, other in (("central", "nonstop"), ("nonstop", "central")):
        r = run("rules", dict(TripRequest.from_case(c).model_dump(), priority_weights={pref: 2.0}))
        sac = next(x["sacrificed_prefs"] for x in r.candidates if x["refs"] == r.package.refs)
        assert sac == [other], (pref, sac)


def test_unparsed_and_accessibility_flagged():
    r = run("rules", dict(TripRequest.model_validate(dict(CASES["F20"]["gold"]["request"], request_id="F20")).model_dump()))
    text = " ".join(r.tradeoffs).lower()
    assert "not handled: accessibility" in text and "not handled: kosher" in text


# ----------------------------------------------------------------- hybrid / B / C on free text (fake LLMs)
def test_hybrid_with_fake_parser_llm():
    fake = ParserLLM(gold_fields("G02"))
    set_llm_factory(lambda role: fake)
    try:
        r = run("hybrid", ft("G02"))
    finally:
        set_llm_factory(None)
    assert r.system == "H" and r.parser == "llm" and r.status.value == "OK_PLAN"
    assert r.llm_calls == 1 and "REQUEST TEXT" in fake.prompts[0] and "unparsed_requirements" in fake.prompts[0]
    assert "gold" not in fake.prompts[0].lower()
    assert r.request.priority_weights == {"central": 2.0}


def test_hybrid_repairs_invalid_json():
    fake = ParserLLM(gold_fields("G03"), bad_first=True)
    set_llm_factory(lambda role: fake)
    try:
        r = run("hybrid", ft("G03"))
    finally:
        set_llm_factory(None)
    assert r.status.value == "OK_PLAN" and r.llm_calls == 2


def test_hybrid_without_llm_is_technical_error(monkeypatch):
    set_llm_factory(None)
    monkeypatch.setenv("LLM_MODEL", "ollama/qwen2.5:7b-instruct")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    r = run("hybrid", ft("G01"))
    assert r.status.value == "TECHNICAL_ERROR" and "LLM not available" in r.message


@pytest.mark.parametrize("system", ["single", "multi"])
def test_b_and_c_accept_free_text(system):
    pytest.importorskip("crewai")
    from fake_llm import ScriptedLLM
    parser = ParserLLM(gold_fields("G03"))
    set_llm_factory(lambda role: parser if role == "parser" else ScriptedLLM(model="fake/scripted"))
    try:
        r = run(system, ft("G03"))
    finally:
        set_llm_factory(None)
    assert r.parser == "llm" and r.status.value == "OK_PLAN", (r.message, r.notes)
    assert r.parse_llm_calls == 1 and r.llm_calls >= 3


def test_rules_on_structured_request_does_not_parse(cases):
    r = run("rules", TripRequest.from_case(cases["A01"]))
    assert r.parser is None and r.status.value == "OK_PLAN"


# ----------------------------------------------------------------- key requirements scorer
def test_keyreq_outcomes():
    r = run("rules", ft("G01"))
    rec = rec_of(r, "G01")
    case = copy.deepcopy(CASES["G01"])
    kr = next(k for k in case["gold"]["key_requirements"] if k["checker"] == "no_activity_in_window")
    assert K.evaluate(rec, case)["requirements"][1]["outcome"] == "met"
    kr["params"].update(start="10:00", end="19:00")          # impossible to meet with this plan
    assert K.evaluate(rec, case)["requirements"][1]["outcome"] == "ignored"
    rec["tradeoffs"] = rec["tradeoffs"] + ["not handled: the nap window could not be kept free on day 2"]
    assert K.evaluate(rec, case)["requirements"][1]["outcome"] == "flagged"
    rec["status"] = "INVALID_REQUEST"
    assert K.evaluate(rec, case)["met"] == 0


def test_flag_unsupported_only_by_flagging():
    rec = dict(status="OK_PLAN", package=None, days=[], tradeoffs=["not handled: accessibility / step-free access"], request={})
    case = dict(city="New York", gold=dict(key_requirements=[dict(id="x", checker="flag_unsupported", params=dict(topic="a", keywords=["accessib"]))]))
    assert K.evaluate(rec, case)["met"] == 1
    rec["tradeoffs"] = []
    assert K.evaluate(rec, case)["ignored"] == 1


# ----------------------------------------------------------------- LLM judge plumbing
class JudgeLLM:
    def __init__(self):
        self.prompts = []

    def call(self, messages, **kw):
        self.prompts.append(messages[-1]["content"])
        return json.dumps({k: {"score": 4, "why": "ok"} for k in J.RUBRIC})


def test_judge_compact_summary_and_fake_call():
    r = run("rules", ft("G04"))
    rec = rec_of(r, "G04")
    s = J.summarize(rec)
    assert s.startswith("REQUEST: ") and "PACKAGE: total $" and len(s) < 4500
    assert len(json.dumps(rec)) > 20 * len(s)               # far smaller than the raw result
    for k in ("gold", "key_requirements", "oracle"):
        assert k not in s
    j = J.judge_one(rec, JudgeLLM())
    assert j["scores"] == {k: 4 for k in J.RUBRIC}


def test_judge_model_must_differ(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.setenv("JUDGE_MODEL", "groq/llama-3.3-70b-versatile")
    monkeypatch.delenv("JUDGE_ALLOW_SAME_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        J.judge_settings()
    monkeypatch.setenv("JUDGE_MODEL", "gemini/gemini-2.0-flash")
    assert J.judge_settings()["temperature"] == 0.0
