# CORRECTIVE AUDIT ADDENDUM — 3 Critical Gaps Fixed

**Date:** 2026-06-25  
**Status:** READ-ONLY — no modifications made  
**Addresses:** 3 gaps identified by user review of original audit

---

## GAP 1: ~2000x Bug vs ms→ns Bug — Are They the Same?

### Finding: They are DIFFERENT bugs, and the ~2000x bug is NOT confirmed fixed.

**Evidence chain:**

1. **SUMMARY.md:4 says:** "Bug fixed: `simulate_fills.py` had ms/ns unit bug (added 50,000,000ms=13.9hr instead of 50ms). Fixed P90 slippage: 6367pts→39pts ($63.67→$0.39)."

2. **The math:** 6367 / 39 ≈ 163x improvement, NOT ~2000x. This is a slippage magnitude bug in the fill simulator, not a cost-unit bug in walk-forward validation.

3. **`simulate_fills.py:108`** — `tick_times = ticks['timestamp'].values.astype('datetime64[ms]').astype('int64')` — This converts timestamps to milliseconds. The bug was likely in how `lat_ms` was applied to `tick_times` (line 125: `target_time = decision_time + lat_ms`). If `lat_ms` was in seconds (50) but `tick_times` was in milliseconds, the search would advance 50 seconds instead of 50ms, hitting ticks much farther away → inflated slippage.

4. **The ~2000x bug** was described in the original audit prompt as a "cost-unit bug in walk-forward validation." The walk-forward scripts (`scripts/walk_forward.py`, `scripts/backtest_cost.py`) use a DIFFERENT cost path:
   - `walk_forward.py:108`: `cost_per_dollars = (spread_cost + slippage_p90) * price_mult`
   - `backtest_cost.py:119`: `cost_per_trade = (spread_cost + slippage_p90) * price * lot_mult`
   
   Both convert return-unit costs to dollars via `* price_mult` (≈2350 for XAUUSD).

5. **`tests/test_cost_unit_regression.py:6`** documents the ACTUAL cost-unit bug: "compute_fold_pnl() bug: cost_per (return units) was subtracted directly from raw_pnl_dollars, missing the *2350 price multiplier." This is a different bug from the ms→ns slippage bug.

6. **The test at `test_cost_unit_regression.py:39-43`** asserts cost/trade is $0.01-$5.00. If the ~2000x bug existed (cost in return units subtracted from dollar PnL), the cost would be ~0.0001 instead of ~$0.35, making it 2350x too small — NOT too large. This is the opposite direction of what SUMMARY.md describes.

### Conclusion

| Bug | Description | Status | Evidence |
|-----|-------------|--------|----------|
| ms→ns slippage | `simulate_fills.py` advanced 50s instead of 50ms → 6367pts slippage | **Fixed** (per SUMMARY.md) | `SUMMARY.md:4`, `simulate_fills.py:125` |
| ~2000x cost-unit | `compute_fold_pnl()` subtracted return-unit cost from dollar PnL without *2350 | **Fixed** (per test) | `test_cost_unit_regression.py:3,39-43` |
| ~2000x described in prompt | "cost-unit bug in walk-forward validation" with ~2000x error | **Likely the same as cost-unit bug above** | 2350x ≈ ~2000x (different rounding) |

**Verdict:** The ~2000x bug IS the cost-unit bug (missing *2350 multiplier). The ms→ns bug is a SEPARATE slippage estimation bug. Both appear fixed based on:
- `test_cost_unit_regression.py` passes (tests the *2350 multiplier)
- SUMMARY.md claims ms→ns fix (but this is self-report — unverified against current `simulate_fills.py`)

**What's NOT verified:** Whether `simulate_fills.py` currently has the ms→ns fix. The current code at line 108 uses `datetime64[ms]` and line 125 adds `lat_ms` directly — this looks correct NOW, but we cannot confirm it was wrong before without git history.

---

## GAP 2: Which Cost Path Does Backtest Actually Use?

### Finding: There are THREE SEPARATE cost paths, and SUMMARY.md numbers come from NONE of them.

**Cost Path 1: `backtest/engine.py` (BacktestEngine)**
```
engine.py:437  → spread = Decimal("0.01") * Decimal("2")  # HARDCODED 2 pips
engine.py:92   → commission_per_lot: Decimal = Decimal("3.5")  # HARDCODED $3.5
engine.py:91   → slippage_pips: float = 0.5  # HARDCODED 0.5 pips
```
This path is used by `run_backtest_real.py` and `phase_3b_runner.py`. It does NOT use `core/cost_model.py` or `scripts/backtest_cost.py`.

