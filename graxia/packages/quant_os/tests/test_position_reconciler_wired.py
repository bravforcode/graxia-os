"""
Unit tests for PositionReconciler (execution.position_reconciler).

Covers:
  - Basic match: internal == broker → matched=True
  - Quantity mismatch → QTY_MISMATCH
  - Position missing from broker → MISSING_FROM_BROKER
  - Extra position at broker → EXTRA_AT_BROKER
  - Multiple drifts increment drift_count
"""

from __future__ import annotations

from decimal import Decimal

from graxia.packages.quant_os.execution.position_reconciler import (
    BrokerPosition,
    InternalPosition,
    PositionReconciler,
    ReconciliationConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _internal(symbol: str = "EURUSD", side: str = "LONG", qty: str = "0.10", price: str = "1.0850") -> InternalPosition:
    return InternalPosition(
        symbol=symbol,
        side=side,
        quantity=Decimal(qty),
        entry_price=Decimal(price),
    )


def _broker(symbol: str = "EURUSD", side: str = "LONG", qty: str = "0.10", price: str = "1.0850") -> BrokerPosition:
    return BrokerPosition(
        symbol=symbol,
        side=side,
        quantity=Decimal(qty),
        avg_price=Decimal(price),
    )


# ---------------------------------------------------------------------------
# Basic match
# ---------------------------------------------------------------------------


class TestReconcilerBasicMatch:
    """Positions that match exactly → matched=True, no drift."""

    def test_single_position_match(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker()],
            timestamp=1000.0,
        )

        assert result.matched is True
        assert result.drift_detected is False
        assert result.mismatches == []
        assert result.action_required == "NONE"
        assert result.position_count_internal == 1
        assert result.position_count_broker == 1

    def test_multiple_positions_all_match(self):
        reconciler = PositionReconciler()
        internal = [
            _internal("EURUSD", "LONG", "0.10"),
            _internal("GBPUSD", "SHORT", "0.05"),
            _internal("XAUUSD", "LONG", "1.0"),
        ]
        broker = [
            _broker("EURUSD", "LONG", "0.10"),
            _broker("GBPUSD", "SHORT", "0.05"),
            _broker("XAUUSD", "LONG", "1.0"),
        ]

        result = reconciler.reconcile(internal, broker, timestamp=2000.0)

        assert result.matched is True
        assert result.drift_detected is False
        assert result.position_count_internal == 3
        assert result.position_count_broker == 3

    def test_empty_positions_match(self):
        """No positions on either side → trivially matched."""
        reconciler = PositionReconciler()
        result = reconciler.reconcile([], [], timestamp=0.0)

        assert result.matched is True
        assert result.drift_detected is False


# ---------------------------------------------------------------------------
# Quantity mismatch
# ---------------------------------------------------------------------------


class TestReconcilerQtyMismatch:
    """Different quantities for same symbol → QTY_MISMATCH."""

    def test_qty_mismatch_detected(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[_internal("EURUSD", "LONG", "0.10")],
            broker_positions=[_broker("EURUSD", "LONG", "0.20")],
            timestamp=1000.0,
        )

        assert result.matched is False
        assert result.drift_detected is True
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["type"] == "QTY_MISMATCH"
        assert result.mismatches[0]["symbol"] == "EURUSD"
        assert result.mismatches[0]["internal_qty"] == Decimal("0.10")
        assert result.mismatches[0]["broker_qty"] == Decimal("0.20")

    def test_qty_mismatch_with_side_match(self):
        """Same side, different qty → still QTY_MISMATCH (no SIDE_MISMATCH)."""
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[_internal("GBPUSD", "SHORT", "0.05")],
            broker_positions=[_broker("GBPUSD", "SHORT", "0.15")],
            timestamp=1000.0,
        )

        mismatch_types = [m["type"] for m in result.mismatches]
        assert "QTY_MISMATCH" in mismatch_types
        assert "SIDE_MISMATCH" not in mismatch_types


# ---------------------------------------------------------------------------
# Missing from broker
# ---------------------------------------------------------------------------


class TestReconcilerMissingFromBroker:
    """Position exists internally but not at broker → MISSING_FROM_BROKER."""

    def test_missing_from_broker(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[
                _internal("EURUSD", "LONG", "0.10"),
                _internal("GBPUSD", "SHORT", "0.05"),
            ],
            broker_positions=[
                _broker("EURUSD", "LONG", "0.10"),
            ],
            timestamp=1000.0,
        )

        assert result.matched is False
        assert result.drift_detected is True
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["type"] == "MISSING_FROM_BROKER"
        assert result.mismatches[0]["symbol"] == "GBPUSD"
        assert result.mismatches[0]["broker_qty"] == Decimal("0")

    def test_all_internal_missing_from_broker(self):
        """All internal positions missing at broker."""
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[
                _internal("EURUSD", "LONG", "0.10"),
                _internal("XAUUSD", "LONG", "1.0"),
            ],
            broker_positions=[],
            timestamp=1000.0,
        )

        assert result.drift_detected is True
        assert result.position_count_internal == 2
        assert result.position_count_broker == 0
        missing = [m for m in result.mismatches if m["type"] == "MISSING_FROM_BROKER"]
        assert len(missing) == 2


