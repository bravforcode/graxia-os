# ADR-004: Numba JIT Hot Path for Indicators

## Status
Accepted — Phase A (Week 1-2)

## Context
The backtest engine recalculates indicators (EMA, RSI, ATR) on every bar using pandas_ta. For strategies with 200k+ bars this becomes the bottleneck. Numba's `@njit` can compile pure-numpy indicator loops to machine code, giving 10-50x speedup on the hot path.

## Decision
Add Numba JIT indicator calculation as an opt-in path in `backtest/engine.py`:

1. Three JIT-compiled indicator functions: `_ema_numba()`, `_rsi_numba()`, `_atr_numba()`
2. Batch function `_indicators_numba_impl()` computes all indicators in one pass
3. Strategy opts in via `supports_numba() -> bool` flag on the base class
4. Graceful fallback: if Numba is unavailable or crashes, engine falls back to pandas_ta

Key code path:
```python
# backtest/engine.py:547-558
def _calculate_indicators(self, up_to_index: int) -> Dict[str, Any]:
    use_numba = (
        _NUMBA_AVAILABLE
        and self.strategy is not None
        and getattr(self.strategy, "supports_numba", lambda: False)()
    )
    if use_numba:
        return self._calculate_indicators_numba(up_to_index)
    return self._calculate_indicators_pandas(up_to_index)
```

## Consequences
+ 10-50x faster indicator calculation on large datasets
+ Zero cost when Numba not installed (graceful `@njit` stub at module level)
+ Strategy explicitly opts in — no implicit behavior change
- First call has ~2s JIT compilation overhead
- Numba functions cannot use Python dicts/objects (numpy arrays only)
- Fallback path maintains exact numerical parity with pandas_ta

## Enabling Numba
Strategy class must override:
```python
class MyStrategy(Strategy):
    def supports_numba(self) -> bool:
        return True  # opt in
```

## Fallback Behavior
```python
# backtest/engine.py:21-34
try:
    from numba import njit as _numba_njit
    _NUMBA_AVAILABLE = True
except ImportError:
    _NUMBA_AVAILABLE = False
    def _numba_njit(*args, **kwargs):
        """Graceful fallback: return the function unchanged."""
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
```

## Alternatives Considered
1. **Always-on Numba** — rejected: adds import time for strategies that don't need it
2. **Cython extension** — rejected: build complexity, no auto-fallback
3. **pandas vectorized** — rejected: still slower than Numba for per-bar loops

## References
- `backtest/engine.py:178-284` — Numba indicator implementations
- `strategies/base.py:282-287` — `supports_numba()` interface
- `tests/test_backtest_refactor_b1_b3_c4.py:219-336` — Numba correctness tests
