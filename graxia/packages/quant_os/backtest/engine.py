"""
Backtest Engine - Core backtesting framework

Simulates strategy execution on historical data with:
- Realistic fill model (slippage, commission) via ExecutionSimulator
- Position tracking with SL/TP
- Equity curve generation
- Walk-forward support
- Event-driven mode (B1): optional EventBus integration
- Numba hot path (B3): optional JIT indicator calculation
- Batch mode (C4): run multiple configs with shared indicators
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any
from uuid import uuid4

try:
    import numpy as np
    from numba import njit as _numba_njit

    _NUMBA_AVAILABLE = True
except ImportError:
    _NUMBA_AVAILABLE = False
    import numpy as np

    def _numba_njit(*args, **kwargs):
        """Graceful fallback: return the function unchanged."""

        def decorator(func):
            return func

        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator


from ..core.enums import CloseReason, PositionType, SignalType
from ..core.events import BarEvent
from ..core.exceptions import StrictMTFViolation
from ..core.lookahead_guard import LookaheadGuard
from ..execution.conservative_bar_model import estimate_bid_ask_from_bar
from ..execution.execution_simulator import (
    BacktestExecutionSimulator,
    ContractSpec,
    MarketSnapshot,
    OrderIntent,
)
from ..execution.execution_simulator import (
    Position as ExecPosition,
)
from ..execution.fill_model import ExecutionQuality
from ..execution.fill_model import Side as FillSide
from ..execution.fill_model import simulate_exit as fill_simulate_exit
from ..strategies.base import Signal, Strategy

# Phase 4: Wire in regime detection, margin simulation, real-time P&L
try:
    from ..risk.margin_simulator import MarginSimulator
    from ..risk.realtime_pnl import RealTimePnLTracker
    from ..validation.regime_detector import RegimeDetector

    _PHASE4_WIRING_AVAILABLE = True
except ImportError:
    _PHASE4_WIRING_AVAILABLE = False

# Phase 3: Market impact (module-level to avoid per-bar lazy import)
try:
    from ..execution.market_impact import estimate_market_impact_bps

    _MARKET_IMPACT_AVAILABLE = True
except ImportError:
    _MARKET_IMPACT_AVAILABLE = False

# Swap cost model
try:
    from ..core.risk.swap_cost import get_live_swap_rates, get_swap_cost_for_trade

    _SWAP_COST_AVAILABLE = True
except ImportError:
    _SWAP_COST_AVAILABLE = False


@dataclass(frozen=True)
class InlineContractSpec:
    """Deterministic contract spec for backtest sizing."""

    symbol: str = ""
    trade_contract_size: Decimal = Decimal("100")
    trade_tick_size: Decimal = Decimal("0.01")
    trade_tick_value: Decimal = Decimal("1.0")
    volume_step: Decimal = Decimal("0.01")
    volume_min: Decimal = Decimal("0.01")
    volume_max: Decimal = Decimal("100")
    stops_level_points: Decimal = Decimal("0")
    snapshot_hash: str = "inline"

    @classmethod
    def for_symbol(cls, symbol: str) -> "InlineContractSpec":
        _FX = 100_000
        _CRYPTO = 1
        specs = {
            "XAUUSD": cls(
                trade_contract_size=Decimal("100"), trade_tick_size=Decimal("0.01"), trade_tick_value=Decimal("1.0")
            ),
            "EURUSD": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("10.0"),
            ),
            "GBPUSD": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("10.0"),
            ),
            "USDJPY": cls(
                trade_contract_size=Decimal(str(_FX)), trade_tick_size=Decimal("0.01"), trade_tick_value=Decimal("6.67")
            ),
            "AUDUSD": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("10.0"),
            ),
            "USDCAD": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("7.50"),
            ),
            "USDCHF": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("11.00"),
            ),
            "NZDUSD": cls(
                trade_contract_size=Decimal(str(_FX)),
                trade_tick_size=Decimal("0.0001"),
                trade_tick_value=Decimal("10.0"),
            ),
            "BTCUSDT": cls(
                trade_contract_size=Decimal(str(_CRYPTO)),
                trade_tick_size=Decimal("0.01"),
                trade_tick_value=Decimal("0.01"),
            ),
        }
        return specs.get(symbol, cls())


def _historical_size(
    equity: Decimal,
    risk_per_trade_bps: int,
    entry_price: Decimal,
    stop_loss: Decimal,
    contract: InlineContractSpec,
) -> Decimal:
    """Deterministic sizing. No MT5. No live broker."""
    if stop_loss == 0 or entry_price == 0:
        return Decimal("0")
    risk_budget = equity * Decimal(str(risk_per_trade_bps)) / Decimal("10000")
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return Decimal("0")
    ticks = stop_distance / contract.trade_tick_size
    one_lot_loss = ticks * contract.trade_tick_value
    if one_lot_loss <= 0:
        return Decimal("0")
    raw_volume = risk_budget / one_lot_loss
    # ponytail: round DOWN to volume_step
    if contract.volume_step > 0:
        rounded = (raw_volume / contract.volume_step).to_integral_value(rounding=ROUND_DOWN) * contract.volume_step
    else:
        rounded = raw_volume
    if rounded < contract.volume_min:
        return Decimal("0")
    return rounded


def _exec_side(signal_type: SignalType) -> FillSide:
    """Map SignalType to fill_model Side."""
    if signal_type == SignalType.BUY:
        return FillSide.BUY
    return FillSide.SELL


@dataclass
class BacktestConfig:
    """Backtest configuration

    Cost parameters are sourced from core.cost_model for per-asset-class parity.
    """

    initial_capital: Decimal = Decimal("10000")
    slippage_pips: float = 0.5
    spread_pips: float = 2.0  # Configurable spread in pips
    commission_per_lot: Decimal = Decimal("3.5")
    max_positions: int = 5
    risk_per_trade_bps: int = 10
    start_date: date | None = None
    end_date: date | None = None
    strict_mtf: bool = True
    cost_scenario: str = "base"
    enable_swap: bool = True
    cost_params: Any = None  # Optional[CostParams] from core.cost_model
    fill_timing: Any = None  # Optional[FillTimingConfig] for latency-based slippage


@dataclass
class BacktestPosition:
    """Open position during backtest"""

    id: str
    symbol: str
    side: PositionType
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    entry_time: datetime | None = None
    strategy_id: str = ""
    unrealized_pnl: Decimal = Decimal("0")
    entry_spread_cost: Decimal = Decimal("0")
    entry_slippage_cost: Decimal = Decimal("0")
    execution_quality: str = ""
    signal_bar_index: int = -1
    contract_size: Decimal = Decimal("100")
    tick_size: Decimal = Decimal("0.01")
    tick_value: Decimal = Decimal("1.0")


@dataclass
class BacktestTrade:
    """Completed trade"""

    id: str
    symbol: str
    side: PositionType
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    return_pct: Decimal
    fees: Decimal
    close_reason: CloseReason
    strategy_id: str = ""
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    execution_quality: str = ""
    entry_spread_cost: Decimal = Decimal("0")
    entry_slippage_cost: Decimal = Decimal("0")
    exit_slippage_cost: Decimal = Decimal("0")
    swap_cost: Decimal = Decimal("0")
    ambiguous_bar: bool = False
    signal_id: str = ""
    order_intent_id: str = ""


@dataclass
class EquityPoint:
    """Point on equity curve"""

    timestamp: datetime
    equity: float
    balance: float
    drawdown_pct: float
    open_positions: int


@_numba_njit
def _ema_numba(close, length):
    """Numba JIT exponential moving average."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length:
        return out
    alpha = 2.0 / (length + 1.0)
    # seed with SMA
    sma = 0.0
    for i in range(length):
        sma += close[i]
    sma /= length
    out[length - 1] = sma
    for i in range(length, n):
        out[i] = close[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


@_numba_njit
def _rsi_numba(close, length):
    """Numba JIT RSI."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 1:
        return out
    gains = np.zeros(length)
    losses = np.zeros(length)
    for i in range(1, length + 1):
        diff = close[i] - close[i - 1]
        if diff > 0:
            gains[i - 1] = diff
        else:
            losses[i - 1] = -diff
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(length):
        avg_gain += gains[i]
        avg_loss += losses[i]
    avg_gain /= length
    avg_loss /= length
    if avg_loss == 0:
        out[length] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[length] = 100.0 - 100.0 / (1.0 + rs)
    for i in range(length + 1, n):
        diff = close[i] - close[i - 1]
        if diff > 0:
            avg_gain = (avg_gain * (length - 1) + diff) / length
            avg_loss = (avg_loss * (length - 1)) / length
        else:
            avg_gain = (avg_gain * (length - 1)) / length
            avg_loss = (avg_loss * (length - 1) - diff) / length
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


@_numba_njit
def _atr_numba(high, low, close, length):
    """Numba JIT ATR (using true range)."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 1:
        return out
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, max(hc, lc))
    # seed with SMA of TR
    atr_val = 0.0
    for i in range(length):
        atr_val += tr[i]
    atr_val /= length
    out[length - 1] = atr_val
    for i in range(length, n):
        atr_val = (atr_val * (length - 1) + tr[i]) / length
        out[i] = atr_val
    return out


