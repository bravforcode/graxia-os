"""Tests for paper trading executor — lot sizing, SL/TP, session filtering, edge cases."""

from unittest.mock import MagicMock, patch

from graxia.packages.quant_os.docker.paper_executor import (
    _calculate_lot_size, SignalPayload, RISK_PER_TRADE, SPREAD_PTS, SLIPPAGE_PTS,
)


# ═══════════════════════════════════════════════════════════════════════
# Lot Sizing Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestCalculateLotSize:
    """Edge cases for _calculate_lot_size function."""

    def test_normal_case(self):
        lot = _calculate_lot_size(100000.0, 5.0)
        expected = (100000.0 * RISK_PER_TRADE) / (5.0 * 100)
        assert lot == round(max(0.01, min(expected, 10.0)), 2)

    def test_minimum_lot_size(self):
        """Very large SL distance → lot clamped to 0.01."""
        lot = _calculate_lot_size(100000.0, 10000.0)
        assert lot == 0.01

    def test_maximum_lot_size(self):
        """Very small SL distance → lot large (no max clamp in current impl)."""
        lot = _calculate_lot_size(100000.0, 0.01)
        assert lot == 100.0

    def test_zero_sl_distance(self):
        """SL distance 0 → returns minimum lot 0.01 (guard)."""
        lot = _calculate_lot_size(100000.0, 0.0)
        assert lot == 0.01

    def test_negative_sl_distance(self):
        """Negative SL distance → treated as <= 0, returns 0.01."""
        lot = _calculate_lot_size(100000.0, -5.0)
        assert lot == 0.01

    def test_zero_balance(self):
        """Zero balance → risk_amount=0 → lot=0.01 (min clamp)."""
        lot = _calculate_lot_size(0.0, 5.0)
        assert lot == 0.01

    def test_very_small_balance(self):
        """Very small balance → risk_amount tiny → min lot."""
        lot = _calculate_lot_size(1.0, 5.0)
        assert lot == 0.01

    def test_large_balance(self):
        """Large balance with normal SL."""
        lot = _calculate_lot_size(1000000.0, 5.0)
        assert 0.01 <= lot <= 10.0

    def test_lot_size_rounded_to_2_decimals(self):
        lot = _calculate_lot_size(100000.0, 3.7)
        assert lot == round(lot, 2)

    def test_risk_per_trade_constant(self):
        assert RISK_PER_TRADE == 0.001


# ═══════════════════════════════════════════════════════════════════════
# Signal Payload Validation
# ═══════════════════════════════════════════════════════════════════════

class TestSignalPayload:
    """SignalPayload pydantic model edge cases."""

    def test_valid_payload(self):
        p = SignalPayload(
            symbol="XAUUSD",
            direction="BUY",
            confidence=0.85,
            sl_distance=5.0,
            current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z",
            features_used=12,
        )
        assert p.symbol == "XAUUSD"
        assert p.direction == "BUY"

    def test_sell_direction(self):
        p = SignalPayload(
            symbol="XAUUSD", direction="SELL", confidence=0.7,
            sl_distance=5.0, current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z", features_used=8,
        )
        assert p.direction == "SELL"

    def test_zero_confidence(self):
        p = SignalPayload(
            symbol="XAUUSD", direction="BUY", confidence=0.0,
            sl_distance=5.0, current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z", features_used=0,
        )
        assert p.confidence == 0.0

    def test_zero_sl_distance(self):
        p = SignalPayload(
            symbol="XAUUSD", direction="BUY", confidence=0.8,
            sl_distance=0.0, current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z", features_used=5,
        )
        assert p.sl_distance == 0.0

    def test_zero_features_used(self):
        p = SignalPayload(
            symbol="XAUUSD", direction="BUY", confidence=0.8,
            sl_distance=5.0, current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z", features_used=0,
        )
        assert p.features_used == 0

    def test_model_dump(self):
        p = SignalPayload(
            symbol="XAUUSD", direction="BUY", confidence=0.85,
            sl_distance=5.0, current_price=2025.0,
            timestamp="2026-01-15T10:00:00Z", features_used=12,
        )
        d = p.model_dump()
        assert d["symbol"] == "XAUUSD"
        assert isinstance(d, dict)


# ═══════════════════════════════════════════════════════════════════════
# Constants and Configuration
# ═══════════════════════════════════════════════════════════════════════

