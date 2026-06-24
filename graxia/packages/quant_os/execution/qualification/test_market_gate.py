"""Tests for market_gate — mock MT5, cover all gate conditions."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ponytail: test isolation — import after mock setup in each test


def _make_mock_tick(bid=2500.0, ask=2510.0, time_msc=None):
    t = MagicMock()
    t.bid = bid
    t.ask = ask
    t.time_msc = time_msc or int(datetime.now(timezone.utc).timestamp() * 1000)
    return t


def _make_mock_terminal(connected=True, trade_allowed=True):
    t = MagicMock()
    t.connected = connected
    t.trade_allowed = trade_allowed
    return t


def _make_mock_symbol(trade_mode=3):  # 3 = SYMBOL_TRADE_EXECUTION
    s = MagicMock()
    s.trade_mode = trade_mode
    return s


def _patch_mt5(dry_run=False, terminal=None, symbol=None, tick=None,
               positions=None, orders=None, init_ok=True):
    """Patch DRY_RUN_MODE and insert mock mt5 into sys.modules."""
    mt5 = MagicMock()
    mt5.initialize.return_value = init_ok
    mt5.terminal_info.return_value = terminal
    mt5.symbol_info.return_value = symbol
    mt5.symbol_info_tick.return_value = tick
    mt5.positions_get.return_value = positions
    mt5.orders_get.return_value = orders

    patcher_module = patch.dict("sys.modules", {"MetaTrader5": mt5})
    patcher_dry = patch("execution.qualification.market_gate.DRY_RUN_MODE", dry_run)

    return mt5, patcher_module, patcher_dry


class TestMarketGate:
    """Market gate conditions — each test covers one fail path."""

    def test_passes_when_all_ok(self):
        """Market open, spread OK, no positions/orders, not expired."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[],
            orders=[],
        )
        with pm, pd:
            # ensure we're in a non-closed session
            from execution.qualification.market_gate import _determine_session
            session = _determine_session()
            if session == "closed":
                pytest.skip("test only valid during market hours")

            result = check_market_open(spread_cap=50.0)

        assert result.passed is True
        assert result.reason is None
        assert result.spread == 3.0

    def test_fails_when_market_closed(self):
        """Session closed → block immediately."""
        from execution.qualification.market_gate import check_market_open

        with patch("execution.qualification.market_gate._determine_session",
                   return_value="closed"):
            result = check_market_open()

        assert result.passed is False
        assert "Market closed" in result.reason

    def test_fails_when_plan_expired(self):
        """Plan expiry in the past → block."""
        from execution.qualification.market_gate import check_market_open

        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[],
            orders=[],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open(plan_expiry=expired)

        assert result.passed is False
        assert "expired" in result.reason.lower()

    def test_fails_when_spread_exceeds_cap(self):
        """Spread > cap → block."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2600.0, now),  # spread=100
            positions=[],
            orders=[],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open(spread_cap=50.0)

        assert result.passed is False
        assert "Spread" in result.reason
        assert result.spread == 100.0

    def test_fails_when_positions_exist(self):
        """Open positions → block."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        pos = MagicMock()
        pos.ticket = 12345

        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[pos],
            orders=[],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open()

        assert result.passed is False
        assert "position" in result.reason.lower()
        assert result.positions_exist is True

    def test_fails_when_terminal_disconnected(self):
        """Terminal not connected → block."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(connected=False),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[],
            orders=[],
            init_ok=True,
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open()

        assert result.passed is False
        assert "not connected" in result.reason.lower()
        assert result.terminal_connected is False

    def test_fails_when_symbol_not_open(self):
        """Symbol trade_mode=0 (disabled) → block."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(trade_mode=0),  # trading disabled
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[],
            orders=[],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open()

        assert result.passed is False
        assert "not open" in result.reason.lower() or "trade_mode" in result.reason
        assert result.symbol_open is False

    def test_fails_when_pending_orders_exist(self):
        """Pending orders → block."""
        from execution.qualification.market_gate import check_market_open

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        order = MagicMock()
        order.ticket = 99999

        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, now),
            positions=[],
            orders=[order],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open()

        assert result.passed is False
        assert "pending" in result.reason.lower()
        assert result.pending_orders_exist is True

    def test_dry_run_mode_passes_without_mt5(self):
        """DRY_RUN_MODE=True returns passed without MT5 calls."""
        from execution.qualification.market_gate import check_market_open

        with patch("execution.qualification.market_gate.DRY_RUN_MODE", True):
            with patch("execution.qualification.market_gate._determine_session",
                       return_value="london"):
                result = check_market_open()

        assert result.passed is True
        assert result.terminal_connected is True

    def test_fails_when_tick_stale(self):
        """Tick older than tick_max_age → block."""
        from execution.qualification.market_gate import check_market_open

        old_ms = int((datetime.now(timezone.utc).timestamp() - 120) * 1000)  # 120s old
        mt5, pm, pd = _patch_mt5(
            dry_run=False,
            terminal=_make_mock_terminal(),
            symbol=_make_mock_symbol(),
            tick=_make_mock_tick(2500.0, 2503.0, old_ms),
            positions=[],
            orders=[],
        )
        with patch("execution.qualification.market_gate._determine_session",
                   return_value="london"), pm, pd:
            result = check_market_open(tick_max_age=60.0)

        assert result.passed is False
        assert "stale" in result.reason.lower()
        assert result.tick_fresh is False
