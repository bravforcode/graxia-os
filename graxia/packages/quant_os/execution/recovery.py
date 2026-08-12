"""Crash recovery — startup state reconciliation, orphan resolution, limit checks."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from ..core.enums import OrderStatus
from .broker_adapter import BrokerAdapter, BrokerOrderResponse
from .ledger import Ledger
from .reconcile import ReconcileAllResult, Reconciler

logger = logging.getLogger(__name__)

MAX_DRAWDOWN_PCT = Decimal("15")  # 15% max drawdown
MAX_DAILY_LOSS_PCT = Decimal("2")  # 2% max daily loss


class StartupVerdict(str, Enum):
    RESUME = "RESUME"  # All checks pass — safe to trade
    HALT = "HALT"  # Critical failure — do not trade
    DEGRADED = "DEGRADED"  # Minor issues — trade with caution


class Severity(str, Enum):
    """Startup check severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class OrphanResolution(str, Enum):
    """Resolution status for orphaned orders."""

    CONFIRMED_FILLED = "CONFIRMED_FILLED"
    CONFIRMED_CANCELLED = "CONFIRMED_CANCELLED"
    MARKED_ERROR = "MARKED_ERROR"
    STILL_OPEN = "STILL_OPEN"


@dataclass
class OrphanedOrder:
    """An order that exists locally but its broker status is unknown or inconsistent."""

    order_id: str
    symbol: str
    broker_order_id: str
    local_status: str
    broker_status: str | None
    resolution: OrphanResolution


@dataclass
class StartupCheck:
    """Result of a single startup check."""

    name: str
    passed: bool
    detail: str
    severity: Severity


@dataclass
class RecoveryResult:
    """Full result of startup recovery procedure."""

    verdict: StartupVerdict
    reconcile_result: ReconcileAllResult | None
    orphaned_orders: list[OrphanedOrder]
    checks: list[StartupCheck]
    timestamp: datetime

    @property
    def is_safe(self) -> bool:
        return self.verdict == StartupVerdict.RESUME

    @property
    def critical_failures(self) -> list[StartupCheck]:
        return [c for c in self.checks if c.severity == Severity.CRITICAL and not c.passed]


# Type for async order status fetcher
OrderStatusFetcher = Callable[[str], Coroutine[Any, Any, BrokerOrderResponse | None]]


