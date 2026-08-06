# tests/test_run_screening.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def test_screening_cli_runs_limited(tmp_path):
    r = _run(["scripts/run_screening.py", "--limit", "3", "--out", str(tmp_path / "results.json")])
    assert r.returncode == 0, r.stderr[-2000:]
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert results["configs_tried"] == 3
    for res in results["results"].values():
        assert res["status"] in {"done", "no_cost_data", "no_strategy", "VOID"}
        assert res["n_registered"] is True  # every config registered before run


def test_screening_log_has_entries():
    # the real screening log must show the runs (registered BEFORE run)
    log = json.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    assert log["count"] >= 3