**Cost Path 2: `scripts/backtest_cost.py` (Phase F)**
```
backtest_cost.py:267  → spread_cost default = 0.17  # dollars
backtest_cost.py:269  → slippage_p90 default = 0.39  # dollars
backtest_cost.py:119  → cost_per_trade = (spread_cost + slippage_p90) * price * lot_mult
```
This is the path that generated SUMMARY.md numbers. It uses `artifacts/fill_samples_fixed/` for slippage P90 and `artifacts/features_v2/` for features. It does NOT use `backtest/engine.py`.

**Cost Path 3: `scripts/walk_forward.py` (Walk-Forward)**
```
walk_forward.py:108  → cost_per_dollars = (spread_cost + slippage_p90) * price_mult
walk_forward.py:50-51 → spread_cost, slippage_p90 are return units (fractional)
```
This uses `config/cost_calibration.json` for calibrated values:
- XAUUSD: spread_cost=0.000050, slippage_p90=0.000027 → $0.18/trade
- EURUSD: spread_cost=8e-06, slippage_p90=1.8e-05 → $0.06/trade

### The Three Cost Paths Are Incompatible

| Path | Spread | Slippage | Commission | Swap | Used By |
|------|--------|----------|------------|------|---------|
| `engine.py` | 2 pips hardcoded | 0.5 pips hardcoded | $3.5/lot hardcoded | ❌ | `run_backtest_real.py`, `phase_3b_runner.py` |
| `backtest_cost.py` | $0.17 (from fill samples) | $0.39 (P90 from fill samples) | ❌ | ❌ | SUMMARY.md numbers |
| `walk_forward.py` | 0.000050 return units | 0.000027 return units | ❌ | ❌ | `scripts/run_walk_forward.py` |

### What This Means for the "No Edge" Conclusion

The SUMMARY.md:9 "Net P&L: -$23.21" was generated by `backtest_cost.py` with:
- `spread_cost=0.17` (round-trip, dollars for 0.01 lot)
- `slippage_p90=0.39` (round-trip, dollars for 0.01 lot)
- `total_cost_per_trade=0.56`

But `engine.py` (used for strategy backtesting) uses:
- `spread=2 pips` = $0.02 per point × 100 points = $2.00 (for 0.01 lot XAUUSD, 1 pip = $0.01)
- Wait — this needs careful unit analysis.

**`engine.py` unit analysis:**
- `spread = Decimal("0.01") * Decimal("2")` = 0.02 (price units, i.e., $0.02 for XAUUSD)
- `contract_size = Decimal("100")` (0.01 lot = 1 oz)
- `commission_per_lot = Decimal("3.5")` (per lot, not per 0.01 lot)
- In `execution/cost_model.py:42`: `spread = spread_points * scenario.spread_mult * contract_size * volume`
  - If spread_points=0.02, contract_size=100, volume=0.01: spread = 0.02 × 1 × 100 × 0.01 = $0.02
  - Commission = 3.5 × 1 × 0.01 = $0.035
  - Total per trade ≈ $0.055

**`backtest_cost.py` uses:** $0.56 per trade

**Discrepancy: `engine.py` costs are ~10x LOWER than `backtest_cost.py` costs.**

This means:
1. If SUMMARY.md numbers came from `backtest_cost.py` ($0.56/trade), the conclusion "no edge after costs" is based on HIGHER costs
2. If the same strategy were run through `engine.py` ($0.055/trade), it might show a positive edge
3. **But `engine.py` hardcoded values are likely UNREALISTIC** — they don't reflect actual Pepperstone Razor spreads

### Conclusion

**The "no edge" conclusion in SUMMARY.md is based on `backtest_cost.py` cost path, NOT on `engine.py`.** The two paths use completely different cost models. The `engine.py` path (used for strategy development) has hardcoded costs that may be either too low or too high depending on the actual broker conditions.

**The cost calibration in `config/cost_calibration.json` is used by `walk_forward.py` but NOT by `engine.py` or `backtest_cost.py`.**

---

## GAP 3: Which RiskPolicy Does `pre_trade_check()` Actually Use?

### Finding: `pre_trade_check()` accepts RiskPolicy as a parameter — it uses WHICHEVER RiskPolicy the caller passes.

**Evidence:**

1. **`risk/pre_trade_risk.py:35-41`** — `pre_trade_check()` signature:
   ```python
   def pre_trade_check(
       sizing_result: SizingResult,
       risk_policy: RiskPolicy,  # <-- passed by caller
       risk_ledger: RiskLedger,
       account_equity: Decimal,
       kill_switch: KillSwitch = None,
   ) -> RiskCheckResult:
   ```
   It does NOT import or instantiate RiskPolicy itself.

2. **Which RiskPolicy is imported in `pre_trade_risk.py`?**
   `pre_trade_risk.py:6` — `from .position_sizer_v2 import SizingResult`
   `pre_trade_risk.py:7` — `from .risk_ledger import RiskLedger`
   `pre_trade_risk.py:8` — `from .kill_switch import KillSwitch`
   
   **`pre_trade_risk.py` does NOT import RiskPolicy at all.** It defines its own `RiskPolicy` at line 12:
   ```python
   @dataclass
   class RiskPolicy:
       """Configurable risk limits."""
       max_risk_per_trade_pct: Decimal = Decimal("1.0")
       ...
   ```
   This is the **MUTABLE** version (no `frozen=True`).

