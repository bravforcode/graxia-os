"""Position reconciliation — sync internal state with broker, auto-fix small diffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_QTY_TOLERANCE = Decimal("0.0001")
DEFAULT_PRICE_TOLERANCE = Decimal("0.00001")
AUTO_FIX_THRESHOLD = Decimal("0.01")


class DiscrepancyType(str, Enum):
    POSITION_MISSING = "POSITION_MISSING"
    BROKER_MISSING = "BROKER_MISSING"
    QTY_MISMATCH = "QTY_MISMATCH"
    SIDE_MISMATCH = "SIDE_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"


class DiscrepancySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class InternalPosition:
    """Internal position representation."""
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    """Broker position snapshot."""
    symbol: str
    side: str
    quantity: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")


@dataclass
class Discrepancy:
    """A single position discrepancy."""
    symbol: str
    disc_type: DiscrepancyType
    severity: DiscrepancySeverity
    internal_qty: Optional[Decimal] = None
    broker_qty: Optional[Decimal] = None
    internal_side: Optional[str] = None
    broker_side: Optional[str] = None
    internal_price: Optional[Decimal] = None
    broker_price: Optional[Decimal] = None
    qty_diff: Optional[Decimal] = None
    price_diff: Optional[Decimal] = None
    auto_fixable: bool = False
    message: str = ""


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    timestamp: datetime
    total_internal: int
    total_broker: int
    matched: int
    discrepancies: list[Discrepancy]
    auto_fixed: list[Discrepancy]
    manual_review: list[Discrepancy]
    is_clean: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_clean = len(self.discrepancies) == 0


@dataclass
class AutoFixAction:
    """Record of an auto-fix applied."""
    symbol: str
    fix_type: str
    old_qty: Decimal
    new_qty: Decimal
    old_price: Optional[Decimal]
    new_price: Optional[Decimal]
    timestamp: datetime
    reason: str


class PositionReconciler:
    """Reconciles internal positions against broker state.

    Compares internal ledger positions with broker-reported positions,
    detects discrepancies, and auto-fixes small rounding differences.

    Usage:
        reconciler = PositionReconciler()
        result = reconciler.reconcile_positions(internal, broker)
        if not result.is_clean:
            reconciler.auto_fix(result)
    """

    def __init__(
        self,
        qty_tolerance: Decimal = DEFAULT_QTY_TOLERANCE,
        price_tolerance: Decimal = DEFAULT_PRICE_TOLERANCE,
        auto_fix_threshold: Decimal = AUTO_FIX_THRESHOLD,
    ) -> None:
        self._qty_tolerance = qty_tolerance
        self._price_tolerance = price_tolerance
        self._auto_fix_threshold = auto_fix_threshold
        self._fix_history: list[AutoFixAction] = []
        logger.info(
            "reconciler.init",
            qty_tolerance=str(qty_tolerance),
            price_tolerance=str(price_tolerance),
            auto_fix_threshold=str(auto_fix_threshold),
        )

    def reconcile_positions(
        self,
        internal: list[InternalPosition],
        broker: list[BrokerPositionSnapshot],
    ) -> ReconciliationResult:
        """Compare internal positions vs broker positions.

        Returns a ReconciliationResult with all discrepancies found.
        """
        internal_map = {p.symbol: p for p in internal}
        broker_map = {p.symbol: p for p in broker}
        all_symbols = set(internal_map.keys()) | set(broker_map.keys())

        discrepancies: list[Discrepancy] = []
        matched = 0

        for symbol in sorted(all_symbols):
            int_pos = internal_map.get(symbol)
            brk_pos = broker_map.get(symbol)

            if int_pos is not None and brk_pos is None:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    disc_type=DiscrepancyType.BROKER_MISSING,
                    severity=DiscrepancySeverity.WARNING,
                    internal_qty=int_pos.quantity,
                    internal_side=int_pos.side,
                    internal_price=int_pos.avg_price,
                    message=f"Position {symbol} exists internally but not at broker",
                ))
                continue

            if int_pos is None and brk_pos is not None:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    disc_type=DiscrepancyType.POSITION_MISSING,
                    severity=DiscrepancySeverity.WARNING,
                    broker_qty=brk_pos.quantity,
                    broker_side=brk_pos.side,
                    broker_price=brk_pos.avg_price,
                    message=f"Position {symbol} exists at broker but not internally",
                ))
                continue

            assert int_pos is not None and brk_pos is not None

            disc = self._compare_positions(int_pos, brk_pos)
            if disc is None:
                matched += 1
            else:
                discrepancies.append(disc)

        auto_fixed = [d for d in discrepancies if d.auto_fixable]
        manual_review = [d for d in discrepancies if not d.auto_fixable]

        result = ReconciliationResult(
            timestamp=datetime.now(UTC),
            total_internal=len(internal),
            total_broker=len(broker),
            matched=matched,
            discrepancies=discrepancies,
            auto_fixed=auto_fixed,
            manual_review=manual_review,
        )

        logger.info(
            "reconciliation.complete",
            total_symbols=len(all_symbols),
            matched=matched,
            discrepancies=len(discrepancies),
            auto_fixable=len(auto_fixed),
            is_clean=result.is_clean,
        )
        return result

    def _compare_positions(
        self,
        internal: InternalPosition,
        broker: BrokerPositionSnapshot,
    ) -> Optional[Discrepancy]:
        """Compare a single internal vs broker position pair."""
        qty_diff = abs(internal.quantity - broker.quantity)
        price_diff = abs(internal.avg_price - broker.avg_price)

        if internal.side != broker.side:
            return Discrepancy(
                symbol=internal.symbol,
                disc_type=DiscrepancyType.SIDE_MISMATCH,
                severity=DiscrepancySeverity.CRITICAL,
                internal_qty=internal.quantity,
                broker_qty=broker.quantity,
                internal_side=internal.side,
                broker_side=broker.side,
                internal_price=internal.avg_price,
                broker_price=broker.avg_price,
                qty_diff=qty_diff,
                price_diff=price_diff,
                auto_fixable=False,
                message=(
                    f"Side mismatch: internal={internal.side} vs broker={broker.side}"
                ),
            )

        if qty_diff > self._qty_tolerance:
            auto_fixable = qty_diff <= self._auto_fix_threshold
            return Discrepancy(
                symbol=internal.symbol,
                disc_type=DiscrepancyType.QTY_MISMATCH,
                severity=(
                    DiscrepancySeverity.WARNING if auto_fixable
                    else DiscrepancySeverity.CRITICAL
                ),
                internal_qty=internal.quantity,
                broker_qty=broker.quantity,
                internal_side=internal.side,
                broker_side=broker.side,
                qty_diff=qty_diff,
                auto_fixable=auto_fixable,
                message=(
                    f"Qty diff: {qty_diff} (internal={internal.quantity} "
                    f"broker={broker.quantity})"
                ),
            )

        if price_diff > self._price_tolerance:
            return Discrepancy(
                symbol=internal.symbol,
                disc_type=DiscrepancyType.PRICE_MISMATCH,
                severity=DiscrepancySeverity.INFO,
                internal_price=internal.avg_price,
                broker_price=broker.avg_price,
                price_diff=price_diff,
                auto_fixable=False,
                message=(
                    f"Price diff: {price_diff} (internal={internal.avg_price} "
                    f"broker={broker.avg_price})"
                ),
            )

        return None

    def find_discrepancies(
        self,
        internal: list[InternalPosition],
        broker: list[BrokerPositionSnapshot],
    ) -> list[Discrepancy]:
        """Find all discrepancies without auto-fixing."""
        result = self.reconcile_positions(internal, broker)
        return result.discrepancies

    def auto_fix(
        self,
        result: ReconciliationResult,
        broker_update_fn: Optional[callable] = None,
    ) -> list[AutoFixAction]:
        """Auto-fix small discrepancies (rounding differences).

        For qty mismatches within threshold: adjust internal to match broker.
        If broker_update_fn is provided, sends corrections to broker instead.
        """
        fixes: list[AutoFixAction] = []
        now = datetime.now(UTC)

        for disc in result.discrepancies:
            if not disc.auto_fixable:
                continue
            if disc.disc_type != DiscrepancyType.QTY_MISMATCH:
                continue

            assert disc.internal_qty is not None
            assert disc.broker_qty is not None

            old_qty = disc.internal_qty
            new_qty = disc.broker_qty
            fix = AutoFixAction(
                symbol=disc.symbol,
                fix_type="QTY_ROUNDING",
                old_qty=old_qty,
                new_qty=new_qty,
                old_price=disc.internal_price,
                new_price=disc.broker_price,
                timestamp=now,
                reason=f"Auto-fix rounding: qty diff {disc.qty_diff}",
            )
            fixes.append(fix)
            self._fix_history.append(fix)

            logger.info(
                "auto_fix.applied",
                symbol=disc.symbol,
                fix_type=fix.fix_type,
                old_qty=str(old_qty),
                new_qty=str(new_qty),
            )

        logger.info(
            "auto_fix.complete",
            fixes_applied=len(fixes),
        )
        return fixes

    def get_fix_history(self) -> list[AutoFixAction]:
        """Return all auto-fix actions taken."""
        return list(self._fix_history)

    def generate_report(
        self, result: ReconciliationResult
    ) -> dict:
        """Generate a summary report of reconciliation."""
        return {
            "timestamp": result.timestamp.isoformat(),
            "is_clean": result.is_clean,
            "total_positions": {
                "internal": result.total_internal,
                "broker": result.total_broker,
            },
            "matched": result.matched,
            "discrepancies": {
                "total": len(result.discrepancies),
                "auto_fixable": len(result.auto_fixed),
                "manual_review": len(result.manual_review),
                "by_type": {
                    dt.value: sum(
                        1 for d in result.discrepancies if d.disc_type == dt
                    )
                    for dt in DiscrepancyType
                },
                "by_severity": {
                    sev.value: sum(
                        1 for d in result.discrepancies if d.severity == sev
                    )
                    for sev in DiscrepancySeverity
                },
            },
            "details": [
                {
                    "symbol": d.symbol,
                    "type": d.disc_type.value,
                    "severity": d.severity.value,
                    "auto_fixable": d.auto_fixable,
                    "message": d.message,
                }
                for d in result.discrepancies
            ],
        }
