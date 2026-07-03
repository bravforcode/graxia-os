"""
Position Sizing Algorithms for Quant OS

Implements multiple position sizing methods:
1. Fixed Fractional (1% risk per trade)
2. Kelly Criterion (optimal growth)
3. ATR-based volatility sizing
4. Anti-Martingale (reduce after losses)

Enhanced with kvrancic patterns (A2):
- Standalone kelly_fraction() for reuse
- TradeStatsTracker for automatic performance tracking
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from ..core.config import get_config
from .risk_policy import RiskPolicy

# Default risk per trade from RiskPolicy (10 bps = 0.10%)
_DEFAULT_RISK_PCT = float(RiskPolicy().risk_per_trade_bps) / 100  # bps → pct

# Per-symbol contract sizes (units per 1 lot)
_SYMBOL_CONTRACT_SIZES: dict[str, float] = {
    "XAUUSD": 100,       # 100 oz per lot
    "XAGUSD": 5000,      # 5000 oz per lot
    "BTCUSD": 1,         # 1 BTC per lot
    "ETHUSD": 1,         # 1 ETH per lot
    "EURUSD": 100_000,   # standard forex lot
    "GBPUSD": 100_000,
    "USDJPY": 100_000,
    "AUDUSD": 100_000,
    "USDCAD": 100_000,
    "USDCHF": 100_000,
    "NZDUSD": 100_000,
}
_DEFAULT_FOREX_LOT = 100_000


def _units_per_lot_for_symbol(symbol: str) -> float:
    """Return units-per-lot for the given symbol, defaulting to standard forex."""
    return _SYMBOL_CONTRACT_SIZES.get(symbol.upper(), _DEFAULT_FOREX_LOT)

# ── A2: Standalone Kelly helper (kvrancic pattern) ───────────────


def kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> float:
    """
    Calculate Kelly Criterion fraction.

    f* = (b*p - q) / b
    where b = avg_win/avg_loss, p = win_rate, q = 1-p

    Args:
        win_rate: historical win probability (0.0-1.0)
        avg_win: average win magnitude (absolute value)
        avg_loss: average loss magnitude (absolute value)
        fraction: Kelly fraction to use (0.25 = quarter-Kelly, default)

    Returns:
        Kelly fraction capped at [0, fraction]. Returns 0 if edge is negative.

    Example:
        >>> kelly_fraction(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        0.0875  # quarter-Kelly
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    b = avg_win / avg_loss  # payoff ratio
    p = win_rate
    q = 1.0 - p

    full_kelly = (b * p - q) / b

    if full_kelly <= 0:
        return 0.0  # no edge

    return full_kelly * fraction


@dataclass
class TradeRecord:
    """Single trade record for stats tracking"""

    pnl: float
    is_win: bool


class TradeStatsTracker:
    """
    Tracks rolling trade statistics for Kelly sizing.
    Uses a sliding window to avoid stale data from very old trades.

    Example:
        tracker = TradeStatsTracker(window=100)
        for trade_pnl in pnl_list:
            tracker.record(trade_pnl)
        kelly = kelly_fraction(
            win_rate=tracker.win_rate,
            avg_win=tracker.avg_win,
            avg_loss=tracker.avg_loss,
        )
    """

    def __init__(self, window: int = 100):
        self._window = window
        self._trades: deque[TradeRecord] = deque(maxlen=window)
        self._total_wins = 0
        self._total_losses = 0

    def record(self, pnl: float) -> None:
        """Record a trade outcome"""
        is_win = pnl > 0
        self._trades.append(TradeRecord(pnl=pnl, is_win=is_win))
        if is_win:
            self._total_wins += 1
        elif pnl < 0:
            self._total_losses += 1

    @property
    def win_rate(self) -> float:
        """Win rate over the sliding window"""
        if len(self._trades) == 0:
            return 0.5  # neutral default
        wins = sum(1 for t in self._trades if t.is_win)
        return wins / len(self._trades)

    @property
    def avg_win(self) -> float:
        """Average win magnitude over the sliding window"""
        wins = [t.pnl for t in self._trades if t.is_win]
        return sum(wins) / len(wins) if wins else 1.0

    @property
    def avg_loss(self) -> float:
        """Average loss magnitude (absolute) over the sliding window"""
        losses = [abs(t.pnl) for t in self._trades if t.pnl < 0]
        return sum(losses) / len(losses) if losses else 1.0

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def profit_factor(self) -> float:
        """Profit factor over the sliding window"""
        gross_profit = sum(t.pnl for t in self._trades if t.pnl > 0)
        gross_loss = sum(abs(t.pnl) for t in self._trades if t.pnl < 0)
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def get_stats(self) -> dict:
        return {
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "trade_count": self.trade_count,
            "profit_factor": self.profit_factor,
        }


@dataclass
class PositionSizeResult:
    """Position sizing result"""

    lots: Decimal
    units: Decimal
    notional_value: Decimal
    risk_amount: Decimal
    risk_pct: float
    method: str
    notes: str = ""


class PositionSizer(ABC):
    """Abstract base class for position sizing"""

    def __init__(self, name: str, units_per_lot: float = 100000.0):
        self.name = name
        self.units_per_lot = units_per_lot
        self.config = get_config()

    @abstractmethod
    def calculate(
        self, account_balance: Decimal, entry_price: Decimal, stop_loss: Decimal, symbol: str = "", **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size.

        Args:
            account_balance: Current account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            symbol: Trading symbol
            **kwargs: Additional parameters specific to sizer

        Returns:
            PositionSizeResult with calculated size
        """
        pass

    def _apply_limits(self, lots: Decimal, units: Decimal, notional: Decimal, account_balance: Decimal) -> tuple:
        """
        Apply position size limits.

        Returns:
            (limited_lots, limited_units, limited_notional)
        """
        # Get mode-specific limits
        limits = self.config.get_mode_risk_limits()
        max_position_size = limits.get("max_position_size", float("inf"))

        # Apply max position size limit
        if max_position_size != float("inf"):
            max_notional = Decimal(str(max_position_size))
            if notional > max_notional:
                ratio = max_notional / notional
                lots = (lots * ratio).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                units = (units * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
                notional = max_notional

        # Max exposure limit
        max_exposure = account_balance * Decimal(str(self.config.max_portfolio_exposure_pct)) / 100
        if notional > max_exposure:
            ratio = max_exposure / notional
            lots = (lots * ratio).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            units = (units * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
            notional = max_exposure

        return lots, units, notional


class FixedFractionalSizer(PositionSizer):
    """
    Fixed Fractional Position Sizing.

    Risk fixed percentage of account per trade.
    Default: 1% as per golden rules.
    """

    def __init__(self, risk_pct: float | None = None, units_per_lot: float = 100000.0):
        super().__init__("FixedFractional", units_per_lot)
        self.risk_pct = risk_pct or _DEFAULT_RISK_PCT

    def calculate(
        self, account_balance: Decimal, entry_price: Decimal, stop_loss: Decimal, symbol: str = "", **kwargs
    ) -> PositionSizeResult:
        """Calculate position size based on fixed risk percentage"""
        # Use per-symbol contract size if available
        units_per_lot = _units_per_lot_for_symbol(symbol) if symbol else self.units_per_lot

        # Calculate risk amount
        risk_amount = account_balance * Decimal(str(self.risk_pct)) / 100

        # Calculate price risk per unit
        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price - cannot calculate size",
            )

        # Calculate units
        units = risk_amount / price_risk

        # Convert to lots using per-symbol contract size
        lots = units / Decimal(str(units_per_lot))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)  # Round to 2 decimals
        units = lots * Decimal(str(units_per_lot))

        # Calculate notional value
        notional = units * entry_price

        # Apply limits
        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)

        # Recalculate actual risk
        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)

        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=f"Risk {actual_risk_pct:.2f}% of account",
        )


class KellySizer(PositionSizer):
    """
    Kelly Criterion Position Sizing.

    Optimal fraction for maximum growth based on:
    f = (bp - q) / b
    where:
    b = average win / average loss (payoff ratio)
    p = win probability
    q = 1 - p (loss probability)

    Uses half-Kelly for safety (conservative Kelly).
    """

    def __init__(
        self, win_rate: float = 0.55, avg_win: float = 1.5, avg_loss: float = 1.0, units_per_lot: float = 100000.0
    ):
        super().__init__("Kelly", units_per_lot)
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.kelly_fraction = 0.5  # Half-Kelly for safety

    def calculate(
        self, account_balance: Decimal, entry_price: Decimal, stop_loss: Decimal, symbol: str = "", **kwargs
    ) -> PositionSizeResult:
        """Calculate position size using Kelly Criterion"""
        # Kelly formula: f = (bp - q) / b
        p = self.win_rate
        q = 1 - p
        b = self.avg_win / self.avg_loss  # Payoff ratio

        kelly_pct = (b * p - q) / b

        # Apply Kelly fraction (half-Kelly for safety)
        adjusted_kelly = kelly_pct * self.kelly_fraction

        # Cap at golden rule max
        max_risk = _DEFAULT_RISK_PCT / 100
        if adjusted_kelly > max_risk:
            adjusted_kelly = max_risk
            capped = True
        else:
            capped = False

        # Use fixed fractional with Kelly percentage
        risk_pct = adjusted_kelly * 100
        risk_amount = account_balance * Decimal(str(risk_pct)) / 100

        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price",
            )

        units = risk_amount / price_risk
        lots = units / Decimal(str(self.units_per_lot))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(self.units_per_lot))
        notional = units * entry_price

        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)

        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)

        notes = f"Kelly: {kelly_pct*100:.2f}%, Using: {risk_pct:.2f}% (half-Kelly)"
        if capped:
            notes += " [capped by golden rule]"

        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=notes,
        )

    def update_stats(self, win_rate: float, avg_win: float, avg_loss: float) -> None:
        """Update Kelly parameters from historical performance"""
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss


class ATRSizer(PositionSizer):
    """
    ATR-based Position Sizing.

    Adjusts position size based on market volatility (ATR).
    Higher volatility = smaller position.
    """

    def __init__(self, atr_multiple: float = 1.5, base_risk_pct: float = 1.0, units_per_lot: float = 100000.0):
        super().__init__("ATR", units_per_lot)
        self.atr_multiple = atr_multiple
        self.base_risk_pct = base_risk_pct

    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        atr: Decimal | None = None,
        **kwargs,
    ) -> PositionSizeResult:
        """Calculate position size based on ATR volatility"""
        if atr is None or atr == 0:
            # Fall back to fixed fractional
            fallback = FixedFractionalSizer(self.base_risk_pct)
            result = fallback.calculate(account_balance, entry_price, stop_loss, symbol)
            result.method = f"{self.name} (fallback to FixedFractional)"
            return result

        # Calculate stop distance based on ATR
        atr_stop_distance = atr * Decimal(str(self.atr_multiple))

        # Risk amount
        risk_amount = account_balance * Decimal(str(self.base_risk_pct)) / 100

        # Calculate units based on ATR stop
        units = risk_amount / atr_stop_distance
        lots = units / Decimal(str(self.units_per_lot))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(self.units_per_lot))
        notional = units * entry_price

        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)

        actual_risk = units * atr_stop_distance
        actual_risk_pct = float(actual_risk / account_balance * 100)

        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=f"ATR: {float(atr):.5f}, Stop: {float(atr_stop_distance):.5f} ({self.atr_multiple}× ATR)",
        )


class AntiMartingaleSizer(PositionSizer):
    """
    Anti-Martingale Position Sizing.

    Increases position size after wins, decreases after losses.
    Opposite of dangerous Martingale strategy.
    """

    def __init__(
        self,
        base_risk_pct: float = 1.0,
        consecutive_losses: int = 0,
        consecutive_wins: int = 0,
        units_per_lot: float = 100000.0,
    ):
        super().__init__("AntiMartingale", units_per_lot)
        self.base_risk_pct = base_risk_pct
        self.consecutive_losses = consecutive_losses
        self.consecutive_wins = consecutive_wins

    def calculate(
        self, account_balance: Decimal, entry_price: Decimal, stop_loss: Decimal, symbol: str = "", **kwargs
    ) -> PositionSizeResult:
        """Calculate position size with anti-martingale adjustment"""
        # Adjust risk based on streak
        adjustment = 1.0

        # Reduce size after losses (check higher streaks first)
        if self.consecutive_losses >= 3:
            adjustment = 0.25  # Quarter size after 3+ losses
        elif self.consecutive_losses >= 2:
            adjustment = 0.5  # Half size after 2 losses

        # Increase size after wins (capped, check higher streaks first)
        if self.consecutive_wins >= 3:
            adjustment = min(adjustment * 1.5, 2.0)  # Max 2x
        elif self.consecutive_wins >= 2:
            adjustment = min(adjustment * 1.25, 1.5)  # Max 1.5x

        adjusted_risk = self.base_risk_pct * adjustment

        # Cap at golden rule
        adjusted_risk = min(adjusted_risk, _DEFAULT_RISK_PCT)

        # Use fixed fractional with adjusted percentage
        risk_amount = account_balance * Decimal(str(adjusted_risk)) / 100

        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price",
            )

        units = risk_amount / price_risk
        lots = units / Decimal(str(self.units_per_lot))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(self.units_per_lot))
        notional = units * entry_price

        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)

        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)

        # Build notes
        notes_parts = [f"Base: {self.base_risk_pct}%, Adj: {adjusted_risk:.2f}%"]
        if self.consecutive_losses > 0:
            notes_parts.append(f"({self.consecutive_losses} losses)")
        elif self.consecutive_wins > 0:
            notes_parts.append(f"({self.consecutive_wins} wins)")

        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=" ".join(notes_parts),
        )

    def record_outcome(self, pnl: float) -> None:
        """Record trade outcome for streak tracking"""
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        else:
            # Breakeven - reset both
            self.consecutive_wins = 0
            self.consecutive_losses = 0


def get_default_sizer() -> PositionSizer:
    """Get default position sizer based on configuration"""
    config = get_config()

    # Default to fixed fractional with configured risk
    return FixedFractionalSizer(config.max_risk_per_trade_pct)