def _indicators_numba_impl(close_arr, high_arr, low_arr, vol_arr):
    """Pure-numba indicator batch — called when strategy.supports_numba()."""
    result = {}
    result["ema_9"] = _ema_numba(close_arr, 9)
    result["ema_20"] = _ema_numba(close_arr, 20)
    result["ema_50"] = _ema_numba(close_arr, 50)
    result["ema_200"] = _ema_numba(close_arr, 200)
    result["rsi_14"] = _rsi_numba(close_arr, 14)
    result["atr_14"] = _atr_numba(high_arr, low_arr, close_arr, 14)
    # Volume SMA — P4 FIX: O(n) running sum instead of O(n × window) nested loop
    n = len(vol_arr)
    vol_sma = np.full(n, np.nan)
    if n >= 20:
        run_sum = 0.0
        for j in range(20):
            run_sum += vol_arr[j]
        vol_sma[19] = run_sum / 20.0
        for i in range(20, n):
            run_sum += vol_arr[i] - vol_arr[i - 20]
            vol_sma[i] = run_sum / 20.0
    result["volume_sma_20"] = vol_sma
    return result


class BacktestEngine:
    """
    Event-driven backtesting engine.

    Usage:
        engine = BacktestEngine(config)
        engine.set_strategy(my_strategy)
        engine.load_data(ohlcv_data, timestamps)
        engine.set_multi_timeframe(h1_data, h1_ts, m15_data, m15_ts)  # optional
        results = engine.run()
    """

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

        # Execution simulator
        self._simulator = BacktestExecutionSimulator()

        # Symbol — set via set_symbol() or load_data(); fallback "BACKTEST" for compat
        self._symbol: str = "BACKTEST"

        # State
        self.balance = Decimal(str(self.config.initial_capital))
        self.equity = Decimal(str(self.config.initial_capital))
        self.peak_equity = Decimal(str(self.config.initial_capital))
        self.positions: dict[str, BacktestPosition] = {}
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[EquityPoint] = []

        # Strategy
        self.strategy: Strategy | None = None

        # Data
        self.ohlcv_data: dict[str, list] = {}
        self.timestamps: list[datetime] = []
        self.current_index: int = 0

        # Multi-TF cursor (ponytail: set via set_multi_timeframe)
        self._mtf_cursor = None

        # Metrics tracking
        self._daily_pnl: float = 0.0
        self._peak_equity_pct: float = 0.0
        self._current_drawdown_pct: float = 0.0

        # Phase 4: Regime detection, margin simulation, real-time P&L
        self._regime_detector: Any = None
        self._margin_simulator: Any = None
        self._pnl_tracker: Any = None

    def set_strategy(self, strategy: Strategy) -> None:
        """Set the strategy to backtest"""
        self.strategy = strategy

    def set_multi_timeframe(
        self,
        h1_data: dict[str, list],
        h1_ts: list[datetime],
        m15_data: dict[str, list],
        m15_ts: list[datetime],
    ) -> None:
        """
        Set multi-timeframe data for point-in-time slicing.

        MUST be called before run() when strategy needs multi-TF data.
        Creates a cursor that slices lower TFs to timestamp <= current bar.
        """
        from .mtf_cursor import MultiTimeframeCursor

        self._mtf_cursor = MultiTimeframeCursor(
            d1_data=self.ohlcv_data,
            d1_ts=self.timestamps,
            h1_data=h1_data,
            h1_ts=h1_ts,
            m15_data=m15_data,
            m15_ts=m15_ts,
        )

    def load_data(self, data: dict[str, list], timestamps: list[datetime] | None = None) -> None:
        """
        Load OHLCV data for backtesting.

        Args:
            data: Dict with 'open', 'high', 'low', 'close', 'volume' lists
            timestamps: Optional list of timestamps for each bar
        """
        self.ohlcv_data = data
        self.timestamps = timestamps or []

        # Validate data
        required_keys = ["open", "high", "low", "close"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required data key: {key}")

        if not all(len(data["close"]) == len(data[k]) for k in required_keys):
            raise ValueError("All OHLCV arrays must have same length")

    def run(self, event_bus=None) -> dict[str, Any]:
        """
        Run the backtest.

        Args:
            event_bus: Optional EventBus. If provided, a BarEvent is published
                       for every bar (B1 event-driven mode). The direct-call
                       path is always executed regardless.

        Returns:
            Dictionary with backtest results and metrics
        """
        if self.strategy is None:
            raise ValueError("No strategy set. Call set_strategy() first.")

        if not self.ohlcv_data:
            raise ValueError("No data loaded. Call load_data() first.")

        # Strict MTF: block static fallback if no cursor set
        if self.config.strict_mtf and self._mtf_cursor is None:
            raise StrictMTFViolation(
                "strict_mtf=True but no MTF cursor set. "
                "Call set_multi_timeframe() before run(), or set strict_mtf=False."
            )

        # Reset state
        self._reset()

        close = self.ohlcv_data["close"]
        high = self.ohlcv_data.get("high", close)
        low = self.ohlcv_data.get("low", close)
        open_price = self.ohlcv_data.get("open", close)
        volume = self.ohlcv_data.get("volume", [0] * len(close))

        total_bars = len(close)

        guard = LookaheadGuard(strict=True)
        guard.initialize(total_bars)

        # --- P1 FIX: Pre-compute indicators once (was O(n²) per-bar rebuild) ---
        if total_bars >= 200:
            self._precomputed_indicators = self._calculate_indicators(total_bars - 1)
        else:
            self._precomputed_indicators = {}

        # --- P3 FIX: Hoist RiskPolicy creation (was per-bar instantiation) ---
        try:
            from ..risk.risk_policy import RiskPolicy as _RP
        except ImportError:
            from risk.risk_policy import RiskPolicy as _RP
        self._risk_policy = _RP()

        # --- P2 FIX: Pre-compute bar dicts once (was O(n × Decimal) per signal) ---
        self._cached_bar_dicts = [
            {
                "open": Decimal(str(self.ohlcv_data["open"][j])),
                "high": Decimal(str(self.ohlcv_data["high"][j])),
                "low": Decimal(str(self.ohlcv_data["low"][j])),
                "close": Decimal(str(self.ohlcv_data["close"][j])),
            }
            for j in range(len(close))
        ]

        # Main loop - iterate through each bar
        for i in range(1, total_bars):
            self.current_index = i
            guard.advance()
            current_time = self.timestamps[i] if i < len(self.timestamps) else self._deterministic_timestamp(i)

            # Current bar OHLCV
            bar_open = Decimal(str(open_price[i]))
            bar_high = Decimal(str(high[i]))
            bar_low = Decimal(str(low[i]))
            bar_close = Decimal(str(close[i]))

            # B1 — Publish BarEvent if event_bus is attached
            if event_bus is not None:
                bar_event = BarEvent(
                    symbol=self._symbol,
                    timeframe="M15",
                    open=float(bar_open),
                    high=float(bar_high),
                    low=float(bar_low),
                    close=float(bar_close),
                    volume=float(volume[i]),
                    bar_index=i,
                    source="backtest_engine",
                )
                event_bus.publish(bar_event)

            # 1. Check stop loss / take profit on existing positions
            self._check_exits(bar_high, bar_low, bar_close, current_time, i)

            # Risk halt checks (P0-5: enforce daily/weekly/drawdown limits in backtest)
            if self._check_risk_halt():
                break  # Stop trading, close remaining positions

            # 2. Read pre-computed indicators (sliced to current bar)
            if self._precomputed_indicators:
                indicators = {
                    k: v[: i + 1] if isinstance(v, list) else v
                    for k, v in self._precomputed_indicators.items()
                    if k not in ("open",)
                }
            else:
                indicators = {}

            # 3. Generate signal from strategy
            bar_data = guard.get_slice(self.ohlcv_data)

            # If adapter has cursor, inject sliced multi-TF data
            if self._mtf_cursor and hasattr(self.strategy, "_set_mtf_cursor"):
                sliced = self._mtf_cursor.slice_as_of(current_time)
                self.strategy._set_mtf_cursor(sliced)

            signal = self.strategy.generate_signal(
                symbol=self._symbol,
                ohlcv_data=bar_data,
                indicators=indicators,
                regime=self._get_regime_state(),  # Phase 4: Wire regime detection
                current_time=current_time,
            )

            # Phase 4: Update regime detector with current bar return
            if self._regime_detector:
                prev_close = float(close[i - 1])
                if prev_close > 0:
                    bar_return = (float(bar_close) - prev_close) / prev_close
                    self._regime_detector.update(bar_return, i)

            # 4. Execute signal (fills on NEXT bar)
            if signal and signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                # Phase 4: Check regime-adjusted position sizing
                regime_mult = 1.0
                if self._regime_detector:
                    regime_mult = self._regime_detector.get_position_size_multiplier()
                self._execute_signal(signal, bar_open, bar_high, bar_low, bar_close, current_time, i, regime_mult)

            # 5. Update equity (Phase 4: use real-time P&L tracker)
            unrealized = self._calculate_unrealized_pnl(float(bar_close))
            if self._pnl_tracker:
                self._pnl_tracker.update_tick(Decimal(str(unrealized)), float(i))
                self.equity = self._pnl_tracker.equity
            else:
                self._update_equity(float(bar_close), current_time)

            # Phase 4: Check margin calls
            if self._margin_simulator and self.positions:
                pos_dicts = [
                    {
                        "symbol": p.symbol,
                        "entry_price": p.entry_price,
                        "quantity": p.quantity,
                        "side": "LONG" if p.side == PositionType.LONG else "SHORT",
                        "current_price": Decimal(str(bar_close)),
                    }
                    for p in self.positions.values()
                ]
                margin_events = self._margin_simulator.check_margin(
                    pos_dicts,
                    self.equity,
                    i,
                    current_prices={p.symbol: Decimal(str(bar_close)) for p in self.positions.values()},
                )
                for evt in margin_events:
                    if evt.event_type == "FORCED_LIQUIDATION" and evt.position_symbol:
                        # Close the position at forced liquidation price
                        for pid, pos in list(self.positions.items()):
                            if pos.symbol == evt.position_symbol:
                                exit_price, _pnl = self._margin_simulator.apply_forced_liquidation(
                                    {
                                        "entry_price": pos.entry_price,
                                        "quantity": pos.quantity,
                                        "side": "LONG" if pos.side == PositionType.LONG else "SHORT",
                                    },
                                    Decimal(str(bar_close)),
                                )
                                self._close_position(pid, exit_price, current_time, CloseReason.MANUAL, Decimal("0"))
                                break

        # Close any remaining positions at last price
        self._close_all_positions(close[-1], self.timestamps[-1] if self.timestamps else datetime.now(UTC))

        result = self._build_results()
        self._last_results = result
        return result

    @staticmethod
    def run_batch(configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Batch mode (C4): run multiple backtest configs sharing precomputed indicators.

        Args:
            configs: list of dicts, each with keys:
                'engine_cfg': BacktestConfig (or None for defaults)
                'strategy': Strategy instance
                'ohlcv_data': dict with OHLCV arrays
                'timestamps': list of datetimes (optional)
                'event_bus': EventBus (optional)

        Returns:
            List of result dicts (one per config).
        """
        # Precompute indicators once for identical data across batch items
        indicator_cache: dict[int, dict[str, Any]] = {}

        results = []
        for cfg in configs:
            engine_cfg = cfg.get("engine_cfg")
            strategy = cfg["strategy"]
            ohlcv_data = cfg["ohlcv_data"]
            timestamps = cfg.get("timestamps")
            event_bus = cfg.get("event_bus")

            # Cache key by data identity (id of close list + length)
            data_key = (id(ohlcv_data.get("close", [])), len(ohlcv_data.get("close", [])))
            if data_key not in indicator_cache:
                engine = BacktestEngine(config=engine_cfg)
                engine.set_strategy(strategy)
                engine.load_data(ohlcv_data, timestamps)
                # Compute full indicator set once
                indicator_cache[data_key] = engine._calculate_indicators(len(ohlcv_data["close"]) - 1)

            # Shared indicators
            shared_indicators = indicator_cache[data_key]

            # Create engine and run
            engine = BacktestEngine(config=engine_cfg)
            engine.set_strategy(strategy)
            engine.load_data(ohlcv_data, timestamps)
            engine._shared_indicators = shared_indicators
            result = engine.run(event_bus=event_bus)
            results.append(result)

        return results

    def get_overfitting_report(self) -> dict | None:
        """Return the last overfitting report from run(), or None if not yet run."""
        return getattr(self, "_last_results", None)

    def _reset(self) -> None:
        """Reset engine state for a new run"""
        self.balance = Decimal(str(self.config.initial_capital))
        self.equity = Decimal(str(self.config.initial_capital))
        self.peak_equity = Decimal(str(self.config.initial_capital))
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.current_index = 0
        self._daily_pnl = 0.0
        self._current_drawdown_pct = 0.0
        self._shared_indicators = None
        self._day_start_balance = Decimal(str(self.config.initial_capital))
        # P1 perf: pre-computed caches cleared each run
        self._precomputed_indicators: dict[str, Any] | None = None
        self._cached_bar_dicts: list[dict] | None = None
        self._risk_policy = None
        # Phase 4: Initialize regime, margin, P&L trackers
        if _PHASE4_WIRING_AVAILABLE:
            self._regime_detector = RegimeDetector()
            self._margin_simulator = MarginSimulator()
            self._pnl_tracker = RealTimePnLTracker(initial_equity=Decimal(str(self.config.initial_capital)))

    def _calculate_indicators(self, up_to_index: int) -> dict[str, Any]:
        """Calculate indicators using Numba JIT (B3) or pandas_ta fallback."""
        # B3 — If batch mode provided precomputed indicators, use them directly
        if getattr(self, "_shared_indicators", None) is not None:
            shared = self._shared_indicators
            return {
                k: v[: up_to_index + 1] if isinstance(v, list) else v for k, v in shared.items() if k not in ("open",)
            }

        # B3 — Numba hot path when strategy signals it
        use_numba = (
            _NUMBA_AVAILABLE and self.strategy is not None and getattr(self.strategy, "supports_numba", lambda: False)()
        )

        if use_numba:
            return self._calculate_indicators_numba(up_to_index)

        # Pure Python / pandas_ta path (original)
        return self._calculate_indicators_pandas(up_to_index)

    def _calculate_indicators_numba(self, up_to_index: int) -> dict[str, Any]:
        """Numba JIT indicator calculation (B3)."""
        try:
            close = np.array(self.ohlcv_data["close"][: up_to_index + 1], dtype=np.float64)
            high = np.array(
                self.ohlcv_data.get("high", self.ohlcv_data["close"])[: up_to_index + 1],
                dtype=np.float64,
            )
            low = np.array(
                self.ohlcv_data.get("low", self.ohlcv_data["close"])[: up_to_index + 1],
                dtype=np.float64,
            )
            volume = np.array(
                self.ohlcv_data.get("volume", [0] * len(close))[: up_to_index + 1],
                dtype=np.float64,
            )

            if len(close) < 200:
                return {}

            raw = _indicators_numba_impl(close, high, low, volume)
            # Convert numpy arrays to plain lists for downstream compat
            return {k: v.tolist() for k, v in raw.items()}
        except Exception:
            # Fallback: if numba fails at runtime, drop back to pandas_ta
            return self._calculate_indicators_pandas(up_to_index)

    def _calculate_indicators_pandas(self, up_to_index: int) -> dict[str, Any]:
        """Original pandas_ta indicator calculation (unchanged logic)."""
        try:
            import pandas as pd
            import pandas_ta as ta

            close = self.ohlcv_data["close"][: up_to_index + 1]
            high = self.ohlcv_data.get("high", close)[: up_to_index + 1]
            low = self.ohlcv_data.get("low", close)[: up_to_index + 1]
            volume = self.ohlcv_data.get("volume", [0] * len(close))[: up_to_index + 1]

            if len(close) < 200:
                return {}

            df = pd.DataFrame(
                {
                    "open": self.ohlcv_data.get("open", close)[: up_to_index + 1],
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )

            # EMAs
            df["ema_9"] = ta.ema(df["close"], length=9)
            df["ema_20"] = ta.ema(df["close"], length=20)
            df["ema_50"] = ta.ema(df["close"], length=50)
            df["ema_200"] = ta.ema(df["close"], length=200)

            # RSI and ATR
            df["rsi_14"] = ta.rsi(df["close"], length=14)
            df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

            # Bollinger Bands
            bb = ta.bbands(df["close"], length=20, std=2)
            if bb is not None and len(bb.columns) >= 3:
                df["bb_upper"] = bb.iloc[:, 2]  # Upper band
                df["bb_lower"] = bb.iloc[:, 0]  # Lower band
                df["bb_mid"] = bb.iloc[:, 1]  # Middle band

            # Volume
            df["volume_sma_20"] = df["volume"].rolling(window=20).mean()

            # ADX
            adx = ta.adx(df["high"], df["low"], df["close"], length=14)
            if adx is not None and len(adx.columns) >= 1:
                df["adx"] = adx.iloc[:, 0]

            return {col: df[col].tolist() for col in df.columns if col != "open"}

        except ImportError:
            return {}
        except Exception as e:
            import structlog

            structlog.get_logger(__name__).warning("backtest.indicator_error", error=str(e))
            return {}

    def _execute_signal(
        self,
        signal: Signal,
        bar_open: Decimal,
        bar_high: Decimal,
        bar_low: Decimal,
        bar_close: Decimal,
        current_time: datetime,
        bar_index: int,
        regime_mult: float = 1.0,
    ) -> None:
        """Execute a trading signal via ExecutionSimulator with next-bar fill."""
        if len(self.positions) >= self.config.max_positions:
            return

        for pos in self.positions.values():
            if pos.symbol == signal.symbol:
                return

        # CRITICAL: reject if no stop loss
        if not signal.stop_loss or signal.stop_loss <= 0:
            self._log_critical_incident("MISSING_SL", signal)
            return

        side = _exec_side(signal.signal_type)

        # Reject invalid SL direction
        entry_price = signal.entry_price or bar_close
        if signal.signal_type == SignalType.BUY and signal.stop_loss >= entry_price:
            self._log_critical_incident("INVALID_SL_DIRECTION", signal)
            return
        if signal.signal_type == SignalType.SELL and signal.stop_loss <= entry_price:
            self._log_critical_incident("INVALID_SL_DIRECTION", signal)
            return

        # Historical sizing — deterministic, no MT5
        entry_price = signal.entry_price or bar_close
        contract_spec = InlineContractSpec.for_symbol(signal.symbol)
        volume = _historical_size(
            equity=self.equity,
            risk_per_trade_bps=self.config.risk_per_trade_bps,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            contract=contract_spec,
        )
        if regime_mult != 1.0:
            volume = volume * Decimal(str(regime_mult))
        if volume <= 0:
            return

        pip_size = contract_spec.trade_tick_size  # 0.0001 for 4-decimal FX, 0.01 for JPY/gold

        # Build snapshot from current bar — dynamic spread based on time of day
        try:
            from backtest.dynamic_spread_model import SpreadConfig

            _spread_config = SpreadConfig()
            bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
            spread = pip_size * _spread_config.get_spread(bar_hour)
        except Exception:
            spread = pip_size * Decimal(str(self.config.spread_pips))

        # Add latency-based slippage from FillTimingConfig
        latency_slippage = Decimal("0")
        if self.config.fill_timing is not None:
            try:
                atr = float(bar_high - bar_low)
                latency_ms = self.config.fill_timing.estimate_latency_ms(atr)
                latency_slippage = self.config.fill_timing.estimate_slippage_pips(latency_ms)
                latency_slippage = pip_size * latency_slippage
            except Exception:
                latency_slippage = Decimal("0")

        # Phase 3: Square-root market impact (Almgren-Chriss)
        market_impact_bps = 0.0
        if _MARKET_IMPACT_AVAILABLE:
            try:
                daily_vol_pct = float(bar_high - bar_low) / float(bar_close) * 100 if bar_close > 0 else 1.0
                volume_lots = float(volume) / 100  # Convert units to lots
                market_impact_bps = estimate_market_impact_bps(
                    order_lots=volume_lots,
                    daily_vol_pct=daily_vol_pct,
                    adv_lots=1_000_000,  # Default for XAUUSD
                    eta=0.1,
                )
            except Exception:
                market_impact_bps = 0.0

        # Phase 3: Adverse selection for momentum entries
        adverse_selection_bps = 0.0
        if signal.signal_type == SignalType.BUY:
            # Momentum entry: buy at ask, adverse selection = half-spread
            adverse_selection_bps = float(spread) / float(bar_close) * 10000 * 0.5 if bar_close > 0 else 0.0
        elif signal.signal_type == SignalType.SELL:
            adverse_selection_bps = float(spread) / float(bar_close) * 10000 * 0.5 if bar_close > 0 else 0.0

        bid, ask = estimate_bid_ask_from_bar(bar_open, bar_high, bar_low, bar_close, spread)
        snapshot = MarketSnapshot(
            bid=bid,
            ask=ask,
            spread=spread,
            high=bar_high,
            low=bar_low,
            close=bar_close,
            timestamp=current_time,
            symbol=signal.symbol,
        )

        _spec_for_costs = InlineContractSpec.for_symbol(signal.symbol)
        contract_spec = ContractSpec(
            # tick_value/tick_size (not raw trade_contract_size) so non-USD-quote
            # pairs (USDJPY/USDCAD/USDCHF) get currency-converted cost math.
            contract_size=_spec_for_costs.trade_tick_value / _spec_for_costs.trade_tick_size,
            commission_per_lot=self.config.commission_per_lot,
            spread_points=spread,
        )

        intent = OrderIntent(
            symbol=signal.symbol,
            side=side,
            volume=volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy_id=self.strategy.id if self.strategy else "",
            signal_id=signal.id,
            execution_quality=ExecutionQuality.BAR_ONLY,
            latency_slippage=latency_slippage,
            market_impact_bps=market_impact_bps,
            adverse_selection_bps=adverse_selection_bps,
        )

        result = self._simulator.submit_intent(
            intent,
            snapshot,
            self._bar_dicts(),
            bar_index,
            contract_spec=contract_spec,
        )

        if result.entry_price <= 0 or volume <= 0:
            return

        pos_id = str(uuid4())[:8]
        pos_side = PositionType.LONG if side == FillSide.BUY else PositionType.SHORT

        fill_time = self.timestamps[bar_index + 1] if bar_index + 1 < len(self.timestamps) else current_time
        self.positions[pos_id] = BacktestPosition(
            id=pos_id,
            symbol=signal.symbol,
            side=pos_side,
            entry_price=result.entry_price,
            quantity=volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_time=fill_time,
            strategy_id=self.strategy.id if self.strategy else "",
            entry_spread_cost=result.spread_cost,
            entry_slippage_cost=result.slippage_cost,
            execution_quality=result.execution_quality.value,
            signal_bar_index=bar_index,
            contract_size=InlineContractSpec.for_symbol(signal.symbol).trade_contract_size,
            tick_size=InlineContractSpec.for_symbol(signal.symbol).trade_tick_size,
            tick_value=InlineContractSpec.for_symbol(signal.symbol).trade_tick_value,
        )
        self.balance -= result.commission

    def _check_exits(
        self,
        bar_high: Decimal,
        bar_low: Decimal,
        bar_close: Decimal,
        current_time: datetime,
        bar_index: int,
    ) -> None:
        """Check stop loss and take profit on all open positions using fill_model."""
        if not self.positions:
            return

        # Dynamic spread based on time of day — use first position's tick_size
        first_pos = next(iter(self.positions.values()), None)
        pip_size = first_pos.tick_size if first_pos else Decimal("0.01")
        try:
            from backtest.dynamic_spread_model import SpreadConfig

            _spread_config = SpreadConfig()
            bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
            spread = pip_size * _spread_config.get_spread(bar_hour)
        except Exception:
            spread = pip_size * Decimal(str(self.config.spread_pips))
        bid, ask = estimate_bid_ask_from_bar(Decimal("0"), bar_high, bar_low, bar_close, spread)
        snapshot = MarketSnapshot(
            bid=bid,
            ask=ask,
            spread=spread,
            high=bar_high,
            low=bar_low,
            close=bar_close,
            timestamp=current_time,
        )

        exec_positions = []
        pos_map = {}
        for pos_id, pos in self.positions.items():
            exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
            ep = ExecPosition(
                trade_id=pos_id,
                symbol=pos.symbol,
                side=exec_side,
                entry_price=pos.entry_price,
                volume=pos.quantity,
                stop_loss=pos.stop_loss or Decimal("0"),
                take_profit=pos.take_profit,
                strategy_id=pos.strategy_id,
                signal_bar_index=pos.signal_bar_index,
            )
            exec_positions.append(ep)
            pos_map[pos_id] = pos

        events = self._simulator.evaluate_open_positions(
            exec_positions,
            snapshot,
            bar_high,
            bar_low,
            current_bar_index=bar_index,
        )

        for event in events:
            pos_id = event.trade_id
            pos = pos_map.get(pos_id)
            if not pos:
                continue

            if event.event_type.value == "STOP_LOSS":
                reason = CloseReason.STOP_LOSS
            elif event.event_type.value == "TAKE_PROFIT":
                reason = CloseReason.TAKE_PROFIT
            elif event.event_type.value == "AMBIGUOUS":
                reason = CloseReason.AMBIGUOUS
            elif event.event_type.value == "TIME_STOP":
                reason = CloseReason.MANUAL
            else:
                continue

            if event.exit_price and event.exit_price > 0:
                exit_price = event.exit_price
                exit_slip = Decimal("0")
            else:
                try:
                    from backtest.dynamic_spread_model import SpreadConfig

                    _spread_config = SpreadConfig()
                    bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
                    atr = float(bar_high - bar_low)
                    exit_slippage = pos.tick_size * _spread_config.get_slippage(bar_hour, atr=atr)
                except Exception:
                    exit_slippage = Decimal(str(self.config.slippage_pips)) * pos.tick_size
                exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
                exit_price, exit_slip = fill_simulate_exit(exec_side, bid, ask, exit_slippage)

            self._close_position(pos_id, exit_price, current_time, reason, exit_slip)

    @staticmethod
    def _pnl_from_ticks(
        price_diff: Decimal,
        quantity: Decimal,
        tick_size: Decimal,
        tick_value: Decimal,
    ) -> Decimal:
        """Convert a price difference to PnL using tick_size/tick_value.

        This correctly handles JPY pairs where contract_size (100k) is in
        quote-currency units but PnL must be in account-currency (USD).
        For USDJPY: tick_size=0.01, tick_value=6.67 → 1 pip = $6.67/lot.
        """
        if tick_size <= 0:
            return Decimal("0")
        return (price_diff / tick_size) * tick_value * quantity

    def _close_position(
        self,
        pos_id: str,
        exit_price: Decimal,
        exit_time: datetime,
        reason: CloseReason,
        exit_slippage_cost: Decimal = Decimal("0"),
    ) -> None:
        """Close a position and record the trade with full execution quality info."""
        pos = self.positions.pop(pos_id, None)
        if not pos:
            return

        # Calculate P&L via tick_size/tick_value (correct for JPY pairs)
        tick_size = getattr(pos, "tick_size", Decimal("0.01"))
        tick_value = getattr(pos, "tick_value", Decimal("1.0"))
        if pos.side == PositionType.LONG:
            pnl = self._pnl_from_ticks(exit_price - pos.entry_price, pos.quantity, tick_size, tick_value)
        else:
            pnl = self._pnl_from_ticks(pos.entry_price - exit_price, pos.quantity, tick_size, tick_value)

        # Commission on exit — quantity is already in lots
        exit_commission = pos.quantity * Decimal(str(self.config.commission_per_lot))
        total_fees = exit_commission

        # Calculate swap cost — negative=cost, positive=credit
        swap_cost = self._calculate_swap_cost(
            symbol=pos.symbol,
            side=pos.side,
            quantity=pos.quantity,
            entry_time=pos.entry_time
            or self._deterministic_timestamp(pos.signal_bar_index if hasattr(pos, "signal_bar_index") else 0),
            exit_time=exit_time,
        )

        pnl -= total_fees
        pnl += swap_cost
        self.balance += pnl

        contract_size = getattr(pos, "contract_size", Decimal("100"))
        notional = pos.entry_price * pos.quantity * contract_size
        return_pct = (pnl / notional * 100) if notional > 0 else Decimal("0")

        is_ambiguous = reason == CloseReason.AMBIGUOUS

        self.trades.append(
            BacktestTrade(
                id=pos.id,
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                entry_time=pos.entry_time
                or self._deterministic_timestamp(pos.signal_bar_index if hasattr(pos, "signal_bar_index") else 0),
                exit_time=exit_time,
                pnl=pnl,
                return_pct=return_pct,
                fees=total_fees,
                close_reason=reason,
                strategy_id=pos.strategy_id,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                execution_quality=pos.execution_quality,
                entry_spread_cost=pos.entry_spread_cost,
                entry_slippage_cost=pos.entry_slippage_cost,
                exit_slippage_cost=exit_slippage_cost,
                swap_cost=swap_cost,
                ambiguous_bar=is_ambiguous,
            )
        )

    def _close_all_positions(self, last_price: float, current_time: datetime) -> None:
        """Close all remaining positions at last price with slippage."""
        last_dec = Decimal(str(last_price))
        for pos_id in list(self.positions.keys()):
            pos = self.positions.get(pos_id)
            if not pos:
                continue
            try:
                from backtest.dynamic_spread_model import SpreadConfig as _SpreadCfg

                _spread_config = _SpreadCfg()
                bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
                exit_slippage = pos.tick_size * _spread_config.get_slippage(bar_hour)
            except Exception:
                exit_slippage = Decimal(str(self.config.slippage_pips)) * pos.tick_size
            if pos.side == PositionType.LONG:
                # Selling: apply slippage (worse price)
                exit_price = last_dec - exit_slippage
            elif pos:
                # Buying to close short: apply slippage (worse price)
                exit_price = last_dec + exit_slippage
            else:
                exit_price = last_dec
            self._close_position(pos_id, exit_price, current_time, CloseReason.MANUAL, exit_slippage)

    def _calculate_swap_cost(
        self,
        symbol: str,
        side: PositionType,
        quantity: Decimal,
        entry_time: datetime,
        exit_time: datetime,
    ) -> Decimal:
        """
        Calculate swap cost for a position held across rollover.

        Uses the swap_cost module if available, otherwise returns 0.
        """
        if not _SWAP_COST_AVAILABLE or not self.config.enable_swap:
            return Decimal("0")

        try:
            # Get live swap rates (or use default XAUUSD rates)
            swap_rates = get_live_swap_rates(symbol)
            if not swap_rates:
                # Default XAUUSD swap rates for Pepperstone Razor
                swap_rates = {
                    "swap_long": -28.5,
                    "swap_short": 5.2,
                    "swap_mode": 0,
                    "swap_rollover3days": 3,  # Wednesday
                    "point": 0.01,
                    "contract_size": 100.0,
                    "currency_profit": "USD",
                }

            # Convert position side to string
            side_str = "BUY" if side == PositionType.LONG else "SELL"

            # quantity is already in lots (from _historical_size)
            lots = quantity

            # Get triple swap weekday
            triple_swap_weekday = swap_rates.get("swap_rollover3days", 3)

            # Calculate swap cost — preserves sign: negative=cost, positive=credit
            swap_cost = get_swap_cost_for_trade(
                entry_time=entry_time,
                exit_time=exit_time,
                side=side_str,
                lot=float(lots),
                swap_rates=swap_rates,
                triple_swap_weekday=triple_swap_weekday,
            )

            return Decimal(str(swap_cost))
        except Exception:
            # If swap calculation fails, return 0
            return Decimal("0")

    def _check_risk_halt(self) -> bool:
        """Check if any risk limit is breached. Returns True if trading should halt."""
        # P3 FIX: reuse hoisted policy instead of creating a new one per bar
        policy = self._risk_policy
        if policy is None:
            try:
                from ..risk.risk_policy import RiskPolicy
            except ImportError:
                from risk.risk_policy import RiskPolicy
            policy = RiskPolicy()

        # Max drawdown check
        if self.peak_equity > 0:
            dd = (self.peak_equity - self.equity) / self.peak_equity
            if dd >= policy.max_total_drawdown_fraction:
                return True

        # Daily loss check
        daily_loss = self.balance - self._day_start_balance
        if daily_loss < 0 and abs(daily_loss) / self._day_start_balance >= policy.max_daily_loss_fraction:
            return True

        return False

    def _log_critical_incident(self, incident_type: str, signal=None):
        """Log critical incident. No silent fallback."""
        import logging

        logging.critical(f"CRITICAL_INCIDENT: {incident_type} signal={signal}")

    def _deterministic_timestamp(self, bar_index: int) -> datetime:
        """Deterministic fallback timestamp based on bar index (no datetime.now)."""
        if self.timestamps:
            return self.timestamps[-1]
        return datetime(2000, 1, 1, tzinfo=UTC)

    def _get_regime_state(self) -> str | None:
        """Phase 4: Get current regime state string for strategy consumption."""
        if not self._regime_detector:
            return None
        state = self._regime_detector._current_state
        if hasattr(state, "vol_regime"):
            return state.vol_regime.value if hasattr(state.vol_regime, "value") else str(state.vol_regime)
        return None

    def _calculate_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L across all open positions."""
        unrealized = 0.0
        current = Decimal(str(current_price))
        for pos in self.positions.values():
            tick_size = getattr(pos, "tick_size", Decimal("0.01"))
            tick_value = getattr(pos, "tick_value", Decimal("1.0"))
            try:
                from backtest.dynamic_spread_model import SpreadConfig as _SpreadCfg

                _spread_config = _SpreadCfg()
                bar_hour = 12  # Default for equity calc
                closing_spread = tick_size * _spread_config.get_spread(bar_hour)
            except Exception:
                closing_spread = Decimal(str(self.config.spread_pips)) * tick_size
            closing_cost = closing_spread * Decimal("0.5")
            closing_slip = tick_size * Decimal(str(self.config.slippage_pips))
            if pos.side == PositionType.LONG:
                unrealized += float(
                    self._pnl_from_ticks(
                        current - closing_cost - closing_slip - pos.entry_price, pos.quantity, tick_size, tick_value
                    )
                )
            else:
                unrealized += float(
                    self._pnl_from_ticks(
                        pos.entry_price - current - closing_cost - closing_slip, pos.quantity, tick_size, tick_value
                    )
                )
        return unrealized

    def _bar_dicts(self) -> list[dict]:
        """Convert loaded OHLCV arrays to list-of-dicts for the simulator.

        P2 FIX: Cache the result so repeated calls (e.g. per-signal in the
        main loop) don't re-convert all bars with expensive Decimal()
        wrapping.  The cache is invalidated by _reset() each run.
        """
        cached = getattr(self, "_cached_bar_dicts", None)
        if cached is not None:
            return cached
        n = len(self.ohlcv_data["close"])
        bars = []
        for i in range(n):
            bars.append(
                {
                    "open": Decimal(str(self.ohlcv_data["open"][i])),
                    "high": Decimal(str(self.ohlcv_data["high"][i])),
                    "low": Decimal(str(self.ohlcv_data["low"][i])),
                    "close": Decimal(str(self.ohlcv_data["close"][i])),
                }
            )
        self._cached_bar_dicts = bars
        return bars

    def _update_equity(self, current_price: float, current_time: datetime) -> None:
        """Update equity curve point"""
        # Calculate unrealized P&L — use dynamic spread consistent with execution
        unrealized = Decimal("0")
        for pos in self.positions.values():
            current = Decimal(str(current_price))
            tick_size = getattr(pos, "tick_size", Decimal("0.01"))
            tick_value = getattr(pos, "tick_value", Decimal("1.0"))
            try:
                from backtest.dynamic_spread_model import SpreadConfig as _SpreadCfg

                _spread_config = _SpreadCfg()
                bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
                closing_spread = tick_size * _spread_config.get_spread(bar_hour)
            except Exception:
                closing_spread = Decimal(str(self.config.spread_pips)) * tick_size
            closing_cost = closing_spread * Decimal("0.5")  # half-spread to close
            closing_slip = tick_size * Decimal(str(self.config.slippage_pips))
            if pos.side == PositionType.LONG:
                # Close = sell at bid - slippage (worse than mid)
                unrealized += self._pnl_from_ticks(
                    current - closing_cost - closing_slip - pos.entry_price, pos.quantity, tick_size, tick_value
                )
            else:
                # Close = buy at ask + slippage (worse than mid)
                unrealized += self._pnl_from_ticks(
                    pos.entry_price - current - closing_cost - closing_slip, pos.quantity, tick_size, tick_value
                )

        self.equity = self.balance + unrealized

        # Update peak and drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        if self.peak_equity > 0:
            drawdown = (self.peak_equity - self.equity) / self.peak_equity * 100
            self._current_drawdown_pct = float(drawdown)

        self.equity_curve.append(
            EquityPoint(
                timestamp=current_time,
                equity=float(self.equity),
                balance=float(self.balance),
                drawdown_pct=self._current_drawdown_pct,
                open_positions=len(self.positions),
            )
        )

    def _build_results(self) -> dict[str, Any]:
        """Build final results dictionary"""
        from .metrics import calculate_metrics

        metrics = calculate_metrics(
            trades=self.trades,
            initial_capital=self.config.initial_capital,
            equity_curve=self.equity_curve,
        )

        # Execution quality breakdown
        total_spread_cost = sum(t.entry_spread_cost for t in self.trades)
        total_slippage_cost = sum(t.entry_slippage_cost + t.exit_slippage_cost for t in self.trades)
        quality_counts: dict[str, int] = {}
        for t in self.trades:
            q = t.execution_quality or "unknown"
            quality_counts[q] = quality_counts.get(q, 0) + 1

        result = {
            "config": {
                "initial_capital": float(self.config.initial_capital),
                "slippage_pips": self.config.slippage_pips,
                "commission_per_lot": float(self.config.commission_per_lot),
                "risk_per_trade_bps": self.config.risk_per_trade_bps,
                "strategy": self.strategy.id if self.strategy else "unknown",
            },
            "metrics": metrics,
            "trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "entry_price": float(t.entry_price),
                    "exit_price": float(t.exit_price),
                    "quantity": float(t.quantity),
                    "stop_loss": float(t.stop_loss) if t.stop_loss else None,
                    "take_profit": float(t.take_profit) if t.take_profit else None,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "pnl": float(t.pnl),
                    "return_pct": float(t.return_pct),
                    "fees": float(t.fees),
                    "close_reason": t.close_reason.value,
                    "strategy_id": t.strategy_id,
                    "execution_quality": t.execution_quality,
                    "entry_spread_cost": float(t.entry_spread_cost),
                    "entry_slippage_cost": float(t.entry_slippage_cost),
                    "exit_slippage_cost": float(t.exit_slippage_cost),
                    "ambiguous_bar": t.ambiguous_bar,
                }
                for t in self.trades
            ],
            "equity_curve": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "equity": p.equity,
                    "balance": p.balance,
                    "drawdown_pct": p.drawdown_pct,
                    "open_positions": p.open_positions,
                }
                for p in (
                    self.equity_curve
                    if len(self.equity_curve) <= 500
                    else self.equity_curve[:: max(1, len(self.equity_curve) // 500)]
                )
            ],
            "execution": {
                "total_spread_cost": float(total_spread_cost),
                "total_slippage_cost": float(total_slippage_cost),
                "quality_breakdown": quality_counts,
            },
        }

        # AUTO: Run overfitting detection if enough trades
        if len(self.trades) >= 10:
            try:
                from ..validation.overfitting_detector import OverfittingDetector

                # Extract bar-level returns from equity curve
                returns = []
                for i in range(1, len(self.equity_curve)):
                    prev_eq = self.equity_curve[i - 1].equity
                    curr_eq = self.equity_curve[i].equity
                    if prev_eq > 0:
                        returns.append((curr_eq - prev_eq) / prev_eq)

                detector = OverfittingDetector()
                overfit_report = detector.evaluate(
                    strategy_id=self.strategy.id if self.strategy else "unknown",
                    returns=returns,
                    n_trials=1,
                    n_observations=len(returns),
                    oos_returns_per_fold=[],
                    cost_pnl=float(sum(float(t.pnl) for t in self.trades)),
                    total_costs=float(sum(float(t.fees) for t in self.trades)),
                    param_values=[],
                    param_pnls=[],
                    data_length=len(self.equity_curve),
                    sharpe=metrics.sharpe_ratio if hasattr(metrics, "sharpe_ratio") else None,
                )

                result["overfitting"] = {
                    "score": overfit_report.score,
                    "recommendation": overfit_report.recommendation,
                    "blockers": overfit_report.blockers,
                    "warnings": overfit_report.warnings,
                }
            except Exception as e:
                result["overfitting"] = {"error": str(e), "score": 0, "recommendation": "UNKNOWN"}

        return result
