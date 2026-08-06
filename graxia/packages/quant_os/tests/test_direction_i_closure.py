# tests/test_direction_i_closure.py
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_closure_items_documented():
    report = (ROOT / "reports" / "direction_i_phase0_closure_20260806.md").read_text(encoding="utf-8")
    normalized = " ".join(report.replace("—", " ").lower().split())
    for marker in [
        "item 0 writer-lock",
        "item 1 tsm jackknife",
        "item 2 c0 reuse",
        "item 3 8001/8002 annotations",
        "item 4 direction h state",
        "item 5 eurusd h4 dependency",
    ]:
        assert marker in normalized


def test_direction_h_files_untouched():
    # Ratchet: Direction I work must never modify Direction H files.
    # Base ref = 28424bff (parallel session's last legitimate H-ledger change,
    # Trial 9002 REJECTED). Update this ref ONLY when legitimate H work commits.
    out = subprocess.run(
        ["git", "diff", "--name-only", "28424bff..HEAD", "--", "research/trial_ledger_h.json"],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == "", "Direction H ledger must not be modified by Direction I work"


def test_ratchet_still_passes():
    out = subprocess.run(
        ["python", "scripts/check_trial_uniqueness.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_tsm_jackknife_rerun_verdict():
    d = json.loads((ROOT / "reports" / "tsm_portfolio_jackknife_rerun_20260806.json").read_text(encoding="utf-8"))
    assert d["verdict"] == "REJECT_CONFIRMED"
    assert "BTC_YF" in d["concerning_single_asset_dependence"]
