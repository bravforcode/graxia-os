"""Phase 4 integration tests — EURUSD clean research foundation.

RESTORED from deleted test_phase_4_integration.py (BE-P7 commit 3ae373f).
Migrated to current API. Contamination/hypothesis tests quarantined
(see QUARANTINE_MANIFEST.md).
"""

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
            data = json.loads(path.read_text(encoding="utf-8"))
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


def test_eurusd_session_calendar_works():
    """Session calendar must identify sessions."""
    from graxia.packages.quant_os.markets.eurusd.session_calendar import EURUSDSessionCalendar

    cal = EURUSDSessionCalendar()
    sessions = cal.get_active_sessions(10)
    assert any(s.name == "london" for s in sessions)


def test_eurusd_event_calendar_works():
    """Event calendar must list high-impact events."""
    from graxia.packages.quant_os.markets.eurusd.event_calendar import EURUSDEventCalendar

    cal = EURUSDEventCalendar()
    events = cal.get_high_impact()
    assert len(events) >= 5


def test_no_xauusd_data_in_eurusd():
    """EURUSD data must not contain XAUUSD values."""
    csv_path = DATA_DIR / "EURUSD_D1.csv"
    if csv_path.exists():
        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")[1:101]
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 5:
                close = float(parts[4])
                assert 0.5 < close < 3.0, f"Suspicious EURUSD close: {close} (might be XAUUSD data)"
