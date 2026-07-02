"""Entry Executor — converts SweepSignal into executable orders.

Receives signal from Phase 3, applies risk/session/spread checks,
calculates SL/TP/sizing, and outputs a ready-to-send Order.
"""
from dataclasses import dataclass
from typing import List
from datetime import datetime
from .sweep_classifier import SweepSignal


@dataclass
class EntryResult:
    should_enter: bool
    side: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0
    risk_amount: float = 0.0
    reason_code: str = ""
    order = None  # populated when should_enter=True


class EntryExecutor:
    """Rule engine that validates SweepSignal and creates orders.

    Args:
        bars: Recent OHLCV bars (for ATR calculation)
        balance: Current account balance
        spread: Current spread (for spread filter)
        session: Current session (ASIAN | LONDON | NY)
    """

    # Default parameters
    RISK_PCT = 0.005  # 0.5% risk per trade
    SL_ATR_MULT = 1.5  # stop = ATR * 1.5
    TP_REVERSAL_RR = 1.5  # 1.5R for reversal
    TP_CONTINUATION_RR = 2.0  # 2R for continuation
    MAX_SPREAD_MULT = 2.0  # reject if spread > 2x normal
    MIN_SIGNAL_CONFIDENCE = 0.5
    COOLDOWN_SECONDS = 300  # 5 min between signals on same symbol
    MAX_LEVERAGE = 5.0  # max notional/balance ratio
    MIN_STOP_PRICE = 0.001  # minimum stop distance in price units (10 pips for FX)
    MIN_STOP_ATR_MULT = 0.5  # fallback: stop distance must be at least this * ATR

    def __init__(self, bars: List[dict], balance: float,
                 spread: float = 0.0, avg_spread: float = 0.0,
                 session: str = "LONDON"):
        self.bars = bars
        self.balance = balance
        self.spread = spread
        self.avg_spread = avg_spread
        self.session = session
        self._atr = self._calc_atr(14)
        self._last_entries = {}  # symbol -> timestamp (for cooldown)

    def evaluate(self, signal: SweepSignal, symbol: str,
                 current_price: float) -> EntryResult:
        """Evaluate a SweepSignal and return EntryResult.

        Args:
            signal: SweepSignal from classifier
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            EntryResult with should_enter and order details
        """
        # --- Gate 1: Confidence ---
        if signal.confidence < self.MIN_SIGNAL_CONFIDENCE:
            return EntryResult(False, reason_code="LOW_CONFIDENCE")

        # --- Gate 2: Spread filter ---
        if self.avg_spread > 0 and self.spread > self.avg_spread * self.MAX_SPREAD_MULT:
            return EntryResult(False, reason_code="SPREAD_TOO_WIDE")

        # --- Gate 3: Session filter ---
        # Asian session is low liquidity for FX majors
        if self.session == "ASIAN":
            # Allow only if signal is very strong
            if signal.confidence < 0.8:
                return EntryResult(False, reason_code="ASIAN_SESSION_LOW_CONF")

        # --- Gate 4: Duplicate check ---
        now = datetime.now().timestamp()
        last = self._last_entries.get(symbol, 0)
        if now - last < self.COOLDOWN_SECONDS:
            return EntryResult(False, reason_code="COOLDOWN_ACTIVE")

        # --- Gate 5: Skip if already have position ---
        # (will be checked by caller)

        # --- Calculate SL and TP ---
        atr = self._atr if self._atr > 0 else 0.001
        sl_distance = atr * self.SL_ATR_MULT
        risk_amount = self.balance * self.RISK_PCT

        if signal.signal == "REVERSAL":
            rr = self.TP_REVERSAL_RR
        else:
            rr = self.TP_CONTINUATION_RR

        if signal.side == "BUY":
            stop_price = current_price - sl_distance
            take_profit = current_price + sl_distance * rr
        else:
            stop_price = current_price + sl_distance
            take_profit = current_price - sl_distance * rr

        # --- Position size ---
        # ponytail: cap stop distance to avoid oversized positions from tiny ATR
        sl_distance = max(sl_distance, self.MIN_STOP_PRICE, self._atr * self.MIN_STOP_ATR_MULT)
        position_size = risk_amount / sl_distance if sl_distance > 0 else 0

        # --- Gate 6: Leverage cap ---
        notional = position_size * current_price
        max_notional = self.balance * self.MAX_LEVERAGE
        if notional > max_notional and max_notional > 0:
            position_size = max_notional / current_price
            risk_amount = position_size * sl_distance

        # --- Gate 7: Zero size check ---
        if position_size <= 0:
            return EntryResult(False, reason_code="ZERO_SIZE")

        # Record entry for cooldown
        self._last_entries[symbol] = now

        # Build result
        return EntryResult(
            should_enter=True,
            side=signal.side,
            entry_price=round(current_price, 5),
            stop_price=round(stop_price, 5),
            take_profit=round(take_profit, 5),
            position_size=round(position_size, 4),
            risk_amount=round(risk_amount, 2),
            reason_code=f"{signal.signal}_{signal.side}_SL={sl_distance:.5f}_RR={rr}",
        )

    def _calc_atr(self, period: int = 14) -> float:
        """ATR from bars."""
        if len(self.bars) < period:
            return 0.0
        trs = []
        for i in range(1, len(self.bars)):
            hl = self.bars[i]["high"] - self.bars[i]["low"]
            hc = abs(self.bars[i]["high"] - self.bars[i - 1]["close"])
            lc = abs(self.bars[i]["low"] - self.bars[i - 1]["close"])
            trs.append(max(hl, hc, lc))
        if not trs:
            return 0.0
        return sum(trs[-period:]) / min(period, len(trs))
