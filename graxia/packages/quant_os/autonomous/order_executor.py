"""Order Executor — bridges TradeDecision to broker submission with safety gates.

Takes a ``TradeDecision`` from the DecisionEngine, runs all risk checks,
and submits orders to the broker.  Respects Golden Rules at every step.

Safety flow:
  1. Kill switch check → reject immediately if active
  2. Decision validation (confidence, direction, symbol)
  3. MAX_OPEN_POSITIONS gate
  4. MAX_DAILY_TRADES gate
  5. MAX_DAILY_LOSS_PCT gate
  6. RiskEngine pre-trade evaluation
  7. Position sizing via RiskEngine Layer 4
  8. Broker submission (paper = direct, live = human approval only)

Golden Rule #2: AI CANNOT SUBMIT LIVE ORDERS.
In live mode the executor logs the suggestion and returns
``ExecutionResult(success=False, error="LIVE_APPROVAL_REQUIRED")``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from ..core.enums import OrderSide
from ..execution.adapters.base import AccountInfo, Order, OrderResult
from ..execution.adapters.manager import BrokerManager
from ..risk.engine import AccountState, PortfolioState, RiskEngine, RiskVerdict, Signal
from ..risk.kill_switch import KillSwitch
from . import config as auto_config
from .decision_engine import TradeDecision
from .live_approval import LiveApprovalGate
from .symbol_registry import SymbolRegistry

logger = structlog.get_logger(__name__)


# ── Result type ─────────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Outcome of an order execution attempt."""

    success: bool
    order_id: str = ""
    broker_order_id: str | None = None
    error: str = ""
    slippage: float = 0.0
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    risk_verdict: RiskVerdict | None = None
    approval_required: bool = False


# ── Order Executor ──────────────────────────────────────────────────────────


