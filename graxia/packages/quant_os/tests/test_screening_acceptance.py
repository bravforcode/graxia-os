# tests/test_screening_acceptance.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_screening_results_artifact():
    d = json.loads((ROOT / "research" / "catalog_i" / "screening_results_wave1.json").read_text(encoding="utf-8"))
    assert d["configs_tried"] >= 20


def test_no_void_without_audit():
    d = json.loads((ROOT / "research" / "catalog_i" / "screening_results_wave1.json").read_text(encoding="utf-8"))
    for res in d["results"].values():
        if res["status"] == "VOID":
            assert "reason" in res  # every VOID carries an audit trail


def test_survivors_have_full_metrics():
    d = json.loads((ROOT / "research" / "catalog_i" / "screening_results_wave1.json").read_text(encoding="utf-8"))
    for s in d["survivors"]:
        sc = s["screening"]
        assert sc["sharpe_ratio"] > 0
        assert sc["total_trades"] >= 30


def test_screening_log_matches_results():
    log = json.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    results = json.loads((ROOT / "research" / "catalog_i" / "screening_results_wave1.json").read_text(encoding="utf-8"))
    assert log["count"] >= results["configs_tried"]