class Recovery:
    """Crash recovery handler for startup.

    Performs:
    1. Load local state from ledger
    2. Reconcile against broker(s)
    3. Resolve orphaned orders
    4. Check risk limits (drawdown, daily loss)
    5. Emit verdict: RESUME / HALT / DEGRADED

    Usage:
        recovery = Recovery(ledger, reconciler, {"pepperstone": adapter})
        result = await recovery.on_startup()
        if result.is_safe:
            print("Safe to trade")
        else:
            print(f"Halted: {[c.detail for c in result.critical_failures]}")
    """

    def __init__(
        self,
        ledger: Ledger,
        reconciler: Reconciler,
        broker_adapters: dict[str, BrokerAdapter],
        max_drawdown_pct: Decimal = MAX_DRAWDOWN_PCT,
        max_daily_loss_pct: Decimal = MAX_DAILY_LOSS_PCT,
        on_halt: Callable[[RecoveryResult], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._ledger = ledger
        self._reconciler = reconciler
        self._adapters = broker_adapters
        self._max_dd = max_drawdown_pct
        self._max_daily = max_daily_loss_pct
        self._on_halt = on_halt

    async def on_startup(self, initial_equity: Decimal | None = None) -> RecoveryResult:
        """Full startup recovery procedure.

        Args:
            initial_equity: Override equity baseline. If None, uses ledger peak.

        Returns:
            RecoveryResult with verdict and all check details.
        """
        now = datetime.now(UTC)
        checks: list[StartupCheck] = []
        orphans: list[OrphanedOrder] = []
        recon_result: ReconcileAllResult | None = None

        # Step 1: Reconcile
        try:
            recon_result = await self._reconciler.reconcile_all_venues()
            checks.append(
                StartupCheck(
                    name="reconcile",
                    passed=recon_result.is_clean,
                    detail=(
                        f"Reconciled {sum(r.broker_count for r in recon_result.venue_results.values())} "
                        f"broker positions across {len(recon_result.venue_results)} venues, "
                        f"{recon_result.total_mismatches} mismatches"
                    ),
                    severity=Severity.CRITICAL if not recon_result.is_clean else Severity.INFO,
                )
            )
        except Exception as exc:
            logger.error("Reconciliation failed: %s", exc)
            checks.append(
                StartupCheck(
                    name="reconcile",
                    passed=False,
                    detail=f"Reconciliation exception: {exc}",
                    severity=Severity.CRITICAL,
                )
            )

        # Step 2: Resolve orphaned orders
        for venue, adapter in self._adapters.items():
            venue_orphans = await self._resolve_orphaned_orders(venue, adapter)
            orphans.extend(venue_orphans)

        unresolved = [o for o in orphans if o.resolution == OrphanResolution.MARKED_ERROR]
        checks.append(
            StartupCheck(
                name="orphaned_orders",
                passed=len(unresolved) == 0,
                detail=(f"Found {len(orphans)} orphaned orders, " f"{len(unresolved)} unresolved"),
                severity=Severity.WARNING if unresolved else Severity.INFO,
            )
        )

        # Step 3: Check drawdown
        pf = self._ledger.calculate_portfolio(initial_equity=initial_equity)
        dd = pf.current_drawdown_pct
        dd_ok = dd < self._max_dd
        checks.append(
            StartupCheck(
                name="drawdown",
                passed=dd_ok,
                detail=f"Current drawdown: {dd}% (limit: {self._max_dd}%)",
                severity=Severity.CRITICAL if not dd_ok else Severity.INFO,
            )
        )

        # Step 4: Check daily loss
        eq = pf.total_equity
        if eq > 0:
            daily_loss_pct = abs(pf.daily_pnl / eq * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            daily_loss_pct = Decimal("0")
        daily_ok = daily_loss_pct < self._max_daily
        checks.append(
            StartupCheck(
                name="daily_loss",
                passed=daily_ok,
                detail=f"Daily loss: {daily_loss_pct}% (limit: {self._max_daily}%)",
                severity=Severity.CRITICAL if not daily_ok else Severity.INFO,
            )
        )

        # Step 5: No unknown orders (broker-only positions not accounted locally)
        broker_only = []
        if recon_result:
            for venue_res in recon_result.venue_results.values():
                for m in venue_res.mismatches:
                    if m.mismatch_type.value == "BROKER_ONLY":
                        broker_only.append(m)
        checks.append(
            StartupCheck(
                name="unknown_orders",
                passed=len(broker_only) == 0,
                detail=f"{len(broker_only)} unknown broker-side positions found",
                severity=Severity.WARNING if broker_only else Severity.INFO,
            )
        )

        # Determine verdict
        critical_fails = [c for c in checks if c.severity == Severity.CRITICAL and not c.passed]
        warnings = [c for c in checks if c.severity == Severity.WARNING and not c.passed]

        if critical_fails:
            verdict = StartupVerdict.HALT
        elif warnings:
            verdict = StartupVerdict.DEGRADED
        else:
            verdict = StartupVerdict.RESUME

        result = RecoveryResult(
            verdict=verdict,
            reconcile_result=recon_result,
            orphaned_orders=orphans,
            checks=checks,
            timestamp=now,
        )

        # Fire halt callback if halted
        if verdict == StartupVerdict.HALT and self._on_halt:
            try:
                await self._on_halt(result)
            except Exception as exc:
                logger.error("Halt callback failed: %s", exc)

        logger.info(
            "Recovery complete: verdict=%s checks=%d orphans=%d",
            verdict.value,
            len(checks),
            len(orphans),
        )
        return result

    async def _resolve_orphaned_orders(self, venue: str, adapter: BrokerAdapter) -> list[OrphanedOrder]:
        """Find and resolve orders that exist locally but have uncertain broker state.

        Checks positions that are open locally against broker positions.
        For any local-only positions, queries broker to determine if the order
        was filled, cancelled, or is still pending.
        """
        orphans: list[OrphanedOrder] = []
        local_positions = self._ledger.get_by_venue(venue)

        for pos in local_positions:
            broker_pos = None
            try:
                broker_pos = await adapter.get_position(pos.symbol)
            except Exception as exc:
                logger.warning(
                    "Failed to query broker for %s on %s: %s",
                    pos.symbol,
                    venue,
                    exc,
                )

            if broker_pos is None:
                # Position exists locally but not at broker — could be orphan
                orphan = OrphanedOrder(
                    order_id=pos.position_id,
                    symbol=pos.symbol,
                    broker_order_id=pos.broker_position_id,
                    local_status="OPEN",
                    broker_status=None,
                    resolution=OrphanResolution.MARKED_ERROR,
                )

                # If we have a broker order ID, try to check its status
                if pos.broker_position_id:
                    try:
                        order_resp = await adapter.get_order_status(pos.broker_position_id)
                        if order_resp:
                            if order_resp.status == OrderStatus.FILLED:
                                orphan.broker_status = "FILLED"
                                orphan.resolution = OrphanResolution.CONFIRMED_FILLED
                            elif order_resp.status in (
                                OrderStatus.CANCELLED,
                                OrderStatus.EXPIRED,
                                OrderStatus.REJECTED,
                            ):
                                orphan.broker_status = order_resp.status.value
                                orphan.resolution = OrphanResolution.CONFIRMED_CANCELLED
                                # Close the local position
                                self._ledger.close_position(pos.position_id)
                            else:
                                orphan.broker_status = order_resp.status.value
                                orphan.resolution = OrphanResolution.STILL_OPEN
                    except Exception as exc:
                        logger.warning(
                            "Order status check failed for %s: %s",
                            pos.broker_position_id,
                            exc,
                        )

                orphans.append(orphan)

        return orphans
