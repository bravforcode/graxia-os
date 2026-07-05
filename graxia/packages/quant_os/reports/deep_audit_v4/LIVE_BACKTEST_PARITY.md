# LIVE/BACKTEST PARITY AUDIT
**Phase 8 | 2026-07-05 | TIER 1**

---

## 8.1 — Code Path Mapping

| Function/Component | Backtest Path | Live Path | Shared? |
|---|---|---|---|
| Feature computation (indicators) | `backtest/engine.py:_calculate_indicators()` | `strategies/*.py` (per-strategy) | **DIVERGENT** — backtest uses Numba/pandas_ta batch; live uses per-bar |
| Signal generation | `strategies/*.py:generate_signal()` | Same | **SHARED** ✅ |
| Ensemble combination | `strategies/ensemble.py:get_ensemble_signal()` | Same | **SHARED** ✅ |
| Position sizing | `backtest/engine.py:_historical_size()` | `risk/position_sizer.py` | **DIVERGENT** — different implementations |
| Order execution | `execution/execution_simulator.py` | `execution/adapters/mt5.py:MT5Adapter.submit_order()` | **DIVERGENT** — simulated vs real |
| Cost model | `execution/cost_model.py` | Same (if wired) | **SHARED** (when wired) |
| SL/TP evaluation | `execution/execution_simulator.py:evaluate_open_positions()` | MT5 terminal handles SL/TP natively | **DIVERGENT** |

### Critical Divergence: Position Sizing
- **Backtest:** `_historical_size()` — deterministic, uses `InlineContractSpec`, risk-budget-based
- **Live:** `risk/position_sizer.py` — separate implementation, potentially different formula
- **Impact:** Same signal could produce different lot sizes in backtest vs live

### Critical Divergence: Indicator Computation
- **Backtest:** Vectorized batch computation via Numba JIT or pandas_ta on full dataset
- **Live:** Per-bar rolling computation (inferred — not directly confirmed in live path code)
- **Risk:** Numerical differences between batch and rolling computation could produce different signals

## 8.2 — Feature Computation Parity
- No test found that verifies live-path indicator output matches backtest-path output for the same input data
- **Status:** `[NO PARITY TEST FOUND]`

## 8.3 — Signal Generation Parity
- Strategies use the same `generate_signal()` method in both modes
- Model weights (XGBoost) loaded from same artifact
- Signal sign convention: +1 = BUY, -1 = SELL (consistent)
- **Status:** Likely shared ✅

## 8.4 — Order Execution Parity
- **Backtest:** Fill on next bar's estimated bid/ask + slippage
- **Live:** Market order via `mt5.order_send()` with `TRADE_ACTION_DEAL`
- **Gap:** Backtest uses bar-level bid/ask estimation; live uses real bid/ask from MT5 terminal
- **Impact:** Systematic difference in fill quality between backtest and live

## 8.5 — Drift Detection
- `core/observability.py` exists — monitoring infrastructure
- No specific mechanism to detect when live signal statistics diverge from backtest expectations
- **Status:** `[NO DRIFT DETECTION]`

## 8.6 — Shadow-Mode Parallel Validation
- `shadow/` directory exists with extensive shadow-mode infrastructure:
  - `shadow/shadow_pipeline.py` — shadow trading pipeline
  - `shadow/shadow_campaign.py` — campaign management
  - `shadow/canonical_tick_source.py` — tick data source
  - `shadow/canonical_bar_builder.py` — bar construction
  - `shadow/terminal_time_reconciler.py` — time reconciliation
- `shadow/broker_observed_runner.py` — runs against live broker data
- **Status:** Shadow infrastructure EXISTS but not verified to have produced parity comparisons

## 8.7 — Independent Execution-Path Validation
- No independently-implemented backtest engine found
- `repo_intelligence/adapters/` has adapters for backtesting_py, backtrader, vectorbt — but these are oracle integrations, not independent engines
- **Status:** `[NO INDEPENDENT ENGINE]` — all parity checks can only confirm internal self-consistency
