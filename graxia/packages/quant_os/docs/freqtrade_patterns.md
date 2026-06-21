# Freqtrade Pattern Analysis for Quant OS Integration

## Executive Summary

Freqtrade is a mature, crypto-focused trading bot with battle-tested patterns. Key differences from Quant OS:
- **Freqtrade**: Exchange-centric (Binance, Kraken), single-asset-class, real money execution
- **Quant OS**: Multi-asset (forex + crypto), regime-aware, ensemble strategy model

The patterns below are actionable recommendations, not wholesale adoption.

---

## 1. Strategy Pattern (IStrategy Interface)

### Freqtrade's Architecture

```python
# freqtrade/strategy/interface.py:51
class IStrategy(ABC, HyperStrategyMixin):
    INTERFACE_VERSION: int = 3
    
    # Core methods (user implements):
    @abstractmethod
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add TA indicators to dataframe"""
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set entry signals (enter_long, enter_short columns)"""
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set exit signals (exit_long, exit_short columns)"""
    
    # Lifecycle hooks:
    def bot_start(self) -> None: ...
    def bot_loop_start(self, current_time: datetime) -> None: ...
    def confirm_trade_entry(self, pair, order_type, amount, rate, ...) -> bool: ...
    def confirm_trade_exit(self, pair, trade, ...) -> bool: ...
    
    # Risk management:
    minimal_roi: dict = {}
    stoploss: float
    trailing_stop: bool = False
    use_custom_stoploss: bool = False
```

### Quant OS Current Architecture

```python
# strategies/base.py:109
class Strategy(ABC):
    @abstractmethod
    def generate_signal(
        self, symbol: str, ohlcv_data: Dict[str, List],
        indicators: Optional[Dict] = None, regime: Optional[RegimeType] = None
    ) -> Optional[Signal]: ...
    
    @abstractmethod
    def required_features(self) -> List[str]: ...
    
    def is_valid_for_regime(self, regime: RegimeType) -> bool: ...
    def calculate_position_size(self, account_balance, entry_price, stop_loss) -> Decimal: ...
```

### Key Differences

| Aspect | Freqtrade | Quant OS |
|--------|-----------|----------|
| Signal generation | Mutate DataFrame columns | Return Signal dataclass |
| Position sizing | Delegated to Wallets | Built into Strategy base |
| ROI/Trailing | Class-level attributes | Not implemented |
| Lifecycle hooks | `bot_start`, `confirm_trade_entry`, `confirm_trade_exit` | None |
| Short support | Native (`can_short: bool`) | Signal-based (BUY/SELL) |
| Parameter optimization | Declarative (IntParameter, RealParameter) | None |

### Patterns to Adopt

**1. Lifecycle Hooks (High Value)**
```python
# Add to Strategy base class:
def bot_start(self) -> None:
    """Called once after initialization"""
    pass

def bot_loop_start(self, current_time: datetime) -> None:
    """Called at start of each iteration"""
    pass

def confirm_trade_entry(self, symbol, signal, amount, price) -> bool:
    """Final gate before execution. Return False to cancel."""
    return True

def confirm_trade_exit(self, symbol, trade, exit_reason) -> bool:
    """Final gate before exit. Return False to cancel."""
    return True
```

**Why**: These enable strategy-level risk gates without modifying the execution engine. Critical for: news blackout detection, correlation checks, drawdown circuit breakers.

**2. Declarative ROI/Trailing (Medium Value)**
```python
# Add to StrategyConfig:
@dataclass
class StrategyConfig:
    # ... existing fields ...
    
    # Take profit
    minimal_roi: Dict[float, float] = field(default_factory=lambda: {0: 0.10})
    # {minutes: min_roi} — e.g., {0: 0.10, 30: 0.05, 60: 0.02, 120: 0}
    
    # Trailing stop
    trailing_stop: bool = False
    trailing_stop_positive: float = 0.02
    trailing_stop_positive_offset: float = 0.03
    trailing_only_offset_is_reached: bool = True
```

**Why**: Declarative parameters are easier to optimize than imperative logic. Freqtrade's approach lets hyperopt tune these without strategy code changes.

**3. DataFrame Mutation for Indicators (Low Priority)**

Freqtrade mutates DataFrames in `populate_indicators`. Quant OS's `required_features()` + pre-calculated indicators is cleaner. Keep your approach.

---

## 2. Hyperopt Parameter Optimization

### Freqtrade's Architecture

