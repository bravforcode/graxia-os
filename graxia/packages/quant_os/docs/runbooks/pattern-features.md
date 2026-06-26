# Runbook: Pattern Features — Enable/Disable/Fallback

## Feature Flags

| Feature | Config | Default | Location |
|---------|--------|---------|----------|
| Event-driven backtest | `event_bus=` param | `None` (disabled) | `backtest/engine.py:372` |
| Numba JIT indicators | `supports_numba()` | `False` | `strategies/base.py:282` |
| Arrow data loader | `pyarrow` import | optional | `backtest/data_loader.py:249` |
| Ensemble strategy | manual instantiation | N/A | `strategies/ensemble.py:206` |
| Agent pipeline | manual wiring | N/A | `core/agents/` |

## Enable/Disable Procedures

### Event-Driven Backtest
**Enable:**
```python
from core.event_bus import EventBus
bus = EventBus()
results = engine.run(event_bus=bus)
```

**Disable:** Remove `event_bus=bus` from `engine.run()`.

**Fallback:** Engine runs in direct-call mode (pre-Phase A behavior).

### Numba JIT
**Enable:**
```python
class MyStrategy(Strategy):
    def supports_numba(self) -> bool:
        return True
```

**Disable:** Remove `supports_numba()` override (inherits `False`).

**Fallback:** Engine uses `_calculate_indicators_pandas()` automatically.

**Verify Numba available:**
```python
from backtest.engine import _NUMBA_AVAILABLE
print(f"Numba: {_NUMBA_AVAILABLE}")
```

### Arrow Data Loader
**Enable:** Install pyarrow:
```bash
pip install pyarrow
```

**Disable:** Uninstall pyarrow. All `load_arrow()` calls raise `ImportError` with clear message.

**Fallback:** Use `load_csv_data()` from same module:
```python
from backtest.data_loader import load_csv_data
df = load_csv_data("data/XAUUSD_M15.csv")
```

### Ensemble Strategy
**Enable:**
```python
from strategies.ensemble import EnsembleStrategy
ensemble = EnsembleStrategy(mtm_strategy=mtm, mrb_strategy=mrb, mlb_strategy=mlb)
```

**Disable:** Don't instantiate `EnsembleStrategy`. Use individual strategies directly.

**Fallback:** Use `get_ensemble_signal()` function directly with manual signal collection:
```python
from strategies.ensemble import get_ensemble_signal
decision, confidence, details = get_ensemble_signal(mtm_sig, mrb_sig, mlb_sig, regime)
```

### Agent Pipeline
**Enable:**
```python
from core.event_bus import EventBus
from core.agents import TechnicalAnalystAgent, BullBearResearcherAgent, RiskAuditorAgent, PortfolioManagerAgent

bus = EventBus()
analyst = TechnicalAnalystAgent()
researcher = BullBearResearcherAgent()
auditor = RiskAuditorAgent()
manager = PortfolioManagerAgent()

bus.subscribe(BarEvent, analyst.observe)
bus.subscribe(SignalEvent, researcher.observe)
bus.subscribe(SignalEvent, auditor.observe)
bus.subscribe(SignalEvent, manager.observe)
```

**Disable:** Don't wire agents to bus. Strategy `generate_signal()` still works independently.

**Fallback:** Each agent can be used standalone without EventBus.

## Troubleshooting

### "pyarrow is required" error
```bash
pip install pyarrow
```

### Numba compilation slow on first run
Expected. JIT compiles on first call (~2s). Subsequent calls are fast.

### Ensemble confidence always 0.60
Check sub-strategy signals. If all return `NO_TRADE`, ensemble returns `NO_TRADE`.

### Agent pipeline not emitting signals
Verify:
1. BarEvent published to bus (check `bus.published_count`)
2. Analyst receives BarEvents (check `analyst._closes` has data)
3. Researcher has >= 2 votes (check `MIN_VOTES = 2`)

### Backtest results different after Phase A
Event-driven and Numba paths produce numerically identical results to pre-Phase A. If different:
1. Check `supports_numba()` returns `False` (same path as before)
2. Check `event_bus=None` in `engine.run()`
3. Run `python -m pytest tests/test_backtest_refactor_b1_b3_c4.py` for parity check

## Emergency Rollback
```bash
git stash  # stash any local changes
git checkout HEAD~1  # revert to pre-Phase A commit
python -m pytest tests/ --tb=short -q  # verify
```