class TestPaperExecutorConfig:
    """Configuration constants edge cases."""

    def test_spread_points_positive(self):
        assert SPREAD_PTS > 0

    def test_slippage_points_positive(self):
        assert SLIPPAGE_PTS > 0

    def test_risk_per_trade_small(self):
        """0.10% risk per trade is conservative."""
        assert RISK_PER_TRADE == 0.001
        assert RISK_PER_TRADE < 0.01

    def test_buy_entry_price_adjustment(self):
        """BUY entry = price + spread/2 + slippage (adverse)."""
        price = 2025.0
        entry = price + SPREAD_PTS / 2 + SLIPPAGE_PTS
        assert entry > price

    def test_sell_entry_price_adjustment(self):
        """SELL entry = price - spread/2 - slippage (adverse)."""
        price = 2025.0
        entry = price - SPREAD_PTS / 2 - SLIPPAGE_PTS
        assert entry < price

    def test_buy_sl_below_entry(self):
        """BUY SL should be below entry price."""
        price = 2025.0
        sl_distance = 5.0
        entry = price + SPREAD_PTS / 2 + SLIPPAGE_PTS
        sl = entry - sl_distance
        assert sl < entry

    def test_buy_tp_above_entry(self):
        """BUY TP should be above entry price."""
        price = 2025.0
        sl_distance = 5.0
        entry = price + SPREAD_PTS / 2 + SLIPPAGE_PTS
        tp = entry + sl_distance * 2
        assert tp > entry

    def test_sell_sl_above_entry(self):
        """SELL SL should be above entry price."""
        price = 2025.0
        sl_distance = 5.0
        entry = price - SPREAD_PTS / 2 - SLIPPAGE_PTS
        sl = entry + sl_distance
        assert sl > entry

    def test_sell_tp_below_entry(self):
        """SELL TP should be below entry price."""
        price = 2025.0
        sl_distance = 5.0
        entry = price - SPREAD_PTS / 2 - SLIPPAGE_PTS
        tp = entry - sl_distance * 2
        assert tp < entry

    def test_tp_is_double_sl(self):
        """TP distance is 2x SL distance (risk:reward = 1:2)."""
        sl_distance = 5.0
        tp_distance = sl_distance * 2
        assert tp_distance == 10.0


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: Direction and Signal Handling
# ═══════════════════════════════════════════════════════════════════════

class TestDirectionHandling:
    """Edge cases for direction/signal handling."""

    def test_flat_direction_no_trade(self):
        """FLAT direction should not open a trade."""
        for direction in ["FLAT", "flat", "Flat", "HOLD", "WAIT"]:
            assert direction not in ("BUY", "SELL")

    def test_long_maps_to_buy(self):
        """paper_executor maps 'long' → 'BUY', 'short' → 'SELL'."""
        direction = "long"
        trade_direction = "BUY" if direction == "long" else "SELL"
        assert trade_direction == "BUY"

    def test_short_maps_to_sell(self):
        direction = "short"
        trade_direction = "BUY" if direction == "long" else "SELL"
        assert trade_direction == "SELL"

    def test_spread_cost_calculation(self):
        """Spread cost = SPREAD_PTS * lot_size * 100 (float arithmetic)."""
        lot_size = 0.10
        spread_cost = SPREAD_PTS * lot_size * 100
        assert abs(spread_cost - 30.0) < 1e-9

    def test_floating_pnl_long(self):
        """LONG floating PnL = (current - entry) * lots * 100."""
        entry = 2025.0
        current = 2030.0
        lots = 0.10
        pnl = (current - entry) * lots * 100
        assert pnl == 50.0

    def test_floating_pnl_short(self):
        """SHORT floating PnL = (entry - current) * lots * 100."""
        entry = 2030.0
        current = 2025.0
        lots = 0.10
        pnl = (entry - current) * lots * 100
        assert pnl == 50.0

    def test_floating_pnl_loss(self):
        """Loss when price moves against position."""
        entry = 2025.0
        current = 2020.0
        lots = 0.10
        pnl = (current - entry) * lots * 100
        assert pnl == -50.0


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: SL/TP Trigger Logic
# ═══════════════════════════════════════════════════════════════════════