```python
# strategy/parameters.py:30
class BaseParameter(ABC):
    space: str | None  # 'buy', 'sell', or custom
    default: Any
    value: Any
    in_space: bool = False  # True when optimizing
    
    def get_space(self, name: str) -> Union["Integer", "Real", "SKDecimal", "Categorical"]:
        """Convert to optuna distribution"""

# Concrete types:
IntParameter(low=5, high=20, default=14, space='buy')
RealParameter(low=0.1, high=0.5, default=0.3, space='sell')
DecimalParameter(low=0.01, high=0.1, default=0.03, decimals=3, space='buy')
CategoricalParameter(categories=['ema', 'sma', 'wma'], default='ema', space='buy')
BooleanParameter(default=True, space='sell')
```

### The Key Pattern: Dual-Mode Parameters

```python
# parameters.py:83
def can_optimize(self):
    return (
        self.in_space
        and self.optimize
        and HyperoptStateContainer.state != HyperoptState.OPTIMIZE
    )

@property
def range(self):
    """Returns full range in hyperopt mode, single value otherwise"""
    if self.can_optimize():
        return range(self.low, self.high + 1)
    else:
        return range(self.value, self.value + 1)
```

**This is the key insight**: Parameters behave as fixed values during normal operation but expand to full ranges during hyperopt. No code changes needed to switch modes.

### Loss Functions (Pluggable)

```python
# optimize/hyperopt_loss/hyperopt_loss_interface.py
class IHyperOptLoss(ABC):
    @staticmethod
    @abstractmethod
    def hyperopt_loss_function(
        *, results: DataFrame, trade_count: int,
        min_date: datetime, max_date: datetime,
        config: Config, processed: dict,
        backtest_stats: dict, starting_balance: float, **kwargs
    ) -> float:
        """Returns smaller number for better results"""
```

Available losses: Sharpe, Sortino, Calmar, MaxDrawdown, ProfitDrawdown, ShortTradeDur, MultiMetric.

### Patterns to Adopt

**1. Declarative Hyperoptable Parameters (High Value)**

```python
# Add to quant_os strategies:
from dataclasses import dataclass, field

@dataclass
class HyperParam:
    """A parameter that can be optimized by hyperopt"""
    value: float
    low: float
    high: float
    space: str = "buy"
    optimize: bool = True
    
    @property
    def range(self):
        """Full range during optimization, single value otherwise"""
        if self._in_optimization and self.optimize:
            return (self.low, self.high)
        return (self.value, self.value)

# Usage in strategy:
class MTMStrategy(Strategy):
    ema_fast: HyperParam = HyperParam(value=9, low=5, high=20, space="buy")
    ema_slow: HyperParam = HyperParam(value=21, low=15, high=50, space="buy")
    rsi_threshold: HyperParam = HyperParam(value=70, low=60, high=80, space="sell")
```

**Why**: Zero-cost abstraction. Normal operation uses fixed values. Optimization mode uses full ranges. No separate config files needed.

**2. Pluggable Loss Functions (Medium Value)**

```python
# Add to quant_os risk/engine.py or new hyperopt/ module:
class HyperOptLoss(ABC):
    @staticmethod
    @abstractmethod
    def calculate(results: BacktestResults, **kwargs) -> float:
        """Lower is better"""

class SharpeLoss(HyperOptLoss):
    @staticmethod
    def calculate(results, **kwargs):
        return -results.sharpe_ratio  # Negate because lower=better

class CalmarLoss(HyperOptLoss):
    @staticmethod
    def calculate(results, **kwargs):
        return -results.calmar_ratio
```

**Why**: Different market regimes need different objectives. Trend-following wants Sharpe. Mean-reversion wants Sortino. Let users choose.

**3. Optuna Integration Pattern**

```python
# From hyperopt_optimizer.py:55
optuna_samplers_dict = {
    "TPESampler": optuna.samplers.TPESampler,
    "GPSampler": optuna.samplers.GPSampler,
    "CmaEsSampler": optuna.samplers.CmaEsSampler,
    "NSGAIISampler": optuna.samplers.NSGAIISampler,
}

# Initial exploration points
INITIAL_POINTS = 30
```

**Why**: TPE (Tree-structured Parzen Estimator) is the default and works well for most cases. GPSampler for larger spaces. NSGA-II for multi-objective.

---

## 3. Walk-Forward Optimization

### Freqtrade's Approach

Freqtrade implements this via `RecursiveAnalysis` and `LookaheadAnalysis` (not a full walk-forward engine). It focuses on **bias detection**:

```python
# optimize/analysis/recursive.py:28
class RecursiveAnalysis(BaseAnalysis):
    """Checks for recursive bias in indicators"""
    
    def analyze_indicators(self):
        """Compare indicators across different startup_candle counts"""
        base_last_row = self.full_varHolder.indicators[pair_to_check].iloc[-1]
        for part in self.partial_varHolder_array:
            compare_df = base_last_row.compare(part_last_row)
            # Report differences as recursive bias
```

