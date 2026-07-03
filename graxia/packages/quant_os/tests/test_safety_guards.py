"""Tests for MarketSessionGuard and SlippageGuard — safety features for order placement."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from graxia.packages.quant_os.execution.slippage_guard import (
    SlippageGuard,
)
from graxia.packages.quant_os.risk.market_session_guard import (
    MarketSessionGuard,
)

# ═══════════════════════════════════════════════════════════════
# MarketSessionGuard Tests
# ═══════════════════════════════════════════════════════════════


class TestMarketSessionGuard:
    """Tests for market session guard."""

    def setup_method(self):
        self.guard = MarketSessionGuard(mt5=None, buffer_minutes=5, check_holidays=False)

    # --- Crypto: always open except rollover ---

    def test_crypto_allowed_during_weekday(self):
        """Crypto trades 24/7 — should always be allowed."""
        now = datetime(2026, 7, 3, 14, 30, tzinfo=UTC)  # Friday afternoon
        result = self.guard.check("BTCUSD", now)
        assert result.allowed is True
        assert result.session == "24/7"

    def test_crypto_allowed_sunday(self):
        """Crypto trades on weekends."""
        now = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)  # Sunday
        result = self.guard.check("BTCUSD", now)
        assert result.allowed is True

    def test_crypto_blocked_during_rollover(self):
        """Crypto should be blocked during rollover window."""
        now = datetime(2026, 7, 3, 22, 0, tzinfo=UTC)  # 22:00 UTC = rollover
        result = self.guard.check("BTCUSD", now)
        assert result.allowed is False
        assert "rollover" in result.reason.lower()
        assert result.in_rollover is True

    # --- Forex session checks ---

    def test_forex_allowed_during_london(self):
        """Forex should be allowed during London session."""
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)  # 10:00 UTC = London
        result = self.guard.check("EURUSD", now)
        assert result.allowed is True
        assert result.session == "01:00–21:55 UTC"

    def test_forex_blocked_outside_session(self):
        """Forex should be blocked outside trading session."""
        now = datetime(2026, 7, 3, 23, 30, tzinfo=UTC)  # 23:30 UTC = closed
        result = self.guard.check("EURUSD", now)
        assert result.allowed is False
        assert result.market_open is False

    def test_forex_blocked_during_rollover(self):
        """Forex should be blocked during rollover window."""
        now = datetime(2026, 7, 3, 22, 5, tzinfo=UTC)  # 22:05 UTC = rollover
        result = self.guard.check("EURUSD", now)
        assert result.allowed is False
        assert result.in_rollover is True

    # --- Buffer checks (low-liquidity bookends) ---

    def test_forex_blocked_at_session_open(self):
        """Forex should be blocked within first 5 minutes of session open."""
        now = datetime(2026, 7, 3, 1, 3, tzinfo=UTC)  # 01:03 UTC = 3min after open
        result = self.guard.check("EURUSD", now)
        assert result.allowed is False
        assert result.in_buffer is True
        assert "session open" in result.reason.lower()

    def test_forex_allowed_after_buffer(self):
        """Forex should be allowed after 5-minute buffer from open."""
        now = datetime(2026, 7, 3, 1, 6, tzinfo=UTC)  # 01:06 UTC = 6min after open
        result = self.guard.check("EURUSD", now)
        assert result.allowed is True

    def test_forex_blocked_at_session_close(self):
        """Forex should be blocked within last 5 minutes of session close."""
        now = datetime(2026, 7, 3, 21, 51, tzinfo=UTC)  # 21:51 UTC = 4min before close
        result = self.guard.check("EURUSD", now)
        assert result.allowed is False
        assert result.in_buffer is True
        assert "session close" in result.reason.lower()

    def test_forex_allowed_before_close_buffer(self):
        """Forex should be allowed more than 5 minutes before session close."""
        now = datetime(2026, 7, 3, 21, 49, tzinfo=UTC)  # 21:49 UTC = 6min before close
        result = self.guard.check("EURUSD", now)
        assert result.allowed is True

    # --- Metals session ---

    def test_metals_allowed_during_session(self):
        """Gold should be allowed during its session."""
        now = datetime(2026, 7, 3, 15, 0, tzinfo=UTC)
        result = self.guard.check("XAUUSD", now)
        assert result.allowed is True

    def test_metals_blocked_at_open_buffer(self):
        """Gold blocked within 5min of session open."""
        now = datetime(2026, 7, 3, 1, 2, tzinfo=UTC)  # 2min after 01:00 open
        result = self.guard.check("XAUUSD", now)
        assert result.allowed is False
        assert result.in_buffer is True

    # --- should_skip convenience ---

    def test_should_skip_returns_tuple(self):
        """should_skip returns (bool, str)."""
        now = datetime(2026, 7, 3, 22, 0, tzinfo=UTC)  # rollover
        skip, reason = self.guard.should_skip("EURUSD", now)
        assert skip is True
        assert "rollover" in reason.lower()

    def test_should_skip_false_when_allowed(self):
        """should_skip returns (False, '') when trading is allowed."""
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)  # London session
        skip, reason = self.guard.should_skip("EURUSD", now)
        assert skip is False
        assert reason == ""

    # --- Custom buffer ---

    def test_custom_buffer_minutes(self):
        """Custom buffer minutes are respected."""
        guard = MarketSessionGuard(mt5=None, buffer_minutes=10, check_holidays=False)
        # 8 minutes after open — within 10min buffer
        now = datetime(2026, 7, 3, 1, 8, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is False
        assert result.in_buffer is True

        # 11 minutes after open — outside 10min buffer
        now = datetime(2026, 7, 3, 1, 11, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is True

    # --- MT5 trade_mode check ---

    def test_mt5_disabled_symbol_blocked(self):
        """Symbol with trade_mode=0 is blocked."""
        mt5_mock = MagicMock()
        info_mock = MagicMock()
        info_mock.trade_mode = 0
        info_mock.trade_allowed = True
        mt5_mock.symbol_info.return_value = info_mock

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is False
        assert "DISABLED" in result.reason

    def test_mt5_restricted_symbol_blocked(self):
        """Symbol with trade_mode=1 (LONGONLY) is blocked."""
        mt5_mock = MagicMock()
        info_mock = MagicMock()
        info_mock.trade_mode = 1
        info_mock.trade_allowed = True
        mt5_mock.symbol_info.return_value = info_mock

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is False
        assert "restricted" in result.reason.lower()

    def test_mt5_full_trading_allowed(self):
        """Symbol with trade_mode=4 (FULL) passes MT5 check."""
        mt5_mock = MagicMock()
        info_mock = MagicMock()
        info_mock.trade_mode = 4
        info_mock.trade_allowed = True
        mt5_mock.symbol_info.return_value = info_mock

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is True

    def test_mt5_trade_not_allowed_blocked(self):
        """Symbol with trade_allowed=False is blocked."""
        mt5_mock = MagicMock()
        info_mock = MagicMock()
        info_mock.trade_mode = 4
        info_mock.trade_allowed = False
        mt5_mock.symbol_info.return_value = info_mock

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is False
        assert "not allowed" in result.reason.lower()

    def test_mt5_symbol_info_none_fallback(self):
        """When MT5 returns None, fall through to session checks."""
        mt5_mock = MagicMock()
        mt5_mock.symbol_info.return_value = None

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        # Should pass because London session is open
        assert result.allowed is True

    def test_mt5_exception_fallback(self):
        """When MT5 raises, fall through to session checks."""
        mt5_mock = MagicMock()
        mt5_mock.symbol_info.side_effect = RuntimeError("MT5 not connected")

        guard = MarketSessionGuard(mt5=mt5_mock, check_holidays=True)
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now)
        assert result.allowed is True


# ═══════════════════════════════════════════════════════════════
# SlippageGuard Tests
# ═══════════════════════════════════════════════════════════════


class TestSlippageGuard:
    """Tests for slippage guard."""

    def setup_method(self):
        self.guard = SlippageGuard()

    # --- Basic threshold checks ---

    def test_buy_within_threshold(self):
        """BUY order within 8 bps should be allowed (EURUSD max=8bps)."""
        result = self.guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08508,  # 0.7 bps above expected
        )
        assert result.allowed is True
        assert result.deviation_bps < 8.0

    def test_buy_exceeds_threshold(self):
        """BUY order with >8 bps deviation should be rejected (EURUSD)."""
        result = self.guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08400,
            current_ask=1.08600,  # ~9.2 bps above expected
        )
        assert result.allowed is False
        assert "exceeds" in result.reason.lower()
        assert result.deviation_bps > 8.0

    def test_sell_within_threshold(self):
        """SELL order within threshold should be allowed."""
        result = self.guard.check(
            symbol="EURUSD",
            side="SELL",
            expected_price=1.08500,
            current_bid=1.08492,  # 0.7 bps below expected
            current_ask=1.08510,
        )
        assert result.allowed is True

    def test_sell_exceeds_threshold(self):
        """SELL order with large deviation should be rejected."""
        result = self.guard.check(
            symbol="EURUSD",
            side="SELL",
            expected_price=1.08500,
            current_bid=1.08350,  # ~13.8 bps below expected
            current_ask=1.08520,
        )
        assert result.allowed is False
        assert result.deviation_bps > 10.0

    # --- Crypto has wider tolerance ---

    def test_crypto_wider_tolerance(self):
        """BTCUSD allows up to 100 bps."""
        result = self.guard.check(
            symbol="BTCUSD",
            side="BUY",
            expected_price=50000.0,
            current_bid=49960.0,
            current_ask=50040.0,  # 8 bps — within 100 bps
        )
        assert result.allowed is True
        assert result.max_bps == 100.0

    def test_crypto_exceeds_tolerance(self):
        """BTCUSD rejects >100 bps."""
        result = self.guard.check(
            symbol="BTCUSD",
            side="BUY",
            expected_price=50000.0,
            current_bid=49800.0,
            current_ask=50200.0,  # 40 bps — still within 100 bps
        )
        # 40 bps < 100 bps, so allowed
        assert result.allowed is True

    def test_crypto_extreme_slippage(self):
        """BTCUSD rejects >100 bps deviation."""
        result = self.guard.check(
            symbol="BTCUSD",
            side="BUY",
            expected_price=50000.0,
            current_bid=49400.0,
            current_ask=50600.0,  # 120 bps — exceeds 100 bps
        )
        assert result.allowed is False
        assert result.deviation_bps > 100.0

    # --- Custom thresholds ---

    def test_custom_max_bps_global(self):
        """Global max_bps override — use symbol without override."""
        guard = SlippageGuard(max_bps=5.0, symbol_overrides={})
        result = guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08550,  # 4.6 bps — within 5 bps global
        )
        assert result.allowed is True
        assert result.max_bps == 5.0

    def test_custom_max_bps_symbol_override(self):
        """Per-symbol override takes precedence over global."""
        guard = SlippageGuard(max_bps=5.0, symbol_overrides={"EURUSD": 3.0})
        result = guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08530,  # 2.8 bps — within 3 bps override
        )
        assert result.allowed is True
        assert result.max_bps == 3.0

    def test_custom_max_bps_exceeded(self):
        """Reject when custom threshold exceeded — use symbol without override."""
        guard = SlippageGuard(max_bps=5.0, symbol_overrides={})
        result = guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08560,  # 5.5 bps — exceeds 5 bps global
        )
        assert result.allowed is False
        assert result.deviation_bps > 5.0

    # --- Edge cases ---

    def test_zero_expected_price_rejected(self):
        """Zero expected price should be rejected."""
        result = self.guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=0.0,
            current_bid=1.0850,
            current_ask=1.0852,
        )
        assert result.allowed is False
        assert "invalid price" in result.reason.lower()

    def test_zero_exec_price_rejected(self):
        """Zero execution price should be rejected."""
        result = self.guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.0850,
            current_bid=0.0,
            current_ask=0.0,
        )
        assert result.allowed is False

    def test_unknown_side_rejected(self):
        """Unknown side should be rejected."""
        result = self.guard.check(
            symbol="EURUSD",
            side="CLOSE",
            expected_price=1.0850,
            current_bid=1.0849,
            current_ask=1.0851,
        )
        assert result.allowed is False
        assert "unknown side" in result.reason.lower()

    def test_exact_price_match(self):
        """Exact price match should be allowed with 0 deviation."""
        result = self.guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08500,
        )
        assert result.allowed is True
        assert result.deviation_bps == 0.0

    # --- should_reject convenience ---

    def test_should_reject_returns_tuple(self):
        """should_reject returns (bool, str)."""
        reject, reason = self.guard.should_reject(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08400,
            current_ask=1.08600,
        )
        assert reject is True
        assert "exceeds" in reason.lower()

    def test_should_reject_false_when_within_threshold(self):
        """should_reject returns (False, '') when within threshold."""
        reject, reason = self.guard.should_reject(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08490,
            current_ask=1.08505,
        )
        assert reject is False
        assert reason == ""

    # --- Metals tolerance ---

    def test_xauusd_moderate_tolerance(self):
        """XAUUSD has 25 bps tolerance."""
        result = self.guard.check(
            symbol="XAUUSD",
            side="BUY",
            expected_price=2350.00,
            current_bid=2349.00,
            current_ask=2350.50,  # ~2.1 bps
        )
        assert result.allowed is True
        assert result.max_bps == 25.0

    def test_xauusd_exceeds_tolerance(self):
        """XAUUSD rejects >25 bps."""
        result = self.guard.check(
            symbol="XAUUSD",
            side="BUY",
            expected_price=2350.00,
            current_bid=2348.00,
            current_ask=2356.00,  # ~25.5 bps
        )
        assert result.allowed is False


# ═══════════════════════════════════════════════════════════════
# Integration: Session + Slippage Combined
# ═══════════════════════════════════════════════════════════════


class TestCombinedGuards:
    """Test that both guards can be composed together."""

    def test_session_blocks_before_slippage_checked(self):
        """Session guard should block before slippage is even considered."""
        session_guard = MarketSessionGuard(mt5=None, buffer_minutes=5, check_holidays=False)
        slippage_guard = SlippageGuard()

        # 22:30 UTC = rollover — session blocks
        now = datetime(2026, 7, 3, 22, 30, tzinfo=UTC)
        skip, reason = session_guard.should_skip("EURUSD", now)
        assert skip is True
        # Slippage never checked

    def test_slippage_blocks_within_session(self):
        """Within session, slippage guard can still reject."""
        session_guard = MarketSessionGuard(mt5=None, buffer_minutes=5, check_holidays=False)
        slippage_guard = SlippageGuard()

        # 10:00 UTC = London session — allowed
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        skip, _ = session_guard.should_skip("EURUSD", now)
        assert skip is False

        # But slippage exceeds threshold
        result = slippage_guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08400,
            current_ask=1.08600,
        )
        assert result.allowed is False

    def test_both_pass_allows_trade(self):
        """Both guards passing allows the trade."""
        session_guard = MarketSessionGuard(mt5=None, buffer_minutes=5, check_holidays=False)
        slippage_guard = SlippageGuard()

        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        skip, _ = session_guard.should_skip("EURUSD", now)
        assert skip is False

        result = slippage_guard.check(
            symbol="EURUSD",
            side="BUY",
            expected_price=1.08500,
            current_bid=1.08495,
            current_ask=1.08503,
        )
        assert result.allowed is True
