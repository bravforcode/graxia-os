"""Phase 4 integration tests — EURUSD clean research foundation."""
import json
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
DATA_DIR = REPO_ROOT / "graxia/packages/quant_os/data"
MANIFEST_DIR = DATA_DIR / "manifests"


def test_eurusd_data_files_exist():
    """EURUSD D1/H1/M15 data files must exist."""
    for tf in ["D1", "H1", "M15"]:
        path = DATA_DIR / f"EURUSD_{tf}.csv"
        assert path.exists(), f"Missing EURUSD_{tf}.csv"


def test_eurusd_data_manifests_exist():
    """EURUSD data manifests must exist for all timeframes."""
    for tf in ["D1", "H1", "M15"]:
        path = MANIFEST_DIR / f"EURUSD_{tf}_manifest.json"
        assert path.exists(), f"Missing EURUSD_{tf}_manifest.json"


def test_eurusd_data_manifests_valid():
    """EURUSD data manifests must be valid JSON with required fields."""
    required = ["symbol", "timeframe", "sha256", "rows", "start_date", "end_date"]
    for tf in ["D1", "H1", "M15"]:
        path = MANIFEST_DIR / f"EURUSD_{tf}_manifest.json"
        if path.exists():
            data = json.loads(path.read_text())
            for field in required:
                assert field in data, f"Missing {field} in EURUSD_{tf}_manifest.json"
            assert data["symbol"] == "EURUSD"
            assert data["timeframe"] == tf


def test_eurusd_contract_snapshot_exists():
    """EURUSD contract snapshot module must exist."""
    from graxia.packages.quant_os.markets.eurusd.contract_snapshot import EURUSDContractSnapshot
    c = EURUSDContractSnapshot()
    assert c.symbol == "EURUSD"
    assert c.contract_size == 100000


def test_eurusd_anti_contamination_works():
    """Anti-contamination guard must block XAUUSD parameters."""
    from graxia.packages.quant_os.markets.eurusd.anti_contamination import AntiContaminationGuard
    guard = AntiContaminationGuard()

    # Should pass for clean params
    report = guard.check_parameter_source({"entry_rule": "sma_cross"}, "EURUSD")
    assert report.clean

    # Should fail for XAUUSD params
    report = guard.check_parameter_source({"liquidity_threshold": 0.0005}, "XAUUSD")
    assert not report.clean


def test_eurusd_hypothesis_template_works():
    """Hypothesis template must create valid hypotheses."""
    from graxia.packages.quant_os.markets.eurusd.hypothesis import EURUSDHypothesis
    h = EURUSDHypothesis(
        hypothesis_id="EURUSD-HYP-001",
        market="EURUSD",
        timeframe="H1",
        entry_logic="sma_crossover",
        exit_logic="trailing_stop",
        stop_logic="fixed_pips",
    )
    assert h.fingerprint()
    assert h.market == "EURUSD"


def test_no_xauusd_data_in_eurusd():
    """EURUSD data must not contain XAUUSD values."""
    csv_path = DATA_DIR / "EURUSD_D1.csv"
    if csv_path.exists():
        content = csv_path.read_text()
        # XAUUSD prices are ~2000-3000, EURUSD is ~1.0-1.5
        # Check first 100 data lines
        lines = content.strip().split("\n")[1:101]
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 5:
                close = float(parts[4])
                assert 0.5 < close < 3.0, f"Suspicious EURUSD close: {close} (might be XAUUSD data)"