### Quant OS Current Approach

```python
# backtest/walk_forward.py:70
class WalkForwardAnalyzer:
    def __init__(self, strategy_factory, config, is_ratio=0.7, 
                 min_windows=3, mode="rolling"): ...
    
    def analyze(self, data, timestamps, n_windows=5, optimize_func=None) -> WalkForwardResult:
        """Full walk-forward with IS/OOS split"""
```

### Comparison

| Feature | Freqtrade | Quant OS |
|---------|-----------|----------|
| Walk-forward windows | Manual (startup_candle tests) | Automatic (rolling/anchored) |
| Bias detection | Recursive + Lookahead | Not implemented |
| IS/OOS ratio | Not standardized | Configurable (default 70/30) |
| Overfitting score | Not calculated | `overfitting_score` metric |

### Patterns to Adopt

**1. Recursive/Lookahead Bias Detection (High Value)**

```python
# Add to quant_os/backtest/metrics.py or new bias_detector.py:
class BiasDetector:
    def check_recursive_bias(self, strategy, data, candle_counts=[199, 399, 499, 999]):
        """Compare indicator values across different warmup periods"""
        results = {}
        for count in candle_counts:
            indicators = strategy.populate_indicators(data, startup_candles=count)
            results[count] = indicators.iloc[-1]
        
        # Flag indicators that change with warmup length
        biases = {}
        for col in results[candle_counts[0]].index:
            values = [r[col] for r in results.values()]
            if any(v != values[0] for v in values):
                biases[col] = "RECURSIVE"
        return biases
    
    def check_lookahead_bias(self, strategy, data, compare_date):
        """Check if indicators use future data"""
        full_run = strategy.populate_indicators(data)
        truncated = strategy.populate_indicators(data[data.index <= compare_date])
        
        full_val = full_run[full_run["date"] == compare_date].iloc[-1]
        trunc_val = truncated.iloc[-1]
        
        diffs = full_val.compare(trunc_val)
        return diffs  # Non-empty = lookahead detected
```

**Why**: Recursive bias is a real problem with indicators like EMA that use warmup data. Lookahead bias is silent but devastating to backtest validity.

**2. Overfitting Score (Medium Value)**

Quant OS already has `overfitting_score` in `WalkForwardResult`. Enhance with:

```python
def calculate_overfitting_score(windows: List[WalkForwardWindow]) -> float:
    """0 = no overfit, 1 = severe overfit"""
    if not windows:
        return 0.0
    
    # Degradation metric: how much worse OOS is vs IS
    degradations = [w.is_degradation for w in windows if w.is_degradation is not None]
    avg_degradation = sum(degradations) / len(degradations) if degradations else 0
    
    # Consistency metric: % of OOS windows that are profitable
    profitable = sum(1 for w in windows if w.oos_metrics and w.oos_metrics.total_pnl > 0)
    consistency = profitable / len(windows) if windows else 0
    
    # Combined score (higher degradation + lower consistency = more overfit)
    return min(1.0, avg_degradation * 0.6 + (1 - consistency) * 0.4)
```

---

## 4. Pairlist Dynamic Selection

### Freqtrade's Architecture

Freqtrade uses a **pipeline pattern** with composable pairlist handlers:

```python
# plugins/pairlistmanager.py:26
class PairListManager:
    def __init__(self, exchange, config, dataprovider):
        self._pairlist_handlers: list[IPairList] = []
        for handler_config in config.get("pairlists", []):
            handler = PairListResolver.load_pairlist(
                handler_config["method"], exchange=exchange,
                pairlistmanager=self, config=config,
                pairlistconfig=handler_config
            )
            self._pairlist_handlers.append(handler)

# plugins/pairlist/IPairList.py:72
class IPairList(ABC):
    is_pairlist_generator = False  # True = generates pairs, False = filters
    supports_backtesting = SupportsBacktesting.NO  # YES, NO, NO_ACTION, BIASED
    
    @abstractmethod
    def filter_pairlist(self, pairlist: list[str], tickers: Tickers) -> list[str]:
        """Filter or sort the pairlist"""
```

### Available Handlers (22 filters)

