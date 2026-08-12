# Jesse Patterns Analysis for quant_os Integration

## Executive Summary

Jesse implements a mature quant framework with **zero look-ahead bias by design**, dual Monte Carlo approaches (trade-shuffling + candle-based), a clean ML gather→train→deploy pipeline, and an extensible strategy base class. Key patterns worth adopting are marked below.

---

## 1. Zero Look-Ahead Bias Design

**Pattern**: Candle-by-candle simulation with strict temporal ordering.

**Key Implementation** (`jesse/modes/backtest_mode.py:648-728`):
```python
for i in range(length):
    # 1. Update time FIRST
    store_app.time = first_candles_set[i, 0] + 60_000

    # 2. Add candles, simulate price changes
    for candles_arr, candles_pipeline, exchange, symbol, arr_1m in candles_info:
        short_candle = candles_arr[i]
        _simulate_price_change_effect(short_candle, exchange, symbol)

    # 3. Generate higher timeframes ONLY after 1m candle processed
    for timeframe, count in generating_timeframes:
        if i_next % count == 0:
            generated_candle = generate_candle_from_one_minutes(...)
            add_candle(generated_candle, ...)

    # 4. Execute strategies AFTER all candles available
    for r, count, strategy, exchange, symbol in routes_info:
        if count == 1:
            strategy._execute()
        elif i_next % count == 0:
            strategy._execute()

    # 5. Execute pending market orders AFTER strategy decision
    execute_simulated_market_orders()
```

**Critical Pattern**: Higher-timeframe candles are generated **after** 1m candle is processed but **before** strategy execution. This ensures:
- HTF candles only contain data up to current minute
- No future data leaks into indicator calculations

**Adopt This**: Our backtester should follow this exact ordering. Most look-ahead bugs come from generating HTF candles before the 1m simulation step.

---

## 2. Monte Carlo Analysis

### 2a. Trade-Order Shuffling (`monte_carlo_trades.py`)

**Pattern**: Shuffle trade sequence, reconstruct equity curve.

```python
@ray.remote
def _ray_run_scenario_monte_carlo(original_trades, original_equity_curve, starting_balance, scenario_index, seed):
    shuffled_trades = original_trades.copy()
    random.shuffle(shuffled_trades)  # Only shuffle ORDER, not trade results
    equity_curve = _reconstruct_equity_curve_from_trades(shuffled_trades, original_equity_curve, starting_balance)
    result = _calculate_metrics_from_equity_curve(equity_curve, starting_balance)
    return result
```

**Key Insight**: Trades keep their individual P&L but order is randomized. This tests whether the strategy's edge is robust to sequence variation.

**Confidence Intervals**:
```python
percentiles = {
    '5th': np.percentile(values_array, 5),
    '50th': np.percentile(values_array, 50),
    '95th': np.percentile(values_array, 95)
}
p_value = np.sum(values_array >= original_value) / len(values_array)
is_significant_5pct = p_value < 0.05
```

### 2b. Candle-Based Shuffling (`monte_carlo_candles.py`)

**Pattern**: Regenerate synthetic candles via `CandlesPipeline`, re-run full backtest.

```python
@ray.remote
def _ray_run_scenario_monte_carlo_candles(config, routes, ..., scenario_index, candles_pipeline_class):
    result = backtest(
        config=config, routes=routes, candles=candles,
        candles_pipeline_class=candles_pipeline_class if scenario_index > 0 else None,
    )
    return result
```

**Pipeline Architecture** (`candle_pipelines/base_candles.py`):
```python
class BaseCandlesPipeline:
    def __init__(self, batch_size: int):
        self._batch_size = batch_size
        self._output = np.zeros((batch_size, 6))
        self.last_price = 0.0

    def get_candles(self, candles, index, candles_step=-1):
        index = index % self._batch_size
        if index == 0:
            # Regenerate batch
            self.process(candles, self._output[:len(candles)])
        return self._output[index]

    def process(self, original_1m_candles, out) -> bool:
        """Override in subclass. Return True if out is modified."""
        return False
```

**Concrete Pipeline** (`moving_block_bootstrap.py`):
```python
class MovingBlockBootstrapCandlesPipeline(BaseCandlesPipeline):
    def process(self, original_1m_candles, out):
        # Bootstrap blocks of (delta_close, delta_high, delta_low)
        deltas = np.column_stack([delta_close, delta_high, delta_low])
        boot_deltas = self._bootstrap_blocks(deltas, n)
        # Rebuild OHLC from bootstrapped deltas
        out[:, 2] = np.cumsum(boot_deltas[:, 0]) + self.last_price
        out[:, 3] = boot_close + boot_deltas[:, 1]  # high
        out[:, 4] = boot_close - boot_deltas[:, 2]  # low
        return True
```

