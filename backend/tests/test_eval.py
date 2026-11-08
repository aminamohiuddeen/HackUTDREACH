"""eval.py: runs entirely in mock mode (builtin mock + scripted fake client). No NVIDIA."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import eval as reach_eval
from agents import orchestrator

BACKEND = Path(__file__).resolve().parent.parent
EDGE_TAGS = {"ir_only_industrial", "ir_human_residential", "ir_small_residential",
             "survey_one_yes", "survey_all_unknown", "no_telemetry_no_survey",
             "ir_missing_size", "ir_small_industrial"}


def _db_state(p: Path):
    return (p.exists(), p.stat().st_mtime_ns if p.exists() else None)


def _run_cli(*args):
    env = {**os.environ, "NVIDIA_API_KEY": ""}  # load_dotenv never overrides a set var
    return subprocess.run([sys.executable, "eval.py", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=300)


def test_eval_n5_known_good_fixture_exits_0():
    dev_db = BACKEND / "reach.db"
    before = _db_state(dev_db)
    proc = _run_cli("--n", "5", "--seed", "0", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)  # stdout is pure JSON
    assert out["passed"] is True
    assert out["meta"]["n"] == 5 and len(out["scenarios"]) == 5
    assert set(out["summary"]) == {"builtin-mock", "scripted-model"}
    for s in out["summary"].values():
        assert s["mismatches"] == 0
        assert s["classification_accuracy"] == s["status_accuracy"] == 1.0
    # seed 0, n=5 -> the first five edge cases, one of them run with the override model
    assert [s["tag"] for s in out["scenarios"]] == [
        "ir_only_industrial", "ir_human_residential", "ir_small_residential",
        "survey_one_yes", "survey_all_unknown"]
    assert out["overrides"]["attempted"] >= 1 and out["overrides"]["accepted"] == 0
    assert all(s["actual"]["builtin-mock"]["mode"] == "mock" for s in out["scenarios"])
    assert out["meta"]["scratch_db_deleted"] is True
    assert not Path(out["meta"]["scratch_dir"]).exists()
    assert _db_state(dev_db) == before  # reach.db untouched


def test_pitch_prints_exactly_one_line():
    proc = _run_cli("--n", "4", "--pitch")
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("Eval: 4 scenarios | classification 100.0% (scripted-model)")
    assert "accepted 0" in lines[0]


def test_harness_reports_mismatch_and_exit_1(client, monkeypatch):
    """The eval must be able to fail: corrupt the reported status and expect mismatches."""
    real = orchestrator.build_report

    def corrupted(row, cls_out):
        rep = real(row, cls_out)
        rep["status"] = "cleared" if rep["status"] != "cleared" else "ranked"
        return rep

    monkeypatch.setattr(orchestrator, "build_report", corrupted)
    scenarios = reach_eval.generate_scenarios(4, seed=0)
    results = reach_eval.evaluate(client, scenarios)
    assert results["passed"] is False
    assert reach_eval.exit_code(results) == 1
    for s in results["summary"].values():
        assert s["mismatches"] == 4 and s["status_accuracy"] == 0.0
        assert s["classification_accuracy"] == 1.0
    text = reach_eval.render_text(results, {
        "n": 4, "seed": 0, "scratch_dir": "-", "edge": 4, "sampled": 0,
        "behaviours": {}, "label_warnings": [], "scratch_db_deleted": True})
    assert "MISMATCH [scripted-model]" in text and "RESULT: FAIL" in text


def test_in_process_eval_passes_and_never_builds_real_client(client):
    # conftest's autouse fixture makes nemotron.get_client raise; eval swaps in its own
    # fakes per runner and restores afterwards.
    results = reach_eval.evaluate(client, reach_eval.generate_scenarios(8, seed=0))
    assert results["passed"] is True
    runs = [s["actual"]["scripted-model"] for s in results["scenarios"]]
    assert any(r["truncated"] for r in runs)  # runaway behaviour hit the cap
    assert results["overrides"]["attempted"] == 2 and results["overrides"]["accepted"] == 0


def test_generator_deterministic_and_covers_edge_cases():
    a = reach_eval.generate_scenarios(40, seed=7)
    b = reach_eval.generate_scenarios(40, seed=7)
    assert a == b
    tags = {s["tag"] for s in a}
    assert EDGE_TAGS <= tags
    assert {s["behaviour"] for s in a} == set(reach_eval.BEHAVIOURS)
    assert reach_eval.generate_scenarios(40, seed=8) != a


def test_label_disagreement_warns_not_fails():
    sc = reach_eval.generate_scenarios(1)[0]
    sc["label"] = ("likely_person", "ranked")  # deliberately wrong hand label
    warnings = reach_eval.label_warnings([sc])
    assert len(warnings) == 1 and "ground truth used" in warnings[0]


def test_check_live_skipped_without_key(capsys):
    assert reach_eval.check_live("", {}) == 0
    assert "skipped" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--json", "--pitch"])
def test_json_and_pitch_are_mutually_exclusive_with_check_live(flag):
    with pytest.raises(SystemExit):
        reach_eval.main([flag, "--check-live"])