| Type | Handler | Backtest Safe? |
|------|---------|----------------|
| Generator | VolumePairList | NO (uses current data) |
| Generator | RemotePairList | NO |
| Generator | MarketCapPairList | NO |
| Filter | AgeFilter | NO |
| Filter | PriceFilter | NO_ACTION |
| Filter | SpreadFilter | NO_ACTION |
| Filter | VolatilityFilter | NO_ACTION |
| Filter | RangeStabilityFilter | NO_ACTION |
| Filter | PerformanceFilter | NO_ACTION |
| Filter | PrecisionFilter | NO_ACTION |
| Filter | FullTradesFilter | NO_ACTION |
| Filter | DelistFilter | NO_ACTION |
| Filter | ShuffleFilter | NO_ACTION |
| Filter | OffsetFilter | NO_ACTION |
| Filter | PercentChangePairList | NO |
| Filter | PairInformationFilter | NO |
| Filter | CrossMarketPairList | NO_ACTION |

### Pattern: SupportsBacktesting Enum

```python
class SupportsBacktesting(StrEnum):
    YES = "yes"        # Works correctly in backtest
    NO = "no"          # Will cause errors
    NO_ACTION = "no_action"  # Runs but does nothing (no bias)
    BIASED = "biased"  # Runs but introduces lookahead bias
```

**Why**: Critical for backtest integrity. Using volume-based pair selection in backtests silently creates survivorship bias.

### Patterns to Adopt

**1. Pipeline Pattern for Pair Filtering (High Value)**

```python
# Add to quant_os/data/pair_filter.py or similar:
from abc import ABC, abstractmethod
from enum import StrEnum

class BacktestSupport(StrEnum):
    SAFE = "safe"
    BIASED = "biased"
    UNSUPPORTED = "unsupported"

class PairFilter(ABC):
    backtest_support: BacktestSupport = BacktestSupport.UNSUPPORTED
    
    @abstractmethod
    def filter(self, pairs: list[str], context: dict) -> list[str]:
        """Filter and return allowed pairs"""

class MinVolumeFilter(PairFilter):
    backtest_support = BacktestSupport.SAFE  # Historical volume is fine
    
    def __init__(self, min_volume_24h: float = 1_000_000):
        self.min_volume = min_volume_24h
    
    def filter(self, pairs, context):
        tickers = context.get("tickers", {})
        return [p for p in pairs 
                if tickers.get(p, {}).get("quoteVolume", 0) >= self.min_volume]

class AgeFilter(PairFilter):
    backtest_support = BacktestSupport.UNSUPPORTED  # Uses current exchange data
    
    def __init__(self, min_days: int = 30):
        self.min_days = min_days
    
    def filter(self, pairs, context):
        exchange = context.get("exchange")
        return [p for p in pairs 
                if exchange.pair_age(p) >= self.min_days]

# Pipeline composition:
class PairFilterPipeline:
    def __init__(self, filters: list[PairFilter]):
        self.filters = filters
    
    def apply(self, pairs: list[str], context: dict) -> list[str]:
        for f in self.filters:
            pairs = f.filter(pairs, context)
        return pairs
```

**Why**: Composable filters are easier to test and configure than monolithic pair selection logic.

**2. Backtest Safety Warnings (Medium Value)**

```python
# Add to backtest engine initialization:
def validate_pairlist_for_backtest(pipeline: PairFilterPipeline):
    """Warn about biased or unsupported pairlist filters"""
    warnings = []
    for f in pipeline.filters:
        if f.backtest_support == BacktestSupport.UNSUPPORTED:
            warnings.append(f"{f.__class__.__name__} is not supported in backtesting")
        elif f.backtest_support == BacktestSupport.BIASED:
            warnings.append(f"{f.__class__.__name__} introduces lookahead bias")
    
    if warnings:
        logger.warning("Pairlist backtest warnings:\n" + "\n".join(warnings))
```

---

## 5. Edge / Position Sizing

### Freqtrade's Approach

Freqtrade does **not** have an Edge module in the current version. Position sizing is handled by:

```python
# wallets.py:36
class Wallets:
    def get_free(self, currency: str) -> float: ...
    def get_used(self, currency: str) -> float: ...
    def get_total(self, currency: str) -> float: ...
    def get_collateral(self) -> float: ...  # For futures margin
    
    def _update_dry(self):
        """Calculate balances from trade history"""
        tot_profit = Trade.get_total_closed_profit()
        tot_in_trades = sum(trade.stake_amount for trade in open_trades)
        current_stake = start_cap + tot_profit - tot_in_trades
```

Position sizing is **strategy-defined** via `stake_amount` in config.

### Quant OS Current Approach

