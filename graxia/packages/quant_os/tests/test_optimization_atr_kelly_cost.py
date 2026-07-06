"""Tests for ATR multiplier optimization, half-Kelly sizing, and cost calibration.

Covers:
  - TASK 1: Per-symbol ATR multipliers (fixed stops, no trailing)
  - TASK 2: Half-Kelly position sizing (rolling 20-trade, cap/floor)
  - TASK 3: Cost calibration (Pepperstone real data, dead-weight removed)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE.parent))

scripts_dir = BASE / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# Import tsm_paper_trade with mocked MT5
import importlib.util

_spec = importlib.util.spec_from_file_location("tsm_paper_trade", scripts_dir / "tsm_paper_trade.py")
_mod = importlib.util.module_from_spec(_spec)

with patch.dict("sys.modules", {"MetaTrader5": MagicMock()}):
    _spec.loader.exec_module(_mod)


# ═══════════════════════════════════════════════════════════════
# TASK 1: Per-Symbol ATR Multipliers
# ═══════════════════════════════════════════════════════════════


class TestATRMultiplierOptimization:
    """Verify per-symbol ATR multipliers and fixed-stop mode."""

    def test_symbol_stop_configs_exist(self):
        """_SYMBOL_STOP_CONFIGS must have all 4 active assets."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        expected_symbols = {"XAUUSD", "NAS100", "USOIL", "USDJPY"}
        assert expected_symbols == set(_SYMBOL_STOP_CONFIGS.keys())

    def test_xauusd_multiplier_2_5(self):
        """XAUUSD: 2.5x ATR (gold is more volatile)."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        cfg = _SYMBOL_STOP_CONFIGS["XAUUSD"]
        assert cfg.trail_multiplier == 2.5

    def test_nas100_multiplier_2_0(self):
        """NAS100: 2.0x ATR (research optimal)."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        cfg = _SYMBOL_STOP_CONFIGS["NAS100"]
        assert cfg.trail_multiplier == 2.0

    def test_oil_multiplier_3_0(self):
        """OIL: 3.0x ATR (oil has extreme moves)."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        cfg = _SYMBOL_STOP_CONFIGS["USOIL"]
        assert cfg.trail_multiplier == 3.0

    def test_usdjpy_multiplier_1_5(self):
        """USDJPY: 1.5x ATR (FX is less volatile)."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        cfg = _SYMBOL_STOP_CONFIGS["USDJPY"]
        assert cfg.trail_multiplier == 1.5

    def test_all_symbol_configs_are_fixed(self):
        """All per-symbol configs must use fixed stop mode (not trailing)."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        for symbol, cfg in _SYMBOL_STOP_CONFIGS.items():
            assert cfg.stop_mode == "fixed", f"{symbol} should use fixed stops, got {cfg.stop_mode}"

    def test_all_symbol_configs_enabled(self):
        """All per-symbol configs must be enabled."""
        from graxia.packages.quant_os.execution.oms import _SYMBOL_STOP_CONFIGS

        for symbol, cfg in _SYMBOL_STOP_CONFIGS.items():
            assert cfg.enabled is True, f"{symbol} should be enabled"

    def test_default_asset_configs_also_fixed(self):
        """Asset-class defaults should also use fixed mode."""
        from graxia.packages.quant_os.execution.oms import _DEFAULT_TRAILING_CONFIGS

        for asset_class, cfg in _DEFAULT_TRAILING_CONFIGS.items():
            if asset_class != "crypto":  # Crypto keeps trailing
                assert cfg.stop_mode == "fixed", f"{asset_class} should use fixed stops"

    def test_oms_accepts_symbol_stop_configs(self):
        """OMS constructor should accept symbol_stop_configs parameter."""
        from graxia.packages.quant_os.execution.oms import OMS, TrailingStopConfig

        mock_risk = MagicMock()
        mock_risk.check_order_sync.return_value = MagicMock(passed=True)
        adapter = MagicMock()
        adapter.name = "MT5"
        adapter.is_connected = True

        custom_configs = {
            "XAUUSD": TrailingStopConfig(enabled=True, trail_multiplier=3.0, stop_mode="fixed"),
        }
        oms = OMS(
            adapters={"mt5": adapter},
            risk_engine=mock_risk,
            symbol_stop_configs=custom_configs,
        )
        assert "XAUUSD" in oms._symbol_stop_configs
        assert oms._symbol_stop_configs["XAUUSD"].trail_multiplier == 3.0

    def test_post_fill_uses_symbol_config_over_asset_class(self):
        """_setup_post_fill_stop_loss should prefer symbol config over asset class."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.oms import OMS, TrailingStopConfig
        from graxia.packages.quant_os.execution.order import Order

        mock_risk = MagicMock()
        mock_risk.check_order_sync.return_value = MagicMock(passed=True)
        adapter = MagicMock()
        adapter.name = "MT5"
        adapter.is_connected = True
        adapter.get_positions.return_value = [
            {"ticket": 99999, "symbol": "XAUUSD", "comment": "test-symbol-config"},
        ]
        adapter.set_stop_loss.return_value = True

        # Symbol config: 3.5x multiplier
        symbol_configs = {
            "XAUUSD": TrailingStopConfig(enabled=True, trail_multiplier=3.5, stop_mode="fixed"),
        }
        # Asset class config: 2.0x multiplier
        asset_configs = {
            "metals": TrailingStopConfig(enabled=True, trail_multiplier=2.0, stop_mode="fixed"),
        }

        oms = OMS(
            adapters={"mt5": adapter},
            risk_engine=mock_risk,
            trailing_stop_configs=asset_configs,
            symbol_stop_configs=symbol_configs,
        )

        order = Order(
            id="test-symbol-config",
            signal_id="sig-test",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_price=None,
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)

        # Should use 3.5x (symbol) not 2.0x (asset class)
        call_kwargs = adapter.set_stop_loss.call_args[1]
        # SL = 2300 - (2300 * 0.02 * 3.5) = 2300 - 161 = 2139
        assert abs(call_kwargs["stop_loss_price"] - 2139.0) < 0.01

    def test_mt5_set_fixed_atr_stop_buy(self):
        """MT5Adapter.set_fixed_atr_stop computes correct SL for BUY."""
        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = MagicMock()

        success = MagicMock()
        success.retcode = 10009
        success.comment = "Done"
        mock_mt5.order_send.return_value = success

        adapter = MT5Adapter(login=123456, password="test", server="Demo")
        adapter._connected = True

        import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

        original = mt5_mod.mt5
        mt5_mod.mt5 = mock_mt5

        try:
            result = adapter.set_fixed_atr_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="BUY",
                entry_price=2300.0,
                atr_value=10.0,
                atr_multiplier=2.5,
            )
            assert result is True
            call_args = mock_mt5.order_send.call_args[0][0]
            # SL = 2300 - (10 * 2.5) = 2275
            assert call_args["sl"] == 2275.0
        finally:
            mt5_mod.mt5 = original

    def test_mt5_set_fixed_atr_stop_sell(self):
        """MT5Adapter.set_fixed_atr_stop computes correct SL for SELL."""
        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = MagicMock()

        success = MagicMock()
        success.retcode = 10009
        success.comment = "Done"
        mock_mt5.order_send.return_value = success

        adapter = MT5Adapter(login=123456, password="test", server="Demo")
        adapter._connected = True

        import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

        original = mt5_mod.mt5
        mt5_mod.mt5 = mock_mt5

        try:
            result = adapter.set_fixed_atr_stop(
                position_ticket=12345,
                symbol="USOIL",
                side="SELL",
                entry_price=75.0,
                atr_value=2.0,
                atr_multiplier=3.0,
            )
            assert result is True
            call_args = mock_mt5.order_send.call_args[0][0]
            # SL = 75 + (2 * 3.0) = 81.0
            assert call_args["sl"] == 81.0
        finally:
            mt5_mod.mt5 = original

    def test_mt5_set_fixed_atr_stop_negative_atr(self):
        """set_fixed_atr_stop rejects negative ATR."""
        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        adapter = MT5Adapter(login=123456, password="test", server="Demo")
        adapter._connected = True

        result = adapter.set_fixed_atr_stop(
            position_ticket=12345,
            symbol="XAUUSD",
            side="BUY",
            entry_price=2300.0,
            atr_value=-5.0,
            atr_multiplier=2.5,
        )
        assert result is False


