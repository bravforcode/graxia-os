"""Tests for state persistence (MacroRegime + RiskBudget)."""

import tempfile
from pathlib import Path

from graxia.packages.quant_os.core.canonical.macro_regime import MacroRegime, MacroRegimeCache, RegimeBias
from graxia.packages.quant_os.core.risk_budget import RiskBudget, load_state, save_state


class TestMacroRegimePersistence:
    def test_round_trip(self):
        regime = MacroRegime(
            bias=RegimeBias.BEARISH,
            confidence=0.75,
            position_multiplier=0.5,
            regime_label="HIGH_UNCERTAINTY",
            source="test",
            headline="test headline",
        )
        d = regime.to_dict()
        restored = MacroRegime.from_dict(d)
        assert restored.bias == RegimeBias.BEARISH
        assert restored.confidence == 0.75
        assert restored.position_multiplier == 0.5
        assert restored.regime_label == "HIGH_UNCERTAINTY"
        assert restored.headline == "test headline"

    def test_cache_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "regime.json"
            cache = MacroRegimeCache()
            cache._STATE_PATH = path  # redirect before any write touches the real state file
            cache.update(
                MacroRegime(
                    bias=RegimeBias.BULLISH,
                    confidence=0.9,
                    position_multiplier=1.2,
                    regime_label="NORMAL",
                    source="test",
                )
            )
            assert path.exists()

            # Clear in-memory only (reset() would also persist NEUTRAL to
            # _STATE_PATH, clobbering the BULLISH state just written above).
            with cache._lock:
                cache._regime = MacroRegime()
            assert cache.get().bias == RegimeBias.NEUTRAL
            cache._load_state()
            assert cache.get().bias == RegimeBias.BULLISH
            assert cache.get().confidence == 0.9


class TestRiskBudgetPersistence:
    def test_round_trip(self):
        budget = RiskBudget(
            current_daily_pnl=-1.5,
            current_weekly_pnl=-3.2,
            open_positions=2,
        )
        d = budget.to_dict()
        restored = RiskBudget.from_dict(d)
        assert restored.current_daily_pnl == -1.5
        assert restored.current_weekly_pnl == -3.2
        assert restored.open_positions == 2

    def test_save_load_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "risk.json"
            budget = RiskBudget(current_daily_pnl=-0.5, open_positions=1)
            save_state(budget, path)
            assert path.exists()

            loaded = load_state(path)
            assert loaded.current_daily_pnl == -0.5
            assert loaded.open_positions == 1

    def test_can_trade(self):
        budget = RiskBudget()
        can, reason = budget.can_trade()
        assert can is True
        assert reason == "OK"

        budget.current_daily_pnl = -2.5
        can, reason = budget.can_trade()
        assert can is False
        assert "Daily" in reason