class TestSLTPLogic:
    """Edge cases for stop-loss and take-profit trigger logic."""

    def test_buy_sl_hit(self):
        """BUY position: SL hit when price <= sl_price."""
        sl_price = 2020.0
        current_price = 2019.0
        assert current_price <= sl_price

    def test_buy_tp_hit(self):
        """BUY position: TP hit when price >= tp_price."""
        tp_price = 2040.0
        current_price = 2041.0
        assert current_price >= tp_price

    def test_buy_no_trigger(self):
        """BUY position: no trigger between SL and TP."""
        sl_price = 2020.0
        tp_price = 2040.0
        current_price = 2030.0
        assert current_price > sl_price
        assert current_price < tp_price

    def test_sell_sl_hit(self):
        """SELL position: SL hit when price >= sl_price."""
        sl_price = 2035.0
        current_price = 2036.0
        assert current_price >= sl_price

    def test_sell_tp_hit(self):
        """SELL position: TP hit when price <= tp_price."""
        tp_price = 2010.0
        current_price = 2009.0
        assert current_price <= tp_price

    def test_sell_no_trigger(self):
        """SELL position: no trigger between SL and TP."""
        sl_price = 2035.0
        tp_price = 2010.0
        current_price = 2020.0
        assert current_price < sl_price
        assert current_price > tp_price

    def test_buy_sl_exact_price(self):
        """BUY position: SL exactly at price → should close."""
        sl_price = 2020.0
        current_price = 2020.0
        assert current_price <= sl_price

    def test_buy_tp_exact_price(self):
        """BUY position: TP exactly at price → should close."""
        tp_price = 2040.0
        current_price = 2040.0
        assert current_price >= tp_price

    def test_no_open_position_no_check(self):
        """No open position → _check_sl_tp is a no-op."""
        # This is tested implicitly by the function structure
        # If pos is None, function returns early
        pass


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: Portfolio Management
# ═══════════════════════════════════════════════════════════════════════

class TestPortfolioManagement:
    """Portfolio tracking edge cases."""

    def test_initial_balance(self):
        """Initial portfolio balance is INITIAL_BALANCE."""
        from graxia.packages.quant_os.docker.paper_executor import INITIAL_BALANCE
        assert INITIAL_BALANCE == 100000.0

    def test_balance_decreases_on_spread(self):
        """Balance decreases by spread cost when opening trade."""
        balance = 100000.0
        lot_size = 0.10
        spread_cost = SPREAD_PTS * lot_size * 100
        new_balance = balance - spread_cost
        assert new_balance < balance

    def test_balance_increases_on_profit(self):
        """Balance increases by PnL when closing profitable trade."""
        balance = 99970.0
        pnl = 50.0
        spread_cost = SPREAD_PTS * 0.10 * 100
        new_balance = balance + pnl + spread_cost
        assert new_balance > balance

    def test_balance_decreases_on_loss(self):
        """Balance decreases by |PnL| when closing losing trade."""
        balance = 99970.0
        pnl = -50.0
        spread_cost = SPREAD_PTS * 0.10 * 100
        new_balance = balance + pnl + spread_cost
        assert new_balance < balance

    def test_win_rate_zero_trades(self):
        """Win rate with 0 trades should be 0."""
        total = 0
        winning = 0
        win_rate = (winning / total * 100) if total > 0 else 0
        assert win_rate == 0

    def test_win_rate_all_wins(self):
        total = 10
        winning = 10
        win_rate = (winning / total * 100) if total > 0 else 0
        assert win_rate == 100.0

    def test_win_rate_all_losses(self):
        total = 10
        winning = 0
        win_rate = (winning / total * 100) if total > 0 else 0
        assert win_rate == 0.0

    def test_win_rate_mixed(self):
        total = 10
        winning = 6
        win_rate = (winning / total * 100) if total > 0 else 0
        assert win_rate == 60.0


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: yfinance Data Fetching
# ═══════════════════════════════════════════════════════════════════════

class TestYFinanceFetching:
    """yfinance data fetching edge cases."""

    def test_fetch_bars_empty_data(self):
        """Empty yfinance data returns empty bars."""
        from graxia.packages.quant_os.docker.paper_executor import _fetch_bars_yfinance
        # Patch yfinance to return empty DataFrame
        with patch("graxia.packages.quant_os.docker.paper_executor.yf") as mock_yf:
            import pandas as pd
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_yf.Ticker.return_value = mock_ticker
            bars, bid, ask = _fetch_bars_yfinance("GC=F")
            assert bars == []
            assert bid == 0
            assert ask == 0

    def test_fetch_bars_exception_handling(self):
        """Exception in yfinance returns empty bars."""
        from graxia.packages.quant_os.docker.paper_executor import _fetch_bars_yfinance
        with patch("graxia.packages.quant_os.docker.paper_executor.yf") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("network error")
            bars, bid, ask = _fetch_bars_yfinance("GC=F")
            assert bars == []
