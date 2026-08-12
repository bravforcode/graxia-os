# Migration Guide: Pattern Integration v1

## Overview
Phase A introduces four patterns into quant_os: event-driven architecture, Numba JIT, multi-agent ensemble, and Arrow data format. This guide covers API changes, migration steps, and backward compatibility.

## Breaking Changes
**None.** All changes are additive. Existing strategies and backtest scripts continue to work without modification.

## New APIs

### 1. Event Bus (`core/event_bus.py`)
New import:
```python
from core.event_bus import EventBus
from core.events import BarEvent, SignalEvent, OrderEvent, FillEvent
```

Attach to backtest (optional):
```python
engine = BacktestEngine(config)
results = engine.run(event_bus=bus)  # new parameter
```

Without `event_bus`, behavior is identical to pre-Phase A.

### 2. Numba Support (`backtest/engine.py`)
Strategy opt-in:
```python
class MyStrategy(Strategy):
    def supports_numba(self) -> bool:
        return True  # enables JIT path
```

If Numba not installed, engine falls back automatically. No code change required.

### 3. Arrow Loader (`backtest/data_loader.py`)
New functions:
```python
from backtest.data_loader import load_arrow, to_arrow

# Load
df = load_arrow("data/XAUUSD_M15.feather")

# Export
to_arrow(df, "data/XAUUSD_M15.feather")
```

Requires `pyarrow` package. Clear error if missing.

### 4. Ensemble Strategy (`strategies/ensemble.py`)
New class:
```python
from strategies.ensemble import EnsembleStrategy, get_ensemble_signal

ensemble = EnsembleStrategy(
    mtm_strategy=mtm,
    mrb_strategy=mrb,
    mlb_strategy=mlb,
)
signal = ensemble.generate_signal(symbol, ohlcv_data, indicators, regime)
```

### 5. Multi-Agent Pipeline (`core/agents/`)
New classes:
```python
from core.agents import (
    TechnicalAnalystAgent,
    BullBearResearcherAgent,
    RiskAuditorAgent,
    PortfolioManagerAgent,
)
```

Connect via EventBus:
```python
bus = EventBus()
bus.subscribe(BarEvent, analyst.observe)
bus.subscribe(SignalEvent, researcher.observe)
bus.subscribe(SignalEvent, auditor.observe)
bus.subscribe(SignalEvent, manager.observe)
```

## Configuration Changes
New fields in `QuantConfig` (`core/config.py`):
```python
strategy_weights: dict = {"mtm": 0.40, "mrb": 0.25, "mlb": 0.35}
ensemble_confidence_threshold: float = 0.60
```

All have sensible defaults. No environment variable changes required.

## Data Migration
CSV files work unchanged. To benefit from Arrow speed:
```bash
python -c "
from backtest.data_loader import load_csv_data, to_arrow
df = load_csv_data('data/XAUUSD_M15.csv')
to_arrow(df, 'data/XAUUSD_M15.feather')
"
```

## Rollback
All new features are opt-in. To revert:
1. Remove `event_bus=bus` from `engine.run()` calls
2. Remove `supports_numba()` override from strategies
3. Use CSV loader instead of Arrow
4. Don't import from `core/agents/` or `strategies/ensemble.py`

## Testing
```bash
# Full regression
python -m pytest tests/ --tb=short -q

# Pattern-specific tests
python -m pytest tests/test_backtest_refactor_b1_b3_c4.py -q
python -m pytest tests/test_arrow_loader_c2.py -q
python -m pytest tests/test_strategy_helpers_a1.py -q
```
