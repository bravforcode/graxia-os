# VectorBT Pattern Analysis for QuantOS Integration

## Key Architectural Differences

### 1. Vectorized vs Event-Driven Backtesting

**VectorBT**: Pure NumPy array operations, no Python loops
```python
# VectorBT: Array-based signal generation
entries = fast_ma > slow_ma  # Boolean array, entire series at once
exits = fast_ma < slow_ma

# Portfolio simulation via vectorized engine
pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=10000)
```

**QuantOS**: Event-driven, row-by-row processing
```python
# Current approach: Per-bar loop
for i, bar in enumerate(data):
    signal = strategy.generate_signal(bar, indicators)
    engine._execute_signal(signal, bar['close'], bar['timestamp'])
```

**Adopt**: Vectorized signal generation for backtesting speed. Keep event-driven for live execution.

### 2. Parameter Sweep Methodology

**VectorBT**: Grid search via broadcasting
```python
# VectorBT: Automatic parameter broadcasting
fast = vbt.Parameter([5, 10, 15, 20])
slow = vbt.Parameter([20, 30, 40, 50])
entries, exits = vbt.MA.run_combs(close, fast, slow, r=2)

# Results: 16 combinations (4x4) computed in parallel
pf = vbt.Portfolio.from_signals(close, entries, exits)
pf.sharpe_ratio()  # Sharpe for all 16 combos
```

**QuantOS**: Manual optimization loop
```python
# Current: Walk-forward with manual iteration
for window in windows:
    for params in param_grid:
        strategy = create_strategy(params)
        result = engine.run(strategy, window.data)
```

**Adopt**: Use NumPy broadcasting for parameter grids. `vbt.Parameter` + `vbt.run_combs()` eliminates explicit loops.

### 3. Portfolio Analytics

**VectorBT**: Accessor-based metrics library
```python
# ReturnsAccessor: 30+ risk metrics
pf.returns.sharpe_ratio()
pf.returns.sortino_ratio()
pf.returns.max_drawdown()
pf.returns.calmar_ratio()
pf.returns.value_at_risk()
pf.returns.rolling_sharpe(window=252)

# Built-in comparison
pf.plot_cumulative(benchmark=benchmark_returns)
```

**QuantOS**: Basic metrics in BacktestEngine
```python
# Current: Limited metrics
results['total_return']
results['max_drawdown']
results['sharpe_ratio']  # Single value only
```

**Adopt**: Port ReturnsAccessor pattern. Rolling metrics are essential for regime detection.

### 4. Signal Generation Patterns

**VectorBT**: Factory pattern with composable signals
```python
# SignalFactory: Composable signal generation
from vectorbt.signals.factory import SignalFactory

class MySignals(SignalFactory):
    def logic(self, close, window):
        # Vectorized signal logic
        ma = close.rolling(window).mean()
        entries = close.crossed_above(ma)
        exits = close.crossed_below(ma)
        return entries, exits

# Run across parameter grid
signals = MySignals.run(close, window=vbt.Parameter([10, 20, 30]))
```

**QuantOS**: Monolithic strategy classes
```python
# Current: All logic in one class
class MTMStrategy(Strategy):
    def generate_signal(self, symbol, ohlcv_data, indicators):
        # 50+ lines of signal logic
        ...
```

**Adopt**: Decompose strategies into composable signal generators. Each signal type (trend, mean-reversion, momentum) should be independent.

### 5. Walk-Forward Optimization

**VectorBT**: Built-in splitter utilities
```python
# Rolling/expanding window splits
from vectorbt.generic.accessors import GenericAccessor

split = close.vbt.splitter(
    method="rolling",
    in_samplePeriods=100,
    out_of_sample_periods=20
)

# Apply strategy across splits
results = split.apply(lambda close: run_strategy(close))
```

**QuantOS**: Custom WalkForwardAnalyzer
```python
# Current: Manual window management
analyzer = WalkForwardAnalyzer(strategy_factory, is_ratio=0.7)
result = analyzer.analyze(data, timestamps, n_windows=5)
```