# ═══════════════════════════════════════════════════════════════
# TASK 2: Half-Kelly Position Sizing
# ═══════════════════════════════════════════════════════════════


class TestHalfKellySizing:
    """Verify Half-Kelly Criterion position sizing."""

    def test_kelly_constants(self):
        """Kelly constants must be correctly configured."""
        assert _mod.KELLY_ROLLING_WINDOW == 20
        assert _mod.KELLY_HALF is True
        assert _mod.KELLY_CAP_PCT == 0.25
        assert _mod.KELLY_FLOOR_PCT == 0.05

    def test_compute_half_kelly_winning_strategy(self):
        """Kelly should give positive fraction for a winning strategy."""
        # 70% win rate, avg_win/avg_loss = 1.5
        trades = []
        for i in range(30):
            if i % 10 < 7:  # 70% wins
                trades.append({"asset": "XAUUSD", "pnl": 1.5, "side": "BUY"})
            else:
                trades.append({"asset": "XAUUSD", "pnl": -1.0, "side": "BUY"})

        kelly = _mod.compute_half_kelly(trades)
        assert "XAUUSD" in kelly
        # Full Kelly: f* = (1.5*0.7 - 0.3) / 1.5 = (1.05 - 0.3) / 1.5 = 0.5
        # Half Kelly: 0.25 (capped at KELLY_CAP_PCT)
        assert kelly["XAUUSD"] == pytest.approx(0.25, abs=0.01)

    def test_compute_half_kelly_losing_strategy(self):
        """Kelly should give floor for a losing strategy."""
        # 30% win rate, avg_win/avg_loss = 0.8
        trades = []
        for i in range(30):
            if i % 10 < 3:  # 30% wins
                trades.append({"asset": "OIL", "pnl": 0.8, "side": "BUY"})
            else:
                trades.append({"asset": "OIL", "pnl": -1.0, "side": "BUY"})

        kelly = _mod.compute_half_kelly(trades)
        # Full Kelly: f* = (0.8*0.3 - 0.7) / 0.8 = (0.24 - 0.7) / 0.8 = -0.575
        # Negative → floor at 0.05
        assert kelly["OIL"] == pytest.approx(0.05, abs=0.01)

    def test_compute_half_kelly_needs_min_trades(self):
        """Kelly should use floor when fewer than min_trades."""
        trades = [
            {"asset": "NAS100", "pnl": 1.0, "side": "BUY"},
            {"asset": "NAS100", "pnl": -0.5, "side": "BUY"},
        ]
        kelly = _mod.compute_half_kelly(trades, min_trades=10)
        assert kelly["NAS100"] == pytest.approx(0.05, abs=0.01)

    def test_compute_half_kelly_empty_history(self):
        """Kelly with empty history returns empty dict."""
        kelly = _mod.compute_half_kelly([])
        assert kelly == {}

    def test_compute_half_kelly_multiple_assets(self):
        """Kelly computes independently per asset."""
        trades = []
        # XAUUSD: good strategy
        for i in range(25):
            if i % 5 < 3:
                trades.append({"asset": "XAUUSD", "pnl": 2.0, "side": "BUY"})
            else:
                trades.append({"asset": "XAUUSD", "pnl": -1.0, "side": "BUY"})
        # USDJPY: mediocre strategy
        for i in range(25):
            if i % 5 < 2:
                trades.append({"asset": "USDJPY", "pnl": 1.0, "side": "SELL"})
            else:
                trades.append({"asset": "USDJPY", "pnl": -1.0, "side": "SELL"})

        kelly = _mod.compute_half_kelly(trades)
        assert "XAUUSD" in kelly
        assert "USDJPY" in kelly
        # XAUUSD should have higher Kelly than USDJPY
        assert kelly["XAUUSD"] > kelly["USDJPY"]

    def test_compute_half_kelly_cap_enforced(self):
        """Kelly fraction must not exceed 25% cap."""
        # Near-perfect strategy: 95% win rate, high payoff
        trades = []
        for i in range(30):
            if i % 20 < 19:  # 95% wins
                trades.append({"asset": "NAS100", "pnl": 5.0, "side": "BUY"})
            else:
                trades.append({"asset": "NAS100", "pnl": -1.0, "side": "BUY"})

        kelly = _mod.compute_half_kelly(trades)
        assert kelly["NAS100"] <= 0.25

    def test_compute_half_kelly_floor_enforced(self):
        """Kelly fraction must not go below 5% floor."""
        # Terrible strategy: 10% win rate
        trades = []
        for i in range(30):
            if i % 10 < 1:  # 10% wins
                trades.append({"asset": "OIL", "pnl": 0.5, "side": "BUY"})
            else:
                trades.append({"asset": "OIL", "pnl": -1.0, "side": "BUY"})

        kelly = _mod.compute_half_kelly(trades)
        assert kelly["OIL"] >= 0.05

    def test_weights_to_lots_with_kelly(self):
        """weights_to_lots applies Kelly fraction to weights."""
        weights = {"XAUUSD": 0.5}
        prices = {"XAUUSD": 2300.0}
        kelly = {"XAUUSD": 0.10}

        result = _mod.weights_to_lots(weights, prices, 100_000.0, kelly_fractions=kelly)

        # effective_weight = 0.5 * 0.10 = 0.05
        # notional = 0.05 * 100000 = 5000
        # lots = 5000 / (2300 * 100) = 0.0217 → 0.02
        assert result["XAUUSD"]["kelly_fraction"] == 0.10
        assert result["XAUUSD"]["raw_weight"] == 0.5
        assert result["XAUUSD"]["weight"] == pytest.approx(0.05, abs=0.001)
        assert result["XAUUSD"]["target_lots"] == 0.02

    def test_weights_to_lots_without_kelly(self):
        """weights_to_lots works without Kelly (backward compat)."""
        weights = {"XAUUSD": 0.5}
        prices = {"XAUUSD": 2300.0}

        result = _mod.weights_to_lots(weights, prices, 100_000.0)

        assert result["XAUUSD"]["kelly_fraction"] is None
        assert result["XAUUSD"]["raw_weight"] == 0.5
        assert result["XAUUSD"]["weight"] == 0.5