# ---------------------------------------------------------------------------
# Extra at broker
# ---------------------------------------------------------------------------


class TestReconcilerExtraAtBroker:
    """Position exists at broker but not internally → EXTRA_AT_BROKER."""

    def test_extra_at_broker(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[],
            broker_positions=[
                _broker("EURUSD", "LONG", "0.10"),
            ],
            timestamp=1000.0,
        )

        assert result.matched is False
        assert result.drift_detected is True
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["type"] == "EXTRA_AT_BROKER"
        assert result.mismatches[0]["symbol"] == "EURUSD"
        assert result.mismatches[0]["internal_qty"] == Decimal("0")

    def test_extra_and_missing_combined(self):
        """Some extra at broker, some missing from broker."""
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[
                _internal("EURUSD", "LONG", "0.10"),
            ],
            broker_positions=[
                _broker("GBPUSD", "SHORT", "0.05"),
            ],
            timestamp=1000.0,
        )

        assert result.drift_detected is True
        types = {m["type"] for m in result.mismatches}
        assert "MISSING_FROM_BROKER" in types
        assert "EXTRA_AT_BROKER" in types


# ---------------------------------------------------------------------------
# Drift counter
# ---------------------------------------------------------------------------


class TestReconcilerDriftCount:
    """Multiple drift events must increment the drift counter."""

    def test_drift_count_increments(self):
        reconciler = PositionReconciler()
        assert reconciler.drift_count == 0

        # First drift
        reconciler.reconcile(
            internal_positions=[_internal("EURUSD", "LONG", "0.10")],
            broker_positions=[],
            timestamp=1000.0,
        )
        assert reconciler.drift_count == 1

        # Second drift
        reconciler.reconcile(
            internal_positions=[_internal("GBPUSD", "SHORT", "0.05")],
            broker_positions=[_broker("GBPUSD", "SHORT", "0.15")],
            timestamp=2000.0,
        )
        assert reconciler.drift_count == 2

    def test_no_drift_does_not_increment(self):
        reconciler = PositionReconciler()

        reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker()],
            timestamp=1000.0,
        )
        assert reconciler.drift_count == 0

    def test_drift_count_resets(self):
        reconciler = PositionReconciler()

        reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[],
            timestamp=1000.0,
        )
        assert reconciler.drift_count == 1

        reconciler.reset()
        assert reconciler.drift_count == 0


# ---------------------------------------------------------------------------
# Auto-close + manual review actions
# ---------------------------------------------------------------------------


class TestReconcilerActions:
    """Action required field based on config."""

    def test_auto_close_drift_action(self):
        config = ReconciliationConfig(auto_close_drift=True)
        reconciler = PositionReconciler(config=config)

        result = reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker(qty="0.20")],
            timestamp=1000.0,
        )
        assert result.action_required == "CLOSE_DRIFT"

    def test_manual_review_when_no_auto_close(self):
        config = ReconciliationConfig(auto_close_drift=False)
        reconciler = PositionReconciler(config=config)

        result = reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker(qty="0.20")],
            timestamp=1000.0,
        )
        assert result.action_required == "MANUAL_REVIEW"

    def test_none_action_when_no_drift(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker()],
            timestamp=1000.0,
        )
        assert result.action_required == "NONE"


# ---------------------------------------------------------------------------
# get_drift_positions
# ---------------------------------------------------------------------------


class TestReconcilerGetDriftPositions:
    """get_drift_positions returns positions that need closing."""

    def test_returns_missing_and_extra(self):
        reconciler = PositionReconciler()
        reconciler.reconcile(
            internal_positions=[_internal("EURUSD", "LONG", "0.10")],
            broker_positions=[_broker("GBPUSD", "SHORT", "0.05")],
            timestamp=1000.0,
        )

        drift_pos = reconciler.get_drift_positions()
        types = {p["type"] for p in drift_pos}
        assert types == {"MISSING_FROM_BROKER", "EXTRA_AT_BROKER"}

    def test_empty_when_no_drift(self):
        reconciler = PositionReconciler()
        reconciler.reconcile(
            internal_positions=[_internal()],
            broker_positions=[_broker()],
            timestamp=1000.0,
        )

        assert reconciler.get_drift_positions() == []

    def test_empty_when_no_history(self):
        reconciler = PositionReconciler()
        assert reconciler.get_drift_positions() == []


# ---------------------------------------------------------------------------
# Side mismatch
# ---------------------------------------------------------------------------


class TestReconcilerSideMismatch:
    """Different sides for same symbol → SIDE_MISMATCH."""

    def test_side_mismatch(self):
        reconciler = PositionReconciler()
        result = reconciler.reconcile(
            internal_positions=[_internal("EURUSD", "LONG", "0.10")],
            broker_positions=[_broker("EURUSD", "SHORT", "0.10")],
            timestamp=1000.0,
        )

        assert result.matched is False
        side_mismatches = [m for m in result.mismatches if m["type"] == "SIDE_MISMATCH"]
        assert len(side_mismatches) == 1
        assert side_mismatches[0]["internal_side"] == "LONG"
        assert side_mismatches[0]["broker_side"] == "SHORT"
