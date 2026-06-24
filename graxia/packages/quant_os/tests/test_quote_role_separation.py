"""G3.2.4: Execution quote and time audit role separation tests.

Divergence is diagnostic only — never blocks execution.
No order_send path. No broker mutation.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shadow.canonical_tick_authority import (
    query_canonical_utc_tick,
    check_execution_quote_available,
    check_canonical_tick_audit,
    check_native_quote_divergence,
    is_time_authority_consistent,
    EXECUTION_QUOTE_AVAILABLE,
    EXECUTION_QUOTE_UNAVAILABLE,
    CANONICAL_TICK_AUDIT_PASS,
    CANONICAL_TICK_AUDIT_FAIL,
    TIME_SOURCE_CONSISTENT,
    CANONICAL_TICK_STALE,
    CANONICAL_TICK_MISSING,
    CANONICAL_TICK_FUTURE,
    CANONICAL_TICK_OUTSIDE_WINDOW,
)


class FakeTick:
    def __getitem__(self, idx):
        return self._data[idx]
    def __init__(self, time_sec, bid, ask, last=0, volume=100, flags=0, time_msc=0):
        self._data = (time_sec, time_msc, bid, ask, last, volume, flags)
    def __len__(self): return len(self._data)
    def __iter__(self): return iter(self._data)


def _fresh_evidence(mt5_module=None):
    """Build fresh canonical tick evidence."""
    if mt5_module is None:
        mt5_module = MagicMock()
    now = datetime.now(timezone.utc)
    tick_time = now.timestamp() - 1
    mt5_module.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
    ev = query_canonical_utc_tick(mt5_module, "XAUUSD")
    return ev


# ── Execution Quote Availability ──


class TestExecutionQuoteAvailable:
    """Valid execution quote + fresh canonical audit tick passes."""

    def test_all_conditions_met(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_AVAILABLE
        assert ev.native_bid_valid
        assert ev.native_ask_valid
        assert ev.canonical_tick_fresh
        assert ev.terminal_connected
        assert ev.position_count == 0
        assert ev.order_count == 0
        assert ev.feature_gate_off
        assert ev.kill_switch_on

    def test_terminal_disconnected_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=False, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE

    def test_positions_open_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=3, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE

    def test_orders_pending_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=2,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE

    def test_feature_gate_on_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=False, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE

    def test_kill_switch_off_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=False,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE


# ── Native/Canonical Price Divergence — Diagnostic Only ──


class TestDivergenceDiagnosticOnly:
    """Native/canonical price divergence does NOT block execution."""

    def test_divergent_prices_still_available(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4200.0, native_ask=4200.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_AVAILABLE

    def test_divergence_recorded_as_diagnostic(self):
        ev = _fresh_evidence()
        ev = check_native_quote_divergence(ev, 4200.0, 4200.18, 0.01, 5)
        # Divergence recorded but execution not blocked
        assert ev.quote_price_divergence_ticks is not None
        assert ev.quote_price_divergence_ticks > 50

    def test_coherent_prices_diagnostic(self):
        ev = _fresh_evidence()
        ev = check_native_quote_divergence(ev, 4120.0, 4120.18, 0.01, 5)
        assert ev.quote_price_divergence_passed

    def test_divergence_does_not_override_execution_status(self):
        """Execution quote status determined solely by check_execution_quote_available."""
        ev = _fresh_evidence()
        ev = check_native_quote_divergence(ev, 4300.0, 4300.18, 0.01, 5)
        ev = check_execution_quote_available(
            ev, native_bid=4300.0, native_ask=4300.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_AVAILABLE
        assert ev.quote_coherence_status == "QUOTE_SOURCE_DIVERGENT"


# ── Invalid Native Bid/Ask Blocks ──


class TestInvalidNativeBlocks:
    """Invalid native bid/ask blocks execution quote."""

    def test_native_bid_zero_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=0.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE
        assert not ev.native_bid_valid

    def test_native_ask_zero_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=0.0,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE
        assert not ev.native_ask_valid

    def test_native_bid_none_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=None, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE

    def test_native_ask_below_bid_blocks(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4119.0,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE
        assert not ev.native_ask_valid


# ── Missing/Stale/Future Canonical Audit Tick Blocks ──


class TestCanonicalAuditTick:
    """Canonical tick audit conditions."""

    def test_fresh_canonical_tick_passes(self):
        ev = _fresh_evidence()
        ev = check_canonical_tick_audit(ev)
        assert ev.canonical_audit_status == CANONICAL_TICK_AUDIT_PASS
        assert ev.audit_tick_valid
        assert ev.audit_timestamp_inside_window
        assert ev.audit_age_within_bounds
        assert ev.audit_no_future_tick

    def test_stale_canonical_tick_fails(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now - timedelta(seconds=30)).timestamp()
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        ev = check_canonical_tick_audit(ev)
        assert ev.canonical_audit_status == CANONICAL_TICK_AUDIT_FAIL
        assert not ev.audit_age_within_bounds

    def test_future_canonical_tick_fails(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now + timedelta(hours=1)).timestamp()
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        ev = check_canonical_tick_audit(ev)
        assert ev.canonical_audit_status == CANONICAL_TICK_AUDIT_FAIL
        assert not ev.audit_no_future_tick

    def test_missing_canonical_tick_fails(self):
        mt5 = MagicMock()
        mt5.copy_ticks_range.return_value = None
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        ev = check_canonical_tick_audit(ev)
        assert ev.canonical_audit_status == CANONICAL_TICK_AUDIT_FAIL
        assert not ev.audit_tick_valid

    def test_outside_window_canonical_tick_fails(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now - timedelta(hours=2)).timestamp()
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        ev = check_canonical_tick_audit(ev)
        assert ev.canonical_audit_status == CANONICAL_TICK_AUDIT_FAIL
        assert not ev.audit_timestamp_inside_window


# ── Native Timestamp Not Used as UTC Authority ──


class TestNativeTimestampNotAuthority:
    """Native timestamp is never used as UTC authority."""

    def test_native_time_not_in_evidence(self):
        ev = _fresh_evidence()
        # native_quote_time is set but marked UNTRUSTED
        assert ev.native_quote_timestamp_status == "UNTRUSTED_NATIVE_TIMESTAMP"

    def test_canonical_time_is_utc(self):
        ev = _fresh_evidence()
        parsed = datetime.fromisoformat(ev.canonical_tick_time_utc)
        assert parsed.tzinfo is not None


# ── No order_send Path ──


class TestNoOrderSend:
    """No order_send path exists in quote/audit functions."""

    def test_no_order_send_in_execution_check(self):
        import inspect
        source = inspect.getsource(check_execution_quote_available)
        assert "order_send" not in source.lower()
        assert "OrderSend" not in source

    def test_no_order_send_in_audit_check(self):
        import inspect
        source = inspect.getsource(check_canonical_tick_audit)
        assert "order_send" not in source.lower()
        assert "OrderSend" not in source

    def test_no_order_send_in_query(self):
        import inspect
        source = inspect.getsource(query_canonical_utc_tick)
        assert "order_send" not in source.lower()
        assert "OrderSend" not in source


# ── No Broker Mutation ──


class TestNoBrokerMutation:
    """Quote/audit functions must not mutate broker state."""

    def test_no_position_open_close(self):
        import inspect
        for fn in [check_execution_quote_available, check_canonical_tick_audit, query_canonical_utc_tick]:
            source = inspect.getsource(fn)
            assert "position" not in source.lower() or "position_count" in source
            assert "close_position" not in source.lower()
            assert "open_position" not in source.lower()

    def test_no_order_send_anywhere(self):
        """Verify entire module has no order_send calls."""
        import inspect
        from shadow import canonical_tick_authority
        source = inspect.getsource(canonical_tick_authority)
        assert "order_send" not in source.lower()


# ── Execution Quote Used for Order Check Geometry ──


class TestExecutionQuoteForOrderCheck:
    """Execution quote available for order_check geometry."""

    def test_execution_quote_provides_bid_ask(self):
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_AVAILABLE
        assert ev.native_bid_valid
        assert ev.native_ask_valid

    def test_divergent_quote_still_usable_for_geometry(self):
        """Even divergent native prices are usable for order geometry."""
        ev = _fresh_evidence()
        ev = check_execution_quote_available(
            ev, native_bid=4200.0, native_ask=4200.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_AVAILABLE
        assert ev.native_quote_bid == 4200.0
        assert ev.native_quote_ask == 4200.18

    def test_stale_canonical_blocks_execution(self):
        """Stale canonical tick → execution unavailable."""
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now - timedelta(seconds=30)).timestamp()
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        ev = check_execution_quote_available(
            ev, native_bid=4120.0, native_ask=4120.18,
            terminal_connected=True, position_count=0, order_count=0,
            feature_gate_off=True, kill_switch_on=True,
        )
        assert ev.execution_quote_status == EXECUTION_QUOTE_UNAVAILABLE