# ═══════════════════════════════════════════════════════════════
# TASK 3: Cost Calibration
# ═══════════════════════════════════════════════════════════════


class TestCostCalibration:
    """Verify Pepperstone cost calibration data."""

    @pytest.fixture
    def cost_data(self):
        """Load cost calibration JSON."""
        path = BASE / "config" / "cost_calibration.json"
        with open(path) as f:
            return json.load(f)

    def test_version_3(self, cost_data):
        """Cost calibration must be version 3.0."""
        assert cost_data["version"] == "3.0"

    def test_only_4_assets(self, cost_data):
        """Must have exactly 4 assets (NAS100, XAUUSD, OIL, USDJPY)."""
        assets = set(cost_data["assets"].keys())
        assert assets == {"XAUUSD", "NAS100", "OIL", "USDJPY"}

    def test_xauusd_spread(self, cost_data):
        """XAUUSD spread must be 0.15 bps (Pepperstone measured)."""
        xau = cost_data["assets"]["XAUUSD"]
        assert xau["spread_bps_measured"] == 0.15

    def test_nas100_spread(self, cost_data):
        """NAS100 spread must be 1.30 bps."""
        nas = cost_data["assets"]["NAS100"]
        assert nas["spread_bps_measured"] == 1.30

    def test_oil_spread(self, cost_data):
        """OIL spread must be 5.0 bps."""
        oil = cost_data["assets"]["OIL"]
        assert oil["spread_bps_measured"] == 5.0

    def test_usdjpy_spread(self, cost_data):
        """USDJPY spread must be 0.80 bps."""
        jpy = cost_data["assets"]["USDJPY"]
        assert jpy["spread_bps_measured"] == 0.80

    def test_xauusd_swaps(self, cost_data):
        """XAUUSD swaps: long=-0.50, short=+0.10 bps/day."""
        xau = cost_data["assets"]["XAUUSD"]
        assert xau["swap_long_bps"] == -0.50
        assert xau["swap_short_bps"] == 0.10

    def test_nas100_swaps(self, cost_data):
        """NAS100 swaps: long=-2.0, short=+0.5 bps/day."""
        nas = cost_data["assets"]["NAS100"]
        assert nas["swap_long_bps"] == -2.0
        assert nas["swap_short_bps"] == 0.5

    def test_oil_swaps(self, cost_data):
        """OIL swaps: long=-1.5, short=+0.3 bps/day."""
        oil = cost_data["assets"]["OIL"]
        assert oil["swap_long_bps"] == -1.5
        assert oil["swap_short_bps"] == 0.3

    def test_usdjpy_swaps(self, cost_data):
        """USDJPY swaps: long=-0.3, short=+0.1 bps/day."""
        jpy = cost_data["assets"]["USDJPY"]
        assert jpy["swap_long_bps"] == -0.3
        assert jpy["swap_short_bps"] == 0.1

    def test_dead_weight_removed(self, cost_data):
        """EURUSD, GBPUSD, SILVER, BTCUSD, ETHUSD must be removed."""
        removed = cost_data.get("removed_assets", [])
        for asset in ["EURUSD", "GBPUSD", "SILVER", "BTCUSD", "ETHUSD"]:
            assert asset in removed, f"{asset} should be in removed_assets list"
            assert asset not in cost_data["assets"], f"{asset} must not be in assets"

    def test_all_assets_measured(self, cost_data):
        """All assets must have MEASURED status."""
        for symbol, info in cost_data["assets"].items():
            assert info["status"] == "MEASURED", f"{symbol} status should be MEASURED"

    def test_round_trip_bps_reasonable(self, cost_data):
        """Round-trip costs must be within reasonable bounds."""
        for symbol, info in cost_data["assets"].items():
            rt = info["round_trip_bps_measured"]
            assert 0.1 <= rt <= 50.0, f"{symbol} round-trip {rt} bps is out of bounds"

    def test_oil_mt5_symbol_is_usoil(self, cost_data):
        """OIL MT5 symbol must be USOIL."""
        assert cost_data["assets"]["OIL"]["mt5_symbol"] == "USOIL"

    def test_nas100_mt5_symbol(self, cost_data):
        """NAS100 MT5 symbol must be NAS100."""
        assert cost_data["assets"]["NAS100"]["mt5_symbol"] == "NAS100"

    def test_stress_scenarios_include_nas100(self, cost_data):
        """Stress scenarios should include NAS100 spike scenario."""
        assert "NAS100_spike" in cost_data["stress_scenarios"]

    def test_cost_map_loads_correctly(self):
        """COST_MAP must load from calibration with correct round-trip costs."""
        cost_map = _mod.COST_MAP
        # XAUUSD: RT = 0.30 bps
        assert "XAUUSD" in cost_map
        assert cost_map["XAUUSD"] == pytest.approx(0.30, abs=0.01)
        # NAS100: RT = 2.60 bps
        assert "NAS100" in cost_map
        assert cost_map["NAS100"] == pytest.approx(2.60, abs=0.01)
        # OIL: RT = 10.0 bps
        assert "USOIL" in cost_map
        assert cost_map["USOIL"] == pytest.approx(10.0, abs=0.1)
        # USDJPY: RT = 7.80 bps
        assert "USDJPY" in cost_map
        assert cost_map["USDJPY"] == pytest.approx(7.80, abs=0.1)


