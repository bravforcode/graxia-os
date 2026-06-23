"""
Phase 2A verification tests.

Run: python -m pytest graxia/packages/quant_os/tests/test_phase_2a.py -v
"""

import json
import hashlib
from pathlib import Path

import pytest

# Paths
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
CSV_FILES = {
    "D1": DATA_DIR / "XAUUSD_D1.csv",
    "H1": DATA_DIR / "XAUUSD_H1.csv",
    "M15": DATA_DIR / "XAUUSD_M15.csv",
}
PRODUCTION_ROOT = Path(__file__).resolve().parent.parent


# === Manifest Tests ===

class TestDatasetManifests:
    """Tests 1-6: manifest existence and content."""

    @pytest.fixture(autouse=True)
    def _load_manifests(self):
        self.manifests = {}
        for tf, csv_path in CSV_FILES.items():
            manifest_path = MANIFEST_DIR / f"XAUUSD_{tf}.manifest.json"
            if manifest_path.exists():
                self.manifests[tf] = json.loads(manifest_path.read_text())

    def test_dataset_manifests_exist(self):
        """Test 1: all 3 XAUUSD manifests exist and are valid JSON."""
        for tf in CSV_FILES:
            manifest_path = MANIFEST_DIR / f"XAUUSD_{tf}.manifest.json"
            assert manifest_path.exists(), f"Missing manifest for {tf}"
            assert tf in self.manifests, f"Invalid JSON in {tf} manifest"

    def test_manifest_checksum_matches(self):
        """Test 2: sha256 in manifest matches actual CSV file."""
        for tf, csv_path in CSV_FILES.items():
            actual_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            expected_sha = self.manifests[tf]["csv_sha256"]
            assert actual_sha == expected_sha, (
                f"{tf}: manifest sha256={expected_sha} actual={actual_sha}"
            )

    def test_manifest_timestamps_ordered(self):
        """Test 3: timestamps in manifest are monotonically increasing."""
        for tf in CSV_FILES:
            first = self.manifests[tf]["first_timestamp_utc"]
            last = self.manifests[tf]["last_timestamp_utc"]
            assert first < last, f"{tf}: first={first} >= last={last}"

    def test_manifest_not_synthetic(self):
        """Test 4: synthetic field is false."""
        for tf in CSV_FILES:
            assert self.manifests[tf]["synthetic"] is False, f"{tf} marked synthetic"

    def test_manifest_timezone_utc(self):
        """Test 5: timezone is UTC."""
        for tf in CSV_FILES:
            assert self.manifests[tf]["timezone"] == "UTC", f"{tf} timezone != UTC"

    def test_manifest_source_known(self):
        """Test 6: source is MT5."""
        for tf in CSV_FILES:
            assert self.manifests[tf]["source"] == "MT5", f"{tf} source != MT5"


# === RiskPolicy Tests ===

