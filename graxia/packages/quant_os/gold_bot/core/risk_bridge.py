"""
Risk Bridge — translates gold_bot signals to 4-Layer RiskEngine format.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ...risk.engine import (
    RiskEngine,
    Signal,
    AccountState,
    PortfolioState,
    RiskVerdict,
    RejectReason,
)
from ...risk.kill_switch import KillSwitch
from ...risk.circuit_breaker import CircuitBreaker
from .config import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    approved: bool
    quantity: float = 0.0
    reason: str = ""
    reject_reason: Optional[RejectReason] = None


class RiskBridge:
    def __init__(self, config: BotConfig):
        self.config = config
        self.kill_switch = KillSwitch()
        self.circuit_breaker = CircuitBreaker()
        self.engine = RiskEngine(kill_switch=self.kill_switch, circuit_breaker=self.circuit_breaker)
        self.peak_equity: float = config.initial_capital
        self.daily_pnl: float = 0.0
        self.weekly_pnl: float = 0.0
        self._last_reset_day: Optional[str] = None
        self._initialized_balance: float = config.initial_capital

    def check(self, signal, open_trades: list, daily_pnl: float,
              balance: float = 0.0, equity: float = 0.0,
              free_margin: float = 0.0, margin_level_pct: float = 999.0) -> RiskCheckResult:
        direction = "BUY" if signal.direction.value == "BUY" else "SELL"
        conviction = min(signal.total_score / 500.0, 1.0)

        entry_price = signal.consensus_entry or 0.0
        stop_loss = signal.consensus_sl or 0.0
        take_profit = signal.consensus_tp or 0.0

        risk_signal = Signal(
            symbol=self.config.symbol, conviction=conviction,
            entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit,
            direction=direction, side=direction,
            timestamp=datetime.now(timezone.utc),
            timestamp_epoch=datetime.now(timezone.utc).timestamp(),
            asset_class="metals", venue="mt5", strategy_id="gold_bot_ensemble",
        )

        if equity <= 0:
            equity = balance if balance > 0 else self.config.initial_capital
        if balance <= 0:
            balance = equity

        if self.peak_equity <= 0 or self.peak_equity == self.config.initial_capital and equity < self.config.initial_capital:
            self.peak_equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        current_dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        account = AccountState(
            equity=equity, balance=balance, daily_pnl=daily_pnl,
            weekly_pnl=self.weekly_pnl, max_drawdown_pct=current_dd,
            margin_level_pct=margin_level_pct,
            free_margin=free_margin if free_margin > 0 else equity,
            peak_equity=self.peak_equity, current_drawdown_pct=current_dd,
            open_positions=len(open_trades),
        )

        portfolio = PortfolioState(
            total_exposure_pct=min(len(open_trades) * 0.1, 0.8),
            class_exposure_pct={"metals": min(len(open_trades) * 0.1, 0.3)},
            venue_exposure_pct={"mt5": min(len(open_trades) * 0.1, 0.5)},
            position_symbols=[self.config.symbol] * len(open_trades),
        )

        verdict: RiskVerdict = self.engine.evaluate(signal=risk_signal, account=account, portfolio=portfolio)

        if verdict.approved:
            qty = self._calculate_gold_position_size(balance, entry_price, stop_loss, verdict.approved_quantity)
            return RiskCheckResult(approved=True, quantity=qty, reason="Approved by 4-layer risk engine")
        else:
            return RiskCheckResult(approved=False, quantity=0.0, reason=verdict.reason, reject_reason=verdict.reason_code)

    def _calculate_gold_position_size(self, balance, entry_price, stop_loss, approved_quantity):
        if balance <= 0 or entry_price <= 0 or stop_loss <= 0:
            return 0.0
        risk_pct = min(self.config.max_risk_per_trade_pct / 100, 0.01)
        risk_amount = balance * risk_pct
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit <= 0:
            return 0.0
        quantity = risk_amount / (risk_per_unit * self.config.units_per_lot)
        quantity = round(quantity, 2)
        quantity = min(quantity, self.config.max_position_size_lots)
        quantity = max(quantity, 0.01)
        if approved_quantity > 0 and approved_quantity < quantity:
            quantity = round(approved_quantity, 2)
        return quantity

    def check_breakeven(self, trade, current_price: float) -> bool:
        if trade.direction.value == "BUY":
            profit_pips = (current_price - trade.entry_price) / 0.01
        else:
            profit_pips = (trade.entry_price - current_price) / 0.01
        return profit_pips >= self.config.breakeven_trigger_pips

    def reset_daily(self):
        self.daily_pnl = 0.0

    def reset_weekly(self):
        self.weekly_pnl = 0.0

    def update_pnl(self, daily_pnl: float, weekly_pnl: float = None):
        self.daily_pnl = daily_pnl
        if weekly_pnl is not None:
            self.weekly_pnl = weekly_pnl