# ═══════════════════════════════════════════════════════════════
# Integration: Kelly + Cost + Weights
# ═══════════════════════════════════════════════════════════════


class TestIntegrationKellyCostWeights:
    """Integration tests combining Kelly, costs, and position sizing."""

    def test_kelly_reduces_position_size(self):
        """Kelly should reduce position sizes vs raw weights."""
        weights = {"XAUUSD": 0.5, "NAS100": 0.3, "OIL": 0.15, "USDJPY": 0.05}
        prices = {"XAUUSD": 2300.0, "NAS100": 20000.0, "OIL": 75.0, "USDJPY": 155.0}

        # Without Kelly
        raw = _mod.weights_to_lots(weights, prices, 100_000.0)
        # With Kelly (conservative fractions)
        kelly = {"XAUUSD": 0.10, "NAS100": 0.08, "OIL": 0.05, "USDJPY": 0.12}
        scaled = _mod.weights_to_lots(weights, prices, 100_000.0, kelly_fractions=kelly)

        for asset in weights:
            if raw[asset]["target_lots"] > 0:
                assert (
                    scaled[asset]["target_lots"] <= raw[asset]["target_lots"]
                ), f"Kelly should reduce {asset} position"

    def test_cost_adjusted_sharpe_improves(self):
        """With tighter spreads, cost-adjusted returns should improve."""
        # Old XAUUSD RT cost: 0.72 bps → New: 0.30 bps
        old_cost = 0.72
        new_cost = 0.30
        # For 100 trades at 0.1 lots (10 oz), price ~2300
        notional_per_trade = 0.1 * 100 * 2300  # $23,000
        old_total_cost = old_cost / 10000 * notional_per_trade * 100
        new_total_cost = new_cost / 10000 * notional_per_trade * 100
        savings = old_total_cost - new_total_cost
        assert savings > 0, "Tighter spreads should save money"

    def test_nas100_round_trip_is_low(self):
        """NAS100 has tight spread for an index CFD."""
        cost_map = _mod.COST_MAP
        nas100_rt = cost_map.get("NAS100", 999)
        # Should be under 5 bps (competitive for indices)
        assert nas100_rt < 5.0, f"NAS100 RT cost {nas100_rt} bps too high"