class TestRiskPolicy:
    """Tests 7-8: bps-based risk policy."""

    def test_risk_policy_basis_points(self):
        """Test 7: RiskPolicy converts bps correctly."""
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "risk_policy",
            os.path.join(os.path.dirname(__file__), "..", "risk", "risk_policy.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        RiskPolicy = mod.RiskPolicy
        p = RiskPolicy(risk_per_trade_bps=10)
        from decimal import Decimal
        assert p.risk_per_trade_fraction == Decimal("0.0010")  # 10 bps = 0.10%
        assert p.max_daily_loss_fraction == Decimal("0.0050")  # 50 bps = 0.50%
        assert p.max_weekly_loss_fraction == Decimal("0.0150")
        assert p.max_total_drawdown_fraction == Decimal("0.0300")

    def test_risk_policy_no_pct_field(self):
        """Test 8: risk_per_trade_pct should not exist on RiskPolicy."""
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "risk_policy",
            os.path.join(os.path.dirname(__file__), "..", "risk", "risk_policy.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        RiskPolicy = mod.RiskPolicy
        p = RiskPolicy()
        assert not hasattr(p, "risk_per_trade_pct"), (
            "RiskPolicy must not have risk_per_trade_pct"
        )


# === Strict MTF Tests ===

class TestStrictMTF:
    """Test 9: engine blocks static fallback when strict_mtf=True."""

    def test_strict_mtf_blocks_static_fallback(self):
        from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
        from graxia.packages.quant_os.core.exceptions import StrictMTFViolation
        from graxia.packages.quant_os.strategies.base import Strategy, StrategyConfig, Signal
        from graxia.packages.quant_os.core.enums import SignalType

        class DummyStrategy(Strategy):
            def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
                return None
            def required_features(self):
                return []

        config = BacktestConfig(strict_mtf=True)
        engine = BacktestEngine(config)
        engine.set_strategy(DummyStrategy(StrategyConfig(name="dummy")))

        # Load minimal data
        n = 250
        data = {
            "open": [1.0] * n,
            "high": [1.1] * n,
            "low": [0.9] * n,
            "close": [1.0] * n,
            "volume": [100] * n,
        }
        from datetime import datetime, timedelta
        ts = [datetime(2020, 1, 1) + timedelta(hours=i) for i in range(n)]
        engine.load_data(data, timestamps=ts)

        # No MTF cursor set — should raise
        with pytest.raises(StrictMTFViolation):
            engine.run()


# === Hardcode Audit Tests ===

class TestHardcodeAudit:
    """Tests 10-11: production code is clean of forbidden patterns."""

    def test_hardcode_audit_no_units_per_lot_in_production(self):
        """Test 10: no units_per_lot in production code paths (exclude tests/)."""
        violations = []
        # Exclude: tests, gold_bot (separate module), __pycache__
        exclude_dirs = {"tests", "test_", "__pycache__", "gold_bot"}
        # Files that legitimately use units_per_lot as a parameter/config field
        # Keyed by (parent_dir_name, filename) to disambiguate engine.py etc.
        allowed = {
            ("core", "config.py"),
            ("risk", "position_sizer.py"),
            ("risk", "risk_policy.py"),
            ("risk", "contract_spec.py"),
            ("backtest", "engine.py"),
            ("strategies", "base.py"),
            ("risk", "engine.py"),
            ("execution", "broker_adapter.py"),
            ("quant_os", "run_backtest_real.py"),  # ponytail: runner script, documented in audit
        }
        py_files = [
            f for f in PRODUCTION_ROOT.rglob("*.py")
            if not any(d in f.parts for d in exclude_dirs)
            and "test" not in f.name
        ]
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                parent = py_file.parent.name
                key = (parent, py_file.name)
                for i, line in enumerate(content.splitlines(), 1):
                    if "units_per_lot" in line and not line.strip().startswith("#"):
                        if key not in allowed:
                            violations.append(f"{parent}/{py_file.name}:{i}: {line.strip()}")
            except Exception:
                pass
        assert len(violations) == 0, (
            f"units_per_lot found in unlisted production code:\n" +
            "\n".join(violations[:10])
        )

    def test_no_order_send_in_phase2(self):
        """Test 11: grep for order_send in broker/ and risk/ should find none (except mt5_gateway guard)."""
        violations = []
        for subdir in ["broker", "risk"]:
            d = PRODUCTION_ROOT / subdir
            if not d.exists():
                continue
            for py_file in d.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(content.splitlines(), 1):
                        stripped = line.strip()
                        if "order_send" in stripped and not stripped.startswith("#"):
                            # mt5_gateway.py has a guard that asserts order_send doesn't exist — allow it
                            if py_file.name == "mt5_gateway.py" and "forbidden" in stripped:
                                continue
                            violations.append(f"{py_file.name}:{i}: {stripped}")
                except Exception:
                    pass
        assert len(violations) == 0, (
            f"order_send found in broker/risk:\n" + "\n".join(violations)
        )
