"""Multi-venue position reconciliation — compares local ledger vs broker state."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from ..core.enums import ReconciliationStatus
from .broker_adapter import BrokerAdapter, BrokerPosition
from .ledger import Ledger, Position

logger = logging.getLogger(__name__)

EQUITY_TOLERANCE = Decimal("10")       # $10 tolerance for equity comparison
QTY_TOLERANCE = Decimal("0.0001")      # 0.0001 lot tolerance for quantity


class MismatchType(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"          # Position exists locally but not at broker
    BROKER_ONLY = "BROKER_ONLY"        # Position exists at broker but not locally
    QTY_MISMATCH = "QTY_MISMATCH"     # Quantity differs beyond tolerance
    SIDE_MISMATCH = "SIDE_MISMATCH"   # Side differs (LONG vs SHORT)
    PNL_MISMATCH = "PNL_MISMATCH"     # Unrealized P&L differs beyond tolerance


@dataclass
class MismatchDetail:
    """Single position mismatch."""
    symbol: str
    venue: str
    mismatch_type: MismatchType
    local_qty: Optional[Decimal]
    broker_qty: Optional[Decimal]
    local_side: Optional[str]
    broker_side: Optional[str]
    local_pnl: Optional[Decimal]
    broker_pnl: Optional[Decimal]
    severity: str  # "WARNING" | "CRITICAL"
    message: str


@dataclass
class ReconcileResult:
    """Result of a single-venue reconciliation."""
    venue: str
    status: ReconciliationStatus
    timestamp: datetime
    local_count: int
    broker_count: int
    matched: int
    mismatches: list[MismatchDetail]
    errors: list[str]


@dataclass
class ReconcileAllResult:
    """Result of all-venue reconciliation."""
    status: ReconciliationStatus
    venue_results: dict[str, ReconcileResult]
    total_mismatches: int
    timestamp: datetime

    @property
    def is_clean(self) -> bool:
        return self.status == ReconciliationStatus.CLEAN


# Type for async alert callback
AlertCallback = Callable[[MismatchDetail], Coroutine[Any, Any, None]]


class Reconciler:
    """Multi-venue position reconciler.

    Compares local ledger positions against broker-reported positions.
    Fires alert callbacks on mismatch.

    Usage:
        reconciler = Reconciler(ledger, {"pepperstone": pepperstone_adapter})
        result = await reconciler.reconcile_all_venues()
        if not result.is_clean:
            for m in result.venue_results["pepperstone"].mismatches:
                print(m.message)
    """

    def __init__(
        self,
        ledger: Ledger,
        broker_adapters: dict[str, BrokerAdapter],
        equity_tolerance: Decimal = EQUITY_TOLERANCE,
        qty_tolerance: Decimal = QTY_TOLERANCE,
        alert_callback: Optional[AlertCallback] = None,
    ) -> None:
        self._ledger = ledger
        self._adapters = broker_adapters
        self._equity_tol = equity_tolerance
        self._qty_tol = qty_tolerance
        self._alert_cb = alert_callback

    async def reconcile_all_venues(self) -> ReconcileAllResult:
        """Run reconciliation across every configured venue.

        Returns:
            ReconcileAllResult with per-venue detail.
        """
        now = datetime.now(UTC)
        venue_results: dict[str, ReconcileResult] = {}
        total_mismatches = 0
        overall = ReconciliationStatus.CLEAN

        for venue, adapter in self._adapters.items():
            try:
                result = await self._reconcile_venue(venue, adapter)
                venue_results[venue] = result
                total_mismatches += len(result.mismatches)
                if result.status == ReconciliationStatus.MISMATCH:
                    overall = ReconciliationStatus.MISMATCH
                elif result.status == ReconciliationStatus.ERROR and overall == ReconciliationStatus.CLEAN:
                    overall = ReconciliationStatus.ERROR
            except Exception as exc:
                logger.error("Reconcile failed for venue %s: %s", venue, exc)
                venue_results[venue] = ReconcileResult(
                    venue=venue,
                    status=ReconciliationStatus.ERROR,
                    timestamp=now,
                    local_count=0,
                    broker_count=0,
                    matched=0,
                    mismatches=[],
                    errors=[str(exc)],
                )
                overall = ReconciliationStatus.ERROR

        return ReconcileAllResult(
            status=overall,
            venue_results=venue_results,
            total_mismatches=total_mismatches,
            timestamp=now,
        )

    async def reconcile_venue(self, venue: str) -> ReconcileResult:
        """Reconcile a single venue by name."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise ValueError(f"No adapter registered for venue '{venue}'")
        return await self._reconcile_venue(venue, adapter)

    async def _reconcile_venue(
        self, venue: str, adapter: BrokerAdapter
    ) -> ReconcileResult:
        """Core reconciliation logic for one venue."""
        now = datetime.now(UTC)
        mismatches: list[MismatchDetail] = []
        errors: list[str] = []
        matched = 0

        # Gather local & broker positions
        local_positions = self._ledger.get_by_venue(venue)
        try:
            broker_positions = await adapter.get_positions()
        except Exception as exc:
            errors.append(f"Broker fetch failed: {exc}")
            return ReconcileResult(
                venue=venue,
                status=ReconciliationStatus.ERROR,
                timestamp=now,
                local_count=len(local_positions),
                broker_count=0,
                matched=0,
                mismatches=[],
                errors=errors,
            )

        # Index by symbol for comparison
        local_map: dict[str, Position] = {p.symbol: p for p in local_positions}
        broker_map: dict[str, BrokerPosition] = {p.symbol: p for p in broker_positions}
        all_symbols = set(local_map) | set(broker_map)

        for symbol in sorted(all_symbols):
            local = local_map.get(symbol)
            broker = broker_map.get(symbol)

            if local and not broker:
                m = MismatchDetail(
                    symbol=symbol,
                    venue=venue,
                    mismatch_type=MismatchType.LOCAL_ONLY,
                    local_qty=local.quantity,
                    broker_qty=None,
                    local_side=local.side,
                    broker_side=None,
                    local_pnl=local.unrealized_pnl,
                    broker_pnl=None,
                    severity="CRITICAL",
                    message=f"[{venue}] {symbol}: position exists locally but not at broker",
                )
                mismatches.append(m)
                await self._fire_alert(m)

            elif broker and not local:
                m = MismatchDetail(
                    symbol=symbol,
                    venue=venue,
                    mismatch_type=MismatchType.BROKER_ONLY,
                    local_qty=None,
                    broker_qty=broker.quantity,
                    local_side=None,
                    broker_side=broker.position_type.value,
                    local_pnl=None,
                    broker_pnl=broker.unrealized_pnl,
                    severity="CRITICAL",
                    message=f"[{venue}] {symbol}: position exists at broker but not locally",
                )
                mismatches.append(m)
                await self._fire_alert(m)

            else:
                # Both exist — compare
                assert local is not None and broker is not None

                # Side check
                broker_side = broker.position_type.value
                if local.side != broker_side:
                    m = MismatchDetail(
                        symbol=symbol,
                        venue=venue,
                        mismatch_type=MismatchType.SIDE_MISMATCH,
                        local_qty=local.quantity,
                        broker_qty=broker.quantity,
                        local_side=local.side,
                        broker_side=broker_side,
                        local_pnl=local.unrealized_pnl,
                        broker_pnl=broker.unrealized_pnl,
                        severity="CRITICAL",
                        message=(
                            f"[{venue}] {symbol}: side mismatch "
                            f"(local={local.side}, broker={broker_side})"
                        ),
                    )
                    mismatches.append(m)
                    await self._fire_alert(m)
                    continue  # no point comparing qty/pnl if side differs

                # Quantity check
                qty_diff = abs(local.quantity - broker.quantity)
                if qty_diff > self._qty_tol:
                    m = MismatchDetail(
                        symbol=symbol,
                        venue=venue,
                        mismatch_type=MismatchType.QTY_MISMATCH,
                        local_qty=local.quantity,
                        broker_qty=broker.quantity,
                        local_side=local.side,
                        broker_side=broker_side,
                        local_pnl=local.unrealized_pnl,
                        broker_pnl=broker.unrealized_pnl,
                        severity="WARNING",
                        message=(
                            f"[{venue}] {symbol}: qty mismatch "
                            f"(local={local.quantity}, broker={broker.quantity}, "
                            f"diff={qty_diff})"
                        ),
                    )
                    mismatches.append(m)
                    await self._fire_alert(m)

                # P&L check
                pnl_diff = abs(local.unrealized_pnl - broker.unrealized_pnl)
                if pnl_diff > self._equity_tol:
                    m = MismatchDetail(
                        symbol=symbol,
                        venue=venue,
                        mismatch_type=MismatchType.PNL_MISMATCH,
                        local_qty=local.quantity,
                        broker_qty=broker.quantity,
                        local_side=local.side,
                        broker_side=broker_side,
                        local_pnl=local.unrealized_pnl,
                        broker_pnl=broker.unrealized_pnl,
                        severity="WARNING",
                        message=(
                            f"[{venue}] {symbol}: P&L mismatch "
                            f"(local={local.unrealized_pnl}, broker={broker.unrealized_pnl}, "
                            f"diff={pnl_diff})"
                        ),
                    )
                    mismatches.append(m)
                    await self._fire_alert(m)

                if not mismatches or mismatches[-1].symbol != symbol:
                    matched += 1

        status = (
            ReconciliationStatus.CLEAN if not mismatches and not errors
            else ReconciliationStatus.MISMATCH if mismatches
            else ReconciliationStatus.ERROR
        )

        return ReconcileResult(
            venue=venue,
            status=status,
            timestamp=now,
            local_count=len(local_positions),
            broker_count=len(broker_positions),
            matched=matched,
            mismatches=mismatches,
            errors=errors,
        )

    async def _fire_alert(self, mismatch: MismatchDetail) -> None:
        """Invoke alert callback if configured."""
        if self._alert_cb is None:
            return
        try:
            await self._alert_cb(mismatch)
        except Exception as exc:
            logger.warning("Alert callback failed for %s: %s", mismatch.symbol, exc)