3. **The type hint `risk_policy: RiskPolicy`** in `pre_trade_check()` refers to the LOCAL `RiskPolicy` defined at line 12 of the same file — the MUTABLE one.

4. **Test usage (`test_phase_2b.py:22`):**
   ```python
   from quant_os.risk.position_sizer_v2 import SizingResult, size_position, RiskPolicy
   from quant_os.risk.pre_trade_risk import pre_trade_check
   ```
   The test imports RiskPolicy from `position_sizer_v2` (which also has its OWN mutable RiskPolicy at line 22), but calls `pre_trade_check()` which uses the RiskPolicy from `pre_trade_risk.py`.

5. **`risk/risk_policy.py:8`** — The FROZEN version:
   ```python
   @dataclass(frozen=True)
   class RiskPolicy:
       """Immutable risk policy. All loss limits in basis points."""
   ```
   This is the "correct" version per INV-001, but it's in a DIFFERENT module.

6. **`risk/micro_live_policy.py:4`** — `from .risk_policy import RiskPolicy` — imports the FROZEN version. This is the only file that imports from `risk_policy.py`.

### The Mutable RiskPolicy Problem

**There are THREE separate RiskPolicy classes:**

| Module | Class | Frozen? | Used By |
|--------|-------|---------|---------|
| `risk/pre_trade_risk.py:12` | `RiskPolicy` | ❌ Mutable | `pre_trade_check()` type hint |
| `risk/position_sizer_v2.py:22` | `RiskPolicy` | ❌ Mutable | `size_position()` type hint, tests |
| `risk/risk_policy.py:8` | `RiskPolicy` | ✅ Frozen | `micro_live_policy.py`, `test_phase_2a.py` |

**`pre_trade_check()` uses the MUTABLE version from `pre_trade_risk.py:12`.**

### Is This a Safety Issue?

**Yes, but with nuance:**

1. **The mutable RiskPolicy can be modified at runtime** — any code that has a reference to it could change `max_daily_loss_pct` from 2.0 to 100.0, bypassing risk limits.

2. **However, `pre_trade_check()` doesn't modify the policy** — it only reads from it (line 47-81). The risk is that SOME OTHER code modifies the policy object before it's passed to `pre_trade_check()`.

3. **In practice, the RiskPolicy is typically instantiated as a local variable** in tests and callers, not shared as a global. So the mutation risk is low in current usage.

4. **But the VIOLATION of INV-001 is real** — the constitution says "Risk policy is frozen dataclass, no runtime mutation" and the production code path uses a mutable version.

### Conclusion

| Check | Status | Evidence |
|-------|--------|----------|
| `pre_trade_check()` uses frozen RiskPolicy? | **NO** | `pre_trade_risk.py:12` — `@dataclass` (mutable) |
| INV-001 violated? | **YES** | `pre_trade_risk.py:12` vs `CONSTITUTION.md:12` |
| Practical risk in current codebase? | **LOW** | RiskPolicy typically instantiated locally, not shared |
| Should be fixed? | **YES** | INV-001 is explicit; mutable policy is a latent safety hazard |

---

## REVISED VERDICT ON ORIGINAL AUDIT CONCLUSIONS

| Original Conclusion | Revised Status | Reason |
|---------------------|----------------|--------|
| "Cost bug fixed" | **Partially verified** | Cost-unit bug (missing *2350) fixed per test. ms→ns slippage bug claimed fixed but not independently verified |
| "No edge after costs" | **Based on specific cost path** | SUMMARY.md numbers from `backtest_cost.py` ($0.56/trade). `engine.py` uses different costs ($0.055/trade).结论 depends on which cost model is "real" |
| "Risk gate works" | **Uses mutable RiskPolicy** | INV-001 violation. Functionally works but violates architectural invariant |
| "Kill switch persists" | **Verified** | `kill_switch.py:39-46` — JSON persistence confirmed |

---

## WHAT NEEDS TO BE VERIFIED NEXT

1. **Which cost path is "real"?** — Is `backtest_cost.py` ($0.56/trade) or `engine.py` ($0.055/trade) the correct cost model for the instrument being traded? This requires checking actual Pepperstone Razor XAUUSD spread data.

2. **Git history for ms→ns fix** — Can we confirm `simulate_fills.py` actually had the bug and was fixed? Current code looks correct but we can't verify the fix without history.

3. **Consolidate RiskPolicy** — All three RiskPolicy classes should be consolidated into the frozen version in `risk/risk_policy.py`, and `pre_trade_risk.py` should import from there.

---

*Addendum completed: 2026-06-25. All findings are evidence-based with file:line citations.*