**Adopt**: Use splitter pattern for cleaner window management. Current implementation is solid but verbose.

## Specific Code Snippets to Adopt

### 1. ArrayWrapper for Data Normalization
```python
# vectorbt/base/array_wrapper.py
# Wraps any array-like with metadata (index, columns, freq)
wrapper = ArrayWrapper(index, columns, ndim=2)
wrapped = wrapper.wrap(raw_array)  # Preserves metadata through operations
```

**Integration**: Add to `data/models.py` for consistent data handling across pipeline.

### 2. Parameter Broadcasting
```python
# vectorbt/utils/params.py
from vectorbt.utils.params import create_param_combs

# Generate all combinations without explicit loops
params = create_param_combs({
    'fast': [5, 10, 15],
    'slow': [20, 30, 40],
    'type': ['sma', 'ema']
})
# Returns 18 combinations (3x3x2)
```

**Integration**: Replace manual `itertools.product` in optimization loops.

### 3. Record Arrays for Trade Storage
```python
# vectorbt/records/
# NumPy structured arrays for efficient trade/order storage
order_records = np.array([
    (timestamp, col_idx, size, price, fees),
    ...
], dtype=[
    ('id', 'i8'),
    ('col', 'i8'),
    ('size', 'f8'),
    ('price', 'f8'),
    ('fees', 'f8')
])
```

**Integration**: Replace `List[BacktestTrade]` with structured arrays for 10x+ memory efficiency.

### 4. Drawdown Analysis
```python
# vectorbt/generic/drawdowns.py
dd = pf.drawdowns
dd.max_drawdown_duration()  # Length of worst drawdown
dd.drawdown_end()  # When each drawdown ended
dd.records  # Structured array of all drawdown periods
```

**Integration**: Add to `risk/engine.py` for drawdown-based position sizing.

### 5. Rolling Metric Computation
```python
# vectorbt/returns/accessors.py
pf.returns.rolling_sharpe(window=252)
pf.returns.rolling_sortino(window=252)
pf.returns.rolling_max_drawdown(window=252)
pf.returns.rolling_beta(window=252)
```

**Integration**: Essential for dynamic regime detection in `core/regime_filter.py`.

## Integration Recommendations

### Priority 1: Immediate Wins (This Sprint)
1. **Add `vbt.Parameter` for optimization** - Replace manual loops in `run_backtest.py`
2. **Port ReturnsAccessor metrics** - Extend `backtest/metrics.py` with rolling metrics
3. **Structured record arrays** - Replace trade lists in `engine.py`

### Priority 2: Architecture (Next Sprint)
1. **Decompose strategies** - Split `strategies/base.py` into composable signal generators
2. **ArrayWrapper pattern** - Normalize data handling across `data/pipeline.py`
3. **Splitter for walk-forward** - Replace custom window logic in `walk_forward.py`

### Priority 3: Performance (Future)
1. **Numba JIT compilation** - VectorBT uses numba for critical paths
2. **Memory-mapped arrays** - For large datasets in `data/feed.py`
3. **Parallel parameter sweeps** - Leverage NumPy broadcasting + multiprocessing

## Key Takeaways

1. **Vectorized > Event-driven for backtesting** - 100-1000x speedup on historical data
2. **Composable signals > Monolithic strategies** - Easier to test, combine, and reuse
3. **Structured arrays > Python lists** - Memory efficiency for trade/order storage
4. **Rolling metrics > Static metrics** - Essential for regime-aware strategies
5. **Parameter broadcasting > Manual loops** - Cleaner optimization code

## Files to Study Further

- `vectorbt/signals/factory.py` - Signal composition pattern
- `vectorbt/returns/accessors.py` - Metrics library
- `vectorbt/generic/splitters.py` - Walk-forward utilities
- `vectorbt/base/array_wrapper.py` - Data normalization