```python
# risk/position_sizer.py
class PositionSizer(ABC):
    def calculate(self, account_balance, entry_price, stop_loss, symbol, **kwargs) -> PositionSizeResult:
        """Calculate position size"""
        pass

# Concrete implementations:
class FixedFractionalSizer(PositionSizer): ...  # 1% risk per trade
class KellyCriterionSizer(PositionSizer): ...  # Optimal growth
class ATRBasedSizer(PositionSizer): ...  # Volatility-adjusted
class AntiMartingaleSizer(PositionSizer): ...  # Reduce after losses
```

### Comparison

| Feature | Freqtrade | Quant OS |
|---------|-----------|----------|
| Position sizing | Config-based (stake_amount) | Pluggable sizers |
| Wallet tracking | Real-time balance updates | Not implemented |
| Leverage support | Native (cross/isolated margin) | Not implemented |
| Liquidation awareness | Yes | No |

### Patterns to Adopt

**1. Real-Time Wallet Tracking (Medium Value)**

```python
# Add to quant_os/risk/engine.py or wallet.py:
@dataclass
class Wallet:
    currency: str
    free: float = 0
    used: float = 0
    total: float = 0

class WalletTracker:
    def __init__(self, start_balance: Decimal):
        self._wallets: Dict[str, Wallet] = {}
        self._start_balance = start_balance
    
    def update(self, open_trades: List, closed_pnl: Decimal):
        """Recalculate from trade state"""
        tot_in_trades = sum(t.stake_amount for t in open_trades)
        current = self._start_balance + closed_pnl - tot_in_trades
        
        self._wallets["USD"] = Wallet(
            currency="USD",
            free=float(current),
            used=float(tot_in_trades),
            float=self._start_balance + closed_pnl
        )
    
    def get_free(self, currency: str) -> float:
        return self._wallets.get(currency, Wallet(currency)).free
    
    def get_available_for_trade(self, risk_pct: float) -> float:
        """Max stake considering risk limits"""
        return self.get_free("USD") * risk_pct
```

**Why**: Critical for position sizing. You need to know actual available capital, not just the starting balance.

**2. Leverage Awareness (Low Priority)**

Freqtrade's `PositionWallet` tracks leverage and collateral:

```python
class PositionWallet(NamedTuple):
    symbol: str
    position: float = 0
    leverage: float | None = 0
    collateral: float = 0
    side: str = "long"
```

Only relevant if you add futures/margin trading. Skip for now if spot-only.

---

## 6. Bonus: Informational Decorator Pattern

### Freqtrade's @informative Decorator

```python
# strategy/informative_decorator.py
@informative("1h")
def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    """Automatically fetches 1h data and merges with 5m data"""
    dataframe["ema_20_1h"] = ta.EMA(dataframe, timeperiod=20)
    return dataframe
```

The decorator:
1. Automatically fetches the specified timeframe
2. Merges it with the base timeframe
3. Suffixes column names (e.g., `ema_20_1h`)

**Why This Is Elegant**: Strategy authors don't need to handle data fetching or column naming. Just declare what timeframes you need.

### Potential for Quant OS

```python
# Hypothetical addition to strategies/base.py:
def informative(timeframe: str):
    """Decorator that auto-fetches and merges higher timeframe data"""
    def decorator(func):
        def wrapper(self, data, **kwargs):
            # Fetch higher timeframe data
            htf_data = self.data_provider.get_ohlcv(data["symbol"], timeframe)
            # Merge with suffix
            merged = merge_timeframes(data, htf_data, suffix=f"_{timeframe}")
            # Call strategy function
            return func(self, merged, **kwargs)
        return wrapper
    return decorator
```

---

## Summary: Priority Matrix

| Pattern | Value | Effort | Priority |
|---------|-------|--------|----------|
| Lifecycle hooks (bot_start, confirm_trade) | High | Low | **P0** |
| Declarative hyperoptable parameters | High | Medium | **P0** |
| Pipeline pair filters | High | Medium | **P0** |
| Recursive/lookahead bias detection | High | Medium | **P0** |
| Pluggable loss functions | Medium | Low | P1 |
| Real-time wallet tracking | Medium | Low | P1 |
| Backtest safety warnings | Medium | Low | P1 |
| Declarative ROI/trailing | Medium | Low | P2 |
| Overfitting score enhancement | Medium | Low | P2 |
| Informational decorator | Low | Medium | P3 |
| Leverage awareness | Low | High | P3 |

---

## Quick Wins (< 1 day each)

1. **Lifecycle hooks**: Add `bot_start`, `confirm_trade_entry`, `confirm_trade_exit` to Strategy base
2. **Backtest warnings**: Add `BacktestSupport` enum and validation in backtest init
3. **Wallet tracker**: Simple `Wallet` dataclass + `WalletTracker.update()` from open trades

---

*Generated from Freqtrade v3.x codebase analysis — 2026-06-20*