**Adopt This**:
- Trade-shuffling is fast (no re-simulation) - good for quick confidence checks
- Candle-based is slower but tests structural robustness
- The `BaseCandlesPipeline` pattern is extensible - we can add our own shuffling strategies

---

## 3. ML Pipeline (Gather → Train → Deploy)

### 3a. Data Gathering (`Strategy.py:114-225`)

**Pattern**: Strategy records features + labels during backtest, exports to CSV.

```python
class Strategy(ABC):
    def record_features(self, features_dict: dict):
        """Record independent variables for ML training."""
        if self._current_ml_point is None:
            self._current_ml_point = {
                'time': int(self.current_candle[0] / 1000),
                'features': {},
                'label': None
            }
        self._current_ml_point['features'].update(features_dict)

    def record_label(self, name: str, value):
        """Record dependent variable (outcome)."""
        if self._current_ml_point is not None:
            self._current_ml_point['label'] = {'name': name, 'value': value}
            self._ml_data_points.append(self._current_ml_point)
            self._current_ml_point = None
```

### 3b. Training (`research/ml.py:141-388`)

**Pattern**: Chronological train/test split, not random.

```python
def train_model(data, estimator, task="binary", test_ratio=0.2):
    sorted_data = sorted(data, key=lambda p: p["time"])
    split = int(len(X) * (1.0 - test_ratio))
    X_train, X_test = X[:split], X[split:]  # Chronological!
    y_train, y_test = y[:split], y[split:]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)  # Don't fit on test!

    fitted = clone(estimator)
    fitted.fit(X_train_scaled, y_train)
```

### 3c. Deployment (`Strategy.py:257-342`)

**Pattern**: Single `ml_features()` method serves both gather and deploy modes.

```python
def ml_features(self) -> dict:
    """Define features once, use in both gather and deploy."""
    import jesse.indicators as ta
    return {
        "rsi_centered": (ta.rsi(self.candles) - 50) / 50,
        "atr_pct": ta.atr(self.candles) / self.price,
    }

def ml_predict(self) -> float:
    """Regression prediction - lazy loads model."""
    self._load_ml_artifacts()
    feats = self.ml_features()
    X = np.array([[feats[k] for k in sorted(feats.keys())]])
    return float(self._ml_model.predict(self._ml_scaler.transform(X))[0])
```

**Adopt This**:
- `ml_features()` as single source of truth is elegant
- Chronological split is essential for time series
- Feature scaling via `StandardScaler` is standard practice

---

## 4. Strategy Base Class Pattern

**Key Design** (`Strategy.py`):

```python
class Strategy(ABC):
    # ── Required Overrides ──────────────────────────────────────────────
    @abstractmethod
    def go_long(self) -> None: pass

    @abstractmethod
    def should_long(self) -> bool: pass

    # ── Optional Overrides ──────────────────────────────────────────────
    def should_short(self) -> bool: return False
    def go_short(self) -> None: pass
    def filters(self) -> list: return []
    def hyperparameters(self) -> list: return []
    def dna(self) -> str: return ''
    def update_position(self) -> None: pass
    def on_open_position(self, order) -> None: pass
    def on_close_position(self, order, closed_trade) -> None: pass

    # ── Lifecycle ───────────────────────────────────────────────────────
    def _execute(self) -> None:
        """Internal execution flow."""
        if self.position.is_close:
            if self.should_long():
                self._execute_long()
            elif self.should_short():
                self._execute_short()
        else:
            self._update_position()
```

**Key Insight**: The framework manages position lifecycle. Strategy only implements:
- `should_long/short` - entry signals
- `go_long/short` - set order parameters
- `update_position` - exit management

**Adopt This**: Separation of signal generation from order execution is clean. The framework handles all order validation, position tracking, and lifecycle events.

---

## 5. Multi-Timeframe / Multi-Symbol Support

**Pattern**: Routes define strategy-symbol-timeframe combinations.

```python
# Example route structure
routes = [
    {'exchange': 'BinancePerp', 'symbol': 'BTC-USDT', 'timeframe': '1h', 'strategy': 'MyStrategy'},
    {'exchange': 'BinancePerp', 'symbol': 'ETH-USDT', 'timeframe': '4h', 'strategy': 'MyStrategy'},
]
data_routes = [
    {'exchange': 'BinancePerp', 'symbol': 'BTC-USDT', 'timeframe': '1d'},  # Extra timeframe for indicators
]
```

**Candle Loading** (`backtest_mode.py:452-495`):
```python
def load_candles(start_date, finish_date):
    warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
    max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])

    for c in config['app']['considering_candles']:
        exchange, symbol = c[0], c[1]
        warmup_candles_arr, trading_candle_arr = candle_service.get_candles_from_db(
            exchange, symbol, max_timeframe, start_date, finish_date, warmup_num
        )
```

