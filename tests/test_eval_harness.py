import json

from eval import run_eval, score


def test_run_eval_and_score(tmp_path):
    out = run_eval.main(["--system", "rules", "--split", "eval", "--city", "chicago", "--ids", "A01,B02,E02", "--out", str(tmp_path / "r")])
    files = sorted(p.name for p in out.glob("*.json"))
    assert files == ["A01.json", "B02.json", "E02.json", "run_meta.json"]
    rec = json.loads((out / "A01.json").read_text())
    for k in ("status", "days", "package", "tool_log", "llm_calls", "tokens_in", "wall_time_s", "rounds_used", "check_report"):
        assert k in rec
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["frozen_ok"] is True
    md = score.main([str(out), "--out", str(tmp_path / "rep")])
    assert "A - rules" in md and "2/2 = 1.00" in md
    assert (tmp_path / "rep" / "comparison.csv").exists()


def test_wilson():
    lo, hi = score.wilson(15, 24)
    assert 0.40 < lo < 0.45 and 0.78 < hi < 0.81