class OrderExecutor:
    """Executes TradeDecisions through the broker with full safety gates.

    Paper mode: submits directly via the active broker adapter.
    Live mode:  logs the suggestion and requires human approval (Golden Rule #2).
    """

    def __init__(
        self,
        broker_manager: BrokerManager,
        risk_engine: RiskEngine,
        kill_switch: KillSwitch,
        mode: str = auto_config.TRADING_MODE,
        approval_gate: LiveApprovalGate | None = None,
        symbol_registry: SymbolRegistry | None = None,
    ) -> None:
        self._broker_manager = broker_manager
        self._risk_engine = risk_engine
        self._kill_switch = kill_switch
        self._mode = mode
        self._approval_gate = approval_gate
        self._symbol_registry = symbol_registry or SymbolRegistry()

        # Daily stats tracking (reset at midnight UTC)
        self._daily_trades: int = 0
        self._daily_realized_pnl: Decimal = Decimal("0")
        self._open_positions: int = 0
        self._last_reset_date: datetime = datetime.now(UTC)

        # Audit trail
        self._execution_log: list[dict[str, Any]] = []

    # ── Public API ──────────────────────────────────────────────────────

    async def execute(self, decision: TradeDecision) -> ExecutionResult:
        """Main execution entry point.  Runs the full safety flow.

        Returns ``ExecutionResult`` with success/failure details.
        """
        self._maybe_reset_daily_stats()

        logger.info(
            "order_executor.execute",
            symbol=decision.symbol,
            direction=decision.direction.value,
            confidence=decision.confidence,
            mode=self._mode,
        )

        # Step 1: Kill switch (is_triggered covers both ACTIVE and PAUSED)
        if self._kill_switch.is_triggered:
            return self._reject("Kill switch active — all trading halted")

        # Step 2: Validate decision
        valid, reason = self._validate_decision(decision)
        if not valid:
            return self._reject(reason)

        # Step 3: MAX_OPEN_POSITIONS
        if self._open_positions >= auto_config.MAX_OPEN_POSITIONS:
            return self._reject(f"Max open positions reached ({self._open_positions}/{auto_config.MAX_OPEN_POSITIONS})")

        # Step 4: MAX_DAILY_TRADES
        if self._daily_trades >= auto_config.MAX_DAILY_TRADES:
            return self._reject(f"Max daily trades reached ({self._daily_trades}/{auto_config.MAX_DAILY_TRADES})")

        # Step 5: MAX_DAILY_LOSS_PCT
        if self._check_daily_loss_breached():
            return self._reject(
                f"Daily loss limit breached ({float(self._daily_realized_pnl):.2f} / {auto_config.MAX_DAILY_LOSS_PCT}%)"
            )

        # Step 6: Risk engine pre-trade check
        risk_ok, risk_reason = self._check_risk(decision)
        if not risk_ok:
            return self._reject(risk_reason)

        # Step 6b: Correlation check — prevent over-exposure to correlated symbols
        corr_ok, corr_reason = self._check_correlation(decision)
        if not corr_ok:
            return self._reject(corr_reason)

        # Step 7: Position sizing
        size = self._calculate_position_size(decision)
        if size <= 0:
            return self._reject("Position size calculated to zero")

        # Step 8: Mode-based submission
        if self._mode == "paper":
            return self._submit_order(decision, size)
        else:
            # Golden Rule #2: AI cannot submit live orders
            return await self._require_approval(decision, size)

    def get_daily_stats(self) -> dict[str, Any]:
        """Return current daily trading statistics."""
        self._maybe_reset_daily_stats()
        return {
            "trades_today": self._daily_trades,
            "max_daily_trades": auto_config.MAX_DAILY_TRADES,
            "realized_pnl": float(self._daily_realized_pnl),
            "max_daily_loss_pct": auto_config.MAX_DAILY_LOSS_PCT,
            "open_positions": self._open_positions,
            "max_open_positions": auto_config.MAX_OPEN_POSITIONS,
            "mode": self._mode,
            "date_utc": self._last_reset_date.date().isoformat(),
        }

    def get_execution_log(self) -> list[dict[str, Any]]:
        """Return the full audit trail of execution attempts."""
        return list(self._execution_log)

    # ── Private helpers ─────────────────────────────────────────────────

    def _validate_decision(self, decision: TradeDecision) -> tuple[bool, str]:
        """Pre-checks on the TradeDecision fields."""
        if not decision.symbol:
            return False, "Missing symbol"

        action = decision.direction.value.upper()
        if action not in ("BUY", "SELL", "NO_TRADE"):
            return False, f"Invalid direction: {action}"

        if action == "NO_TRADE":
            return False, "Non-trade direction: NO_TRADE"

        if not (0.0 <= decision.confidence <= 1.0):
            return False, f"Confidence out of range: {decision.confidence}"

        if decision.confidence < auto_config.LLM_MIN_CONFIDENCE:
            return False, (f"Confidence {decision.confidence:.2f} below minimum {auto_config.LLM_MIN_CONFIDENCE}")

        return True, ""

    def _check_risk(self, decision: TradeDecision) -> tuple[bool, str]:
        """Run the 4-layer RiskEngine evaluation."""
        signal = Signal(
            symbol=decision.symbol,
            conviction=decision.confidence,
            entry_price=decision.entry,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            direction=decision.direction.value.upper(),
            side=decision.direction.value.upper(),
            timestamp=datetime.now(UTC),
            timestamp_epoch=datetime.now(UTC).timestamp(),
            asset_class=self._symbol_registry.get_asset_class(decision.symbol),
            venue=self._mode,
            strategy_id="autonomous",
        )

        account, portfolio = self._fetch_account_state()

        verdict: RiskVerdict = self._risk_engine.evaluate(signal, account, portfolio)

        if not verdict.approved:
            logger.warning(
                "order_executor.risk_rejected",
                symbol=decision.symbol,
                reason=verdict.reason,
                reason_code=verdict.reason_code,
                layer=verdict.layer_failed,
            )
            return False, f"Risk rejected (layer {verdict.layer_failed}): {verdict.reason}"

        return True, ""

    def _check_correlation(self, decision: TradeDecision) -> tuple[bool, str]:
        """Check if new position creates excessive correlation.

        Rejects if 2+ positions already exist in the same asset class.
        """
        MAX_PER_CLASS = 2
        asset_class = self._symbol_registry.get_asset_class(decision.symbol)

        try:
            broker = self._broker_manager.active
            positions = broker.get_positions()
        except Exception:
            return True, ""

        class_count = 0
        for pos in positions:
            sym = pos.get("symbol", "")
            if self._symbol_registry.get_asset_class(sym) == asset_class:
                class_count += 1

        if class_count >= MAX_PER_CLASS:
            return False, (f"Correlation limit: {class_count} positions in " f"{asset_class} (max {MAX_PER_CLASS})")

        return True, ""

    def _fetch_account_state(self) -> tuple[AccountState, PortfolioState]:
        """Fetch real account and portfolio state from the broker adapter.

        Falls back to sensible defaults if the broker is unavailable.
        """
        try:
            broker = self._broker_manager.active
            info: AccountInfo = broker.get_account_info()
            positions = broker.get_positions()

            margin_level = 999.0
            if info.margin_used > 0:
                margin_level = (info.equity / info.margin_used) * 100.0

            account = AccountState(
                equity=info.equity,
                balance=info.cash,
                free_margin=info.margin_available,
                margin_level_pct=margin_level,
                open_positions=len(positions),
            )
            portfolio = self._portfolio_from_positions(positions, info.equity)
            return account, portfolio

        except Exception as exc:
            logger.warning("order_executor.fetch_account_fallback", error=str(exc))
            return AccountState(), PortfolioState()

    def _portfolio_from_positions(self, positions: list[dict], equity: float) -> PortfolioState:
        """Build a PortfolioState from broker position data."""
        if not positions:
            return PortfolioState()

        total_notional = 0.0
        class_exposure: dict[str, float] = {}
        symbols: list[str] = []

        for pos in positions:
            sym = pos.get("symbol", "")
            vol = pos.get("volume", 0.0)
            price = pos.get("price_open", 0.0)
            notional = vol * price
            total_notional += notional
            symbols.append(sym)

            asset_class = self._symbol_registry.get_asset_class(sym)
            class_exposure[asset_class] = class_exposure.get(asset_class, 0.0) + notional

        total_exposure_pct = total_notional / equity if equity > 0 else 0.0
        class_pct = {cls: (notional / equity if equity > 0 else 0.0) for cls, notional in class_exposure.items()}

        return PortfolioState(
            total_exposure_pct=total_exposure_pct,
            class_exposure_pct=class_pct,
            position_symbols=symbols,
        )

    def _calculate_position_size(self, decision: TradeDecision) -> float:
        """Derive position size from confidence and real account equity.

        Risk is expressed as a % of equity per trade, then converted to lots
        using SL distance and contract size for the asset class.
        """
        try:
            broker = self._broker_manager.active
            info = broker.get_account_info()
            equity = info.equity
        except Exception:
            equity = 10000.0  # fallback

        risk_pct = max(0.01, min(decision.confidence * 0.5, 1.0)) / 100.0
        risk_amount = equity * risk_pct

        sl_distance = abs(decision.entry - decision.stop_loss) if decision.stop_loss else 0
        if sl_distance <= 0:
            return 0.0

        asset_class = self._symbol_registry.get_asset_class(decision.symbol)
        if asset_class == "forex":
            size = risk_amount / (sl_distance * 100000)
        elif asset_class == "metals":
            size = risk_amount / (sl_distance * 100)
        elif asset_class == "crypto":
            size = risk_amount / sl_distance
        else:
            size = risk_amount / sl_distance

        return round(max(0.01, min(size, 1.0)), 4)

    def _submit_order(self, decision: TradeDecision, size: float) -> ExecutionResult:
        """Submit order to broker in paper mode."""
        order_id = f"auto-{uuid.uuid4().hex[:12]}"

        side = OrderSide.BUY if decision.direction.value.upper() == "BUY" else OrderSide.SELL
        order = Order(
            order_id=order_id,
            signal_id=order_id,
            symbol=decision.symbol,
            asset_class=self._symbol_registry.get_asset_class(decision.symbol),
            side=side.value,
            quantity=size,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
        )

        logger.info(
            "order_executor.submitting",
            order_id=order_id,
            symbol=decision.symbol,
            side=side.value,
            quantity=size,
        )

        try:
            broker = self._broker_manager.active
            result: OrderResult = broker.submit_order(order)

            exec_result = ExecutionResult(
                success=result.status.value in ("FILLED", "ACKNOWLEDGED", "SUBMITTED"),
                order_id=order_id,
                broker_order_id=result.broker_id,
                error=result.error or "",
                filled_quantity=result.filled_quantity,
                avg_price=result.avg_price,
                slippage=abs(result.avg_price - decision.entry) if result.avg_price else 0.0,
            )

            if exec_result.success:
                self._daily_trades += 1
                if self._open_positions < auto_config.MAX_OPEN_POSITIONS:
                    self._open_positions += 1

            self._log_execution(decision, exec_result)
            return exec_result

        except Exception as exc:
            logger.error(
                "order_executor.submit_failed",
                order_id=order_id,
                error=str(exc),
            )
            exec_result = ExecutionResult(
                success=False,
                order_id=order_id,
                error=str(exc),
            )
            self._log_execution(decision, exec_result)
            return exec_result

    def close_position(self) -> None:
        """Decrement open position counter (called when position closes)."""
        self._open_positions = max(0, self._open_positions - 1)

    async def _require_approval(self, decision: TradeDecision, size: float) -> ExecutionResult:
        """Golden Rule #2: Live mode requires human approval.

        If a LiveApprovalGate is configured, sends a Telegram approval request
        and waits for human response. Otherwise logs and returns approval-required.
        """
        order_id = f"pending-{uuid.uuid4().hex[:12]}"

        logger.warning(
            "order_executor.live_approval_required",
            order_id=order_id,
            symbol=decision.symbol,
            direction=decision.direction.value,
            confidence=decision.confidence,
            size=size,
            rule="GOLDEN_RULE_2: AI_CANNOT_SUBMIT_ORDER",
        )

        if self._approval_gate is not None:
            try:
                approval_result = await self._approval_gate.request_approval(decision)

                if approval_result.approved:
                    adjusted_size = size * approval_result.size_multiplier
                    logger.info(
                        "order_executor.live_approved",
                        order_id=order_id,
                        action=approval_result.action.value,
                        size_multiplier=approval_result.size_multiplier,
                        adjusted_size=adjusted_size,
                    )
                    return self._submit_order(decision, adjusted_size)
                else:
                    logger.info(
                        "order_executor.live_rejected",
                        order_id=order_id,
                        action=approval_result.action.value,
                    )
                    return ExecutionResult(
                        success=False,
                        order_id=order_id,
                        error=f"LIVE_REJECTED:{approval_result.action.value}",
                    )
            except Exception as exc:
                logger.error("order_executor.approval_error", error=str(exc))
                return ExecutionResult(
                    success=False,
                    order_id=order_id,
                    error=f"APPROVAL_ERROR:{exc}",
                )

        # No approval gate — return pending
        exec_result = ExecutionResult(
            success=False,
            order_id=order_id,
            error="LIVE_APPROVAL_REQUIRED",
            approval_required=True,
        )
        self._log_execution(decision, exec_result)
        return exec_result

    def _check_daily_loss_breached(self) -> bool:
        """Check if daily realized P&L exceeds the loss limit (as % of equity)."""
        if self._daily_realized_pnl >= 0:
            return False
        try:
            broker = self._broker_manager.active
            equity = broker.get_account_info().equity
        except Exception:
            equity = 10000.0
        loss_pct = abs(float(self._daily_realized_pnl)) / equity * 100.0 if equity > 0 else 0.0
        return loss_pct >= auto_config.MAX_DAILY_LOSS_PCT

    def _maybe_reset_daily_stats(self) -> None:
        """Reset daily counters at midnight UTC."""
        now = datetime.now(UTC)
        if now.date() != self._last_reset_date.date():
            logger.info(
                "order_executor.daily_reset",
                prev_date=self._last_reset_date.date().isoformat(),
                new_date=now.date().isoformat(),
                trades=self._daily_trades,
                pnl=float(self._daily_realized_pnl),
            )
            self._daily_trades = 0
            self._daily_realized_pnl = Decimal("0")
            self._last_reset_date = now

    def _reject(self, reason: str) -> ExecutionResult:
        """Create a rejection result and log it."""
        logger.info("order_executor.rejected", reason=reason)
        return ExecutionResult(success=False, error=reason)

    def _log_execution(self, decision: TradeDecision, result: ExecutionResult) -> None:
        """Append to the audit trail."""
        self._execution_log.append(
            {
                "timestamp": result.timestamp.isoformat(),
                "symbol": decision.symbol,
                "direction": decision.direction.value,
                "confidence": decision.confidence,
                "entry": decision.entry,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "reasoning": decision.reasoning,
                "success": result.success,
                "order_id": result.order_id,
                "broker_order_id": result.broker_order_id,
                "error": result.error,
                "approval_required": result.approval_required,
                "mode": self._mode,
            }
        )
