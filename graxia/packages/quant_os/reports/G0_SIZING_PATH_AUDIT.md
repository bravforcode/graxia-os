# G0.10 — Position Sizing Path Audit

**Date:** 2026-06-22
**Scope:** Legacy vs canonical position sizer import chains

---

## 1. Legacy Path — `risk/position_sizer.py`

### Imports

```python
from ..core.config import get_config
from ..core.golden_rules import GOLDEN_RULES
```

### Uses `units_per_lot`?

**Yes.** Every sizer class (`FixedFractionalSizer`, `KellySizer`, `ATRSizer`, `AntiMartingaleSizer`) accepts `units_per_lot` as a constructor parameter. The base `PositionSizer` class defaults it to `100000.0`.

### Uses hardcoded 100000?

**Yes.** The default parameter `units_per_lot: float = 100000.0` appears in every `__init__` signature. The fallback `get_default_sizer()` also implicitly uses it via the config path.

### Who imports it? (non-test only)

| File | What it imports |
|------|----------------|
| `risk/__init__.py:3` | `PositionSizer, KellySizer, ATRSizer` — re-exports for package API |
| `risk/engine.py:82` | Accepts `position_sizer` as constructor param, stores as `self.position_sizer` (never calls it in code — validation-only engine) |

### Test importers

| File | What |
|------|------|
| `tests/test_strategies.py:152,167` | `FixedFractionalSizer`, `KellySizer` |
| `tests/test_position_sizer_numeric.py:17` | All sizer classes |
| `tests/test_antimartingale_tiers.py:19` | `AntiMartingaleSizer` |

---

## 2. Canonical Path — `risk/position_sizer_v2.py`

### Imports

**None.** Zero framework or internal imports. The module is fully decoupled. It accepts a `contract_spec` parameter typed as a duck-typed object (comment says "ContractSpec — avoid import to keep module decoupled").

### Uses `ContractSpec`?

**Yes, but indirectly.** It accesses `contract_spec.trade_contract_size`, `contract_spec.trade_tick_size`, `contract_spec.trade_tick_value`, `contract_spec.volume_step`, `contract_spec.volume_min`, `contract_spec.stops_level_points`, `contract_spec.point`, `contract_spec.snapshot_hash`. No import dependency — purely duck-typed.

### Who imports it? (non-test only)

| File | What |
|------|------|
| `risk/pre_trade_risk.py:6` | `from .position_sizer_v2 import SizingResult` |

**Critical finding:** `pre_trade_risk.py` only imports `SizingResult`, NOT `size_position`. The actual `size_position()` function is never imported by any production code.

### Test importers

| File | What |
|------|------|
| `tests/test_phase_2b.py:22` | `SizingResult, size_position, RiskPolicy` |

---

## 3. Engine Path — `backtest/engine.py`

### Which sizer does the engine call?

**Neither.** The `BacktestEngine._execute_signal()` method (line 308) contains its own **inline position sizing** with hardcoded logic:

```python
risk_amount = self.balance * Decimal(str(self.config.risk_per_trade_pct)) / 100
quantity = risk_amount / risk_per_unit
```

It does NOT import or call `PositionSizer` (legacy) or `size_position()` (canonical).

### Function call chain

```
engine.run()
  → engine._execute_signal(signal, current_price, current_time)
    → Inline calculation: risk_amount / risk_per_unit → quantity
    → Inline commission: lots = quantity / self.config.units_per_lot
    → No sizer function called
```

### `units_per_lot` in engine

The engine uses `self.config.units_per_lot` (default `100000.0`) in `BacktestConfig` — the same hardcoded assumption as the legacy sizer. Used for commission calculation (lines 366, 427) only.

### `RiskEngine` in `risk/engine.py`

The risk engine also has inline sizing in `_check_position_size()` (line 162-177) that uses `self.units_per_lot` directly for exposure calculation. It accepts `position_sizer` as a constructor param but **never calls it**.

---

## 4. Conclusion

### Is the legacy path still reachable from canonical production code?

**Partially.** Here's the full reachability map:

| Code path | Reachable? | How |
|-----------|-----------|-----|
| `risk/__init__.py` → legacy sizer | ✅ Yes | `from quant_os.risk import KellySizer` |
| `risk/engine.py` → legacy sizer | ⚠️ Indirect | Constructor param, never called |
| `backtest/engine.py` → legacy sizer | ❌ No | Uses inline sizing |
| `backtest/engine.py` → v2 sizer | ❌ No | Uses inline sizing |
| `risk/pre_trade_risk.py` → v2 sizer | ⚠️ Partial | Imports `SizingResult` only, not `size_position()` |
| `run_paper_trading.py` → any sizer | ❌ No | Uses `RiskEngine` which has inline sizing |

### Key finding: Three separate sizing implementations exist

1. **Legacy sizer** (`position_sizer.py`): 4 sizer classes, uses hardcoded `units_per_lot=100000`, test-only consumers
2. **Canonical sizer** (`position_sizer_v2.py`): Single function, uses `ContractSpec`, test-only consumers
3. **Engine inline** (`backtest/engine.py`): Hardcoded risk_amount / risk_per_unit, actual runtime path

**None of these are wired into each other.** The canonical v2 sizer was built for Phase 2B (broker-native sizing) but the backtest engine was never migrated to use it.

### What needs to change for Phase 3.1

1. **Wire `BacktestEngine._execute_signal()` to call `size_position()`** from `position_sizer_v2.py` — pass a `ContractSpec` and `RiskPolicy` instead of inline math
2. **Wire `RiskEngine` to use `pre_trade_check()`** instead of inline `_check_position_size` — the v2 risk gate exists but is disconnected
3. **Remove `units_per_lot` from `BacktestConfig`** — it becomes a property of `ContractSpec`
4. **Deprecate legacy sizer** — no production code calls it; tests can be migrated to v2 fixtures

### Minimum change for Phase 3.1

Wire the backtest engine to use `size_position()`. The hard part is constructing a `ContractSpec` from backtest config (or a simplified mock). The easy part: replace the 15-line inline block in `_execute_signal()` with a `size_position()` call.