**Strategy Access to Multi-Timeframe Data**:
```python
def get_candles(self, exchange: str, symbol: str, timeframe: str) -> np.ndarray:
    """Access any candle data available in the store."""
    return candle_service.get_candles(exchange, symbol, timeframe)
```

**Adopt This**:
- Routes are the natural abstraction for multi-asset strategies
- Data routes separate "trading candles" from "indicator candles"
- Warmup candle handling is automatic

---

## 6. Fitness Function for Optimization

**Pattern** (`optimize_mode/fitness.py`):
```python
def get_fitness(config, routes, ..., training_candles, testing_candles, optimal_total):
    # Train on training period
    training_result = backtest(candles=training_candles, ...)
    training_metrics = training_result['metrics']

    # Test on out-of-sample period
    testing_result = backtest(candles=testing_candles, ...)
    testing_metrics = testing_result['metrics']

    # Combined fitness score
    score = calculate_fitness(training_metrics, testing_metrics, optimal_total)
    return score, training_metrics, testing_metrics
```

**Key Insight**: Always evaluate on separate train/test periods. The optimizer (Optuna) searches for hyperparameters that generalize.

---

## 7. Ray Parallelization Pattern

**Consistent Pattern** across Monte Carlo and optimization:

```python
# Initialize once
if not ray.is_initialized():
    ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)

# Put shared data in object store
trades_ref = ray.put(original_trades)

# Launch remote tasks
scenario_refs = []
for i in range(num_scenarios):
    ref = remote_function.remote(trades_ref, ...)
    scenario_refs.append(ref)

# Gather results
results = []
for ref in scenario_refs:
    results.append(ray.get(ref))

# Cleanup
if started_here and ray.is_initialized():
    ray.shutdown()
```

---

## Specific Code Snippets to Adopt

### 1. Jumped Candle Fix (`backtest_mode.py:907-928`)
```python
def _get_fixed_jumped_candle(previous_candle, candle):
    """Handle price gaps between candles."""
    previous_close = previous_candle[2]
    candle_open = candle[1]
    if previous_close < candle_open:
        candle[1] = previous_close
        if previous_close < candle[4]:
            candle[4] = previous_close
    elif previous_close > candle_open:
        candle[1] = previous_close
        if previous_close > candle[3]:
            candle[3] = previous_close
    return candle
```

### 2. Confidence Interval Calculation
```python
def _calculate_confidence_intervals(original_result, simulation_results):
    for metric_name, values in metrics.items():
        values_array = np.array(values)
        percentiles = {
            '5th': np.percentile(values_array, 5),
            '50th': np.percentile(values_array, 50),
            '95th': np.percentile(values_array, 95)
        }
        ci_95 = {
            'lower': np.percentile(values_array, 2.5),
            'upper': np.percentile(values_array, 97.5)
        }
        p_value = np.sum(values_array >= original_value) / len(values_array)
```

### 3. Feature Importance with RFE
```python
from sklearn.feature_selection import RFE, f_classif

def _compute_feature_importance(X_train, y_train, feature_names, estimator, task):
    # RFE ranking
    rfe = RFE(estimator, n_features_to_select=min(10, len(feature_names)))
    rfe.fit(X_train, y_train)
    rfe_ranks = {name: int(rank) for name, rank in zip(feature_names, rfe.ranking_)}

    # ANOVA F-values
    f_scores, p_values = f_classif(X_train, y_train)
    anova = {name: float(score) for name, score in zip(feature_names, f_scores)}

    return {'rfe_ranks': rfe_ranks, 'anova_f': anova}
```

---

## Integration Recommendations

| Pattern | Priority | Effort | Notes |
|---------|----------|--------|-------|
| Zero look-ahead ordering | **P0** | Medium | Must have correct simulation loop |
| Trade-shuffling MC | P1 | Low | Simple to implement, high value |
| Candle-based MC | P1 | Medium | Need BaseCandlesPipeline abstraction |
| ML gather→train→deploy | P2 | Medium | `ml_features()` pattern is clean |
| Strategy base class | P2 | High | Architectural decision |
| Ray parallelization | P2 | Low | Already using Ray? |
| Fitness function pattern | P2 | Low | Train/test split evaluation |
| Confidence intervals | P1 | Low | Statistical rigor |

---

## Key Differences from Our Approach

1. **Simulation Loop**: Jesse's minute-by-minute loop with HTF generation is more rigorous than batch processing
2. **ML Integration**: Jesse embeds ML in the strategy itself; we might prefer separate pipeline
3. **Candle Pipelines**: Jesse's `BaseCandlesPipeline` abstraction is powerful for Monte Carlo
4. **Optimization**: Optuna + Ray is production-ready; worth adopting
5. **No Overfit Testing**: Jesse doesn't have walk-forward analysis built-in (we should add)

---

*Generated from jesse repo analysis, June 2026*
