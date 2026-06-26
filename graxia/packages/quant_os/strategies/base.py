"""Base strategy class for Quant OS

Enhanced with jesse-inspired ergonomics (A1):
- should_long / should_short helpers
- on_trade_closed callback
- hyperparameters() for Optuna
- supports_numba() flag
- Convenience properties: price, balance, position, available_margin
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from ..core.enums import CloseReason, OrderSide, RegimeType, SignalType


@dataclass
class TradeResult:
    """Result of a closed trade — passed to on_trade_closed callback"""

    trade_id: str
    symbol: str
    side: OrderSide
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl: Decimal
    pnl_pct: float
    close_reason: CloseReason
    opened_at: datetime
    closed_at: datetime
    duration_bars: int = 0
    fees: Decimal = Decimal("0")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HyperparameterRange:
    """Defines a hyperparameter search space for Optuna integration"""

    name: str
    low: float
    high: float
    step: float | None = None
    log: bool = False
    choices: list[Any] | None = None

    def to_optuna_distribution(self):
        """Convert to Optuna-compatible distribution kwargs"""
        if self.choices is not None:
            return {"choices": self.choices}
        kwargs = {"low": self.low, "high": self.high}
        if self.step is not None:
            kwargs["step"] = self.step
        if self.log:
            kwargs["log"] = True
        return kwargs


@dataclass
class Signal:
    """Trading signal from a strategy"""

    id: str
    strategy_id: str
    symbol: str
    signal_type: SignalType
    timestamp: datetime

    # Signal strength
    confidence: float = 0.0  # 0.0 to 1.0
    strength: str = "medium"  # weak, medium, strong

    # Price levels
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    # Context
    regime: RegimeType | None = None
    timeframe: str = "M15"

    # Indicators
    indicator_values: dict[str, Any] = field(default_factory=dict)

    # Metadata
    raw_payload: dict | None = None
    notes: str = ""

    @classmethod
    def create(
        cls, strategy_id: str, symbol: str, signal_type: SignalType, confidence: float = 0.0, **kwargs
    ) -> "Signal":
        """Factory method to create a signal"""
        return cls(
            id=str(uuid4()),
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type=signal_type,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            **kwargs,
        )

    @property
    def is_buy(self) -> bool:
        return self.signal_type == SignalType.BUY

    @property
    def is_sell(self) -> bool:
        return self.signal_type == SignalType.SELL

    @property
    def risk_reward_ratio(self) -> float | None:
        """Calculate risk/reward ratio if SL and TP are set"""
        if self.stop_loss is None or self.take_profit is None or self.entry_price is None:
            return None

        risk = abs(float(self.entry_price) - float(self.stop_loss))
        reward = abs(float(self.take_profit) - float(self.entry_price))

        if risk == 0:
            return None

        return reward / risk


@dataclass
class StrategyConfig:
    """Configuration for a strategy"""

    name: str
    version: str = "1.0.0"

    # Symbols and timeframes
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=lambda: ["M15"])

    # Risk parameters
    risk_per_trade_pct: float = 1.0
    max_trades_per_day: int = 5

    # Entry/exit rules
    min_confidence: float = 0.60
    min_risk_reward: float = 1.5

    # Filters
    require_trend_confirm: bool = True
    require_volume_spike: bool = False
    regime_filter: list[RegimeType] | None = None


class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    All strategies must implement:
    - generate_signal(): Produce trading signals from market data
    - required_features(): List required features/indicators
    - is_valid_for_regime(): Check if strategy is valid for current regime
    """

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig(name=self.__class__.__name__)
        self.id = f"{self.__class__.__name__}_{self.config.version}"

        # Performance tracking
        self.signals_generated: int = 0
        self.trades_taken: int = 0
        self.win_count: int = 0
        self.loss_count: int = 0

        # Runtime state (set by engine before strategy runs)
        self._current_price: Decimal | None = None
        self._account_balance: Decimal | None = None
        self._position: dict[str, Any] | None = None
        self._available_margin: Decimal | None = None

    # ── Convenience properties (jesse pattern) ──────────────────────

    @property
    def price(self) -> Decimal | None:
        """Current market price, set by engine before strategy runs"""
        return self._current_price

    @property
    def balance(self) -> Decimal | None:
        """Current account balance, set by engine before strategy runs"""
        return self._account_balance

    @property
    def position(self) -> dict[str, Any] | None:
        """Current open position for this symbol (None if flat)"""
        return self._position

    @property
    def available_margin(self) -> Decimal | None:
        """Available margin for new positions"""
        return self._available_margin

    def set_runtime_state(
        self,
        price: Decimal | None = None,
        balance: Decimal | None = None,
        position: dict[str, Any] | None = None,
        available_margin: Decimal | None = None,
    ) -> None:
        """Engine calls this before generate_signal to inject runtime context"""
        if price is not None:
            self._current_price = price
        if balance is not None:
            self._account_balance = balance
        if position is not None:
            self._position = position
        if available_margin is not None:
            self._available_margin = available_margin

    # ── Entry / exit helpers (jesse pattern) ────────────────────────

    def should_long(self, data: dict[str, Any]) -> bool:
        """
        Override to return True when strategy wants a long entry.
        Called by generate_signal() default path. Default: False.

        Args:
            data: dict with at least 'close', 'ohlcv', 'indicators', 'regime'
        """
        return False

    def should_short(self, data: dict[str, Any]) -> bool:
        """
        Override to return True when strategy wants a short entry.
        Called by generate_signal() default path. Default: False.

        Args:
            data: dict with at least 'close', 'ohlcv', 'indicators', 'regime'
        """
        return False

    # ── Lifecycle callbacks (jesse pattern) ──────────────────────────

    def on_trade_closed(self, trade: TradeResult) -> None:  # noqa: B027
        """
        Called after a trade closes. Override for adaptive logic:
        - adjust parameters after consecutive losses
        - track regime-specific performance
        - implement recovery protocols
        """
        pass

    # ── Hyperparameter metadata (jesse + Optuna) ────────────────────

    def hyperparameters(self) -> dict[str, HyperparameterRange]:
        """
        Return search space for Optuna. Override to expose tunable params.
        Keys become Optuna param names.

        Example:
            return {
                "ema_fast": HyperparameterRange("ema_fast", 5, 20, step=1),
                "atr_mult": HyperparameterRange("atr_mult", 1.0, 3.0, step=0.1),
            }
        """
        return {}

    def from_hyperparameters(self, params: dict[str, Any]) -> None:
        """
        Apply a set of hyperparameters (from Optuna trial or manual config).
        Override to map param names to instance attributes.
        """
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)

    # ── Performance hints ────────────────────────────────────────────

    def supports_numba(self) -> bool:
        """
        Return True if strategy signal logic can run in Numba JIT.
        Override for strategies with pure numerical logic (no dicts/objects).
        """
        return False

    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],  # OHLCV data
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """
        Generate trading signal from market data.

        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            ohlcv_data: Dictionary with 'open', 'high', 'low', 'close', 'volume' arrays
            indicators: Pre-calculated indicators (optional)
            regime: Current market regime (optional)

        Returns:
            Signal if conditions met, None otherwise
        """
        pass

    @abstractmethod
    def required_features(self) -> list[str]:
        """
        Return list of required features/indicators.

        Returns:
            List of feature names (e.g., ["ema_9", "ema_20", "rsi_14"])
        """
        pass

    def is_valid_for_regime(self, regime: RegimeType) -> bool:
        """
        Check if strategy is valid for given market regime.
        Override for regime-specific strategies.
        """
        if self.config.regime_filter is None:
            return True
        return regime in self.config.regime_filter

    def calculate_position_size(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_pct: float | None = None,
        units_per_lot: float = 100000.0,
    ) -> Decimal:
        """
        Calculate position size based on risk parameters.

        Returns:
            Position size in lots/units
        """
        risk_amount = account_balance * Decimal(str(risk_pct or self.config.risk_per_trade_pct)) / 100

        price_risk = abs(entry_price - stop_loss)
        if price_risk == 0:
            return Decimal("0")

        # Convert to lot size
        units = risk_amount / price_risk
        lots = units / Decimal(str(units_per_lot))

        return lots.quantize(Decimal("0.01"))  # Round to 2 decimal places

    def record_outcome(self, pnl: float, trade: TradeResult | None = None) -> None:
        """
        Record trade outcome for performance tracking.
        If trade is provided, also fires on_trade_closed callback.
        """
        self.trades_taken += 1
        if pnl > 0:
            self.win_count += 1
        elif pnl < 0:
            self.loss_count += 1
        if trade is not None:
            self.on_trade_closed(trade)

    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        if self.trades_taken == 0:
            return 0.0
        return self.win_count / self.trades_taken

    @staticmethod
    def create_trade_result(
        symbol: str,
        side: OrderSide,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        close_reason: CloseReason,
        opened_at: datetime,
        closed_at: datetime,
        fees: Decimal = Decimal("0"),
        duration_bars: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> TradeResult:
        """Helper to build a TradeResult with auto-calculated PnL"""
        if side == OrderSide.BUY:
            raw_pnl = (exit_price - entry_price) * quantity
        else:
            raw_pnl = (entry_price - exit_price) * quantity
        pnl = raw_pnl - fees
        pnl_pct = float(pnl / (entry_price * quantity)) * 100 if entry_price * quantity != 0 else 0.0
        return TradeResult(
            trade_id=str(uuid4()),
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            close_reason=close_reason,
            opened_at=opened_at,
            closed_at=closed_at,
            duration_bars=duration_bars,
            fees=fees,
            metadata=metadata or {},
        )

    def get_stats(self) -> dict[str, Any]:
        """Get strategy statistics"""
        return {
            "id": self.id,
            "name": self.config.name,
            "version": self.config.version,
            "signals_generated": self.signals_generated,
            "trades_taken": self.trades_taken,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": self.win_rate,
        }
