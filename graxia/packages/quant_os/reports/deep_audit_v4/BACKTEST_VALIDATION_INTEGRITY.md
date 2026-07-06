# BACKTEST VALIDATION INTEGRITY — Phase 7
**Date:** 2026-07-05 | **Auditor:** Strategist Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md

---

## 7.1 — Transaction Cost Model (Final Verification)

### Where Costs Are Subtracted

| Path | Cost Location | How Applied | Source |
|------|--------------|-------------|--------|
| Backtest (engine) | Commission + swap deducted from trade PnL at close | Per-trade | `backtest/engine.py:_close_position()` |
| Walk-forward (ML) | Deducted from per-bar raw PnL as fixed cost/trade | Per-signal bar | `scripts/walk_forward.py:110-111` |
| Live (paper) | `execution/cost_model.py` — session-based cost tables | Per-trade | `execution/cost_model.py:18-23` |

### Cost Components

| Component | Backtest | ML Walk-Forward | Live |
|-----------|----------|-----------------|------|
| Spread | `dynamic_spread_model.py` — time-of-day variation | `spread_cost` arg (default $0.024) | `tick.ask - tick.bid` |
| Slippage | Half-spread + latency + market impact + adverse selection | `slippage_p90` arg (default $0.02) | Live observed (if system tracks it) |
| Commission | `execution_simulator.py:158-165` | Included in spread+slippage | P90 estimated |
| **Swap/rollover** | `backtest/engine.py:1078-1140` — `_calculate_swap_cost()` added during P0 fix | **NOT INCLUDED** | `core/risk/swap_cost.py` (orphaned per `AUDIT_INDEX.md:98`) |
| **Funding (crypto)** | NOT FOUND | NOT FOUND | NOT FOUND |

### Swap Cost Integration Status
- `core/risk/swap_cost.py`: EXISTS with `estimate_overnight_cost()` and `get_swap_cost_for_trade()`
- `backtest/engine.py:1078-1140`: `_calculate_swap_cost()` was added during P0 fix pass
- **BUT**: `KNOWLEDGE_LIMITATIONS.md:3` states "Swap not modeled in cost calculations" — suggesting the fix may be incomplete

### Known Cost Bug in Walk-Forward
`scripts/walk_forward.py:108-111`:
```python
price_mult = float(np.mean(closes_masked))
...
cost_per_dollars = (spread_cost + slippage_p90) * price_mult
```
- `price_mult` = mean of all test bar close prices (e.g., ~2350 for XAUUSD) — **IS now dynamic** (was hardcoded 2350.0 pre-fix)
- Raw PnL uses per-bar prices (`:110` — `raw_pnl_dollars = dir_mask * rets * closes_masked`)
- **BUT R13 states**: "only current state confirmed, prior buggy state not re-tested" (`AUDIT_INDEX.md:93`)

### Worst-Case Scenario: 2× Spread
- **NOT PERFORMED** — no stress test re-running with doubled spread costs
- `validation/cost_stress.py` or similar stress test: NOT FOUND
- `execution/cost_model.py` has `StressScenario` dataclass with `spread_mult` and `slippage_mult` fields but no sweep application

**Verdict**: `[PARTIAL]` — Cost model is multi-layered but:
1. Swap costs may not be wired (conflicting evidence)
2. Crypto funding rates not modeled
3. No 2× spread worst-case test
4. Walk-forward cost was buggy (hardcoded 2350) — now dynamic but unverified

---

## 7.2 — Fold Construction

### ML Walk-Forward (`scripts/walk_forward.py:163-180`)

```python
train_start = fold_idx * step     # 0, 200, 400, ...
train_end   = train_start + train_window  # 500, 700, 900, ...
test_end    = train_end + test_window     # 700, 900, 1100, ...
```

| Parameter | Default | Meaning |
|-----------|---------|---------|
| train_window | 500 | Bars per training fold |
| test_window | 200 | Bars per test fold |
| step | 200 | Bars to advance per fold |
| **Purge gap** | **0** | **Train ends at bar N, test starts at bar N** |

### Strategy Walk-Forward (`backtest/walk_forward.py:127-201`)

| Mode | Description | Purge Support |
|------|-------------|---------------|
| Anchored | IS starts at 0, grows each window | `purge_bars` parameter (default: 0) |
| Rolling | Fixed IS length, slides forward | `purge_bars` parameter (default: 0) |

### Critical Issues

1. **Zero Purge Gap**: Default `purge_bars=0` in all implementations (`backtest/walk_forward.py:109-110`). With 5-bar forward returns (`build_features.py:43` — `TARGET_FORWARD_BARS = 5`), bars at the IS/OOS boundary carry label information across the split.

2. **Row-count folds, not time-period folds**: `scripts/walk_forward.py` splits by bar count. At 1-min resolution, 500 bars = 8.3 hours. These are trivially small time periods — a single trading session.

3. **Train/validation/holdout dates are unfilled**: `validation/dataset_protocol.py:63-69` — dates are placeholder defaults with comment "User must fill actual dates."

**Verdict**: `[FAIL]` — No purge gap between IS and OOS. Folds are row-count based, not time-period based. With 5-bar forward labels, at least 5 bars of embargo are needed.

---

## 7.3 — Order Execution Realism

### Signal-to-Fill Timing

| Path | When Signal Generated | When Fill Executed | Realistic? |
|------|----------------------|-------------------|------------|
| Backtest engine | Bar N close (signal on closed bar) | Bar N+1 open (`backtest/engine.py:311`) | YES ✅ |
| ML walk-forward | Prediction at bar N (test fold start+n) | Same bar N | **NO** — `scripts/walk_forward.py:208-211` uses same-bar data |
| Live/paper | Real-time tick → signal | Next available tick via MT5 | YES ✅ |
| Execution simulator | Bar N OHLCV | Next bar OHLC + bid/ask estimation (`execution_simulator.py:145`) | YES ✅ |

### Look-at-Close, Trade-at-Open Issue
- `scripts/walk_forward.py:178-183`: X_test contains features including bar N's own close (via `close.diff()`, etc.)
- `scripts/walk_forward.py:201`: `model.predict(X_test)` makes prediction using bar N's data
- `scripts/walk_forward.py:228`: PnL uses `ret_test` which is `target_return` — the forward return from bar N → N+forward_bars
- **If any feature uses the current bar's close** (which many do — SMA, EMA, RSI, etc.), the prediction at bar N implicitly uses bar N's close to predict bar N's future return → **lookahead in prediction**
- Mitigation: Features are computed from `close.shift()` variants for relative features, but **SMAs and EMAs use current bar's close**

### For 1-Min System
- 1-min bars with next-bar fill = execution delay of ≤60 seconds
- For XAUUSD liquid during London/NY: realistic
- For Asian session or low-liquidity periods: spreads widen, next-bar fill at estimated bid/ask may be optimistic

**Verdict**: `[PARTIAL]` — Backtest engine has proper next-bar fill. ML walk-forward does NOT — it uses same-bar features + same-bar returns. For a 1-min system, the backtest path is marginally realistic; the ML path is not.

---

## 7.4 — Position Management

### Walk-Forward (ML)
`scripts/walk_forward.py:79-80`:
```python
direction = 2 * preds.astype(float) - 1  # 0→-1 (short), 1→+1 (long)
mask = confs >= min_confidence
```
- **Max 1 position per bar?** Yes — one prediction per bar
- **New signal while position open?** N/A — each bar is an independent prediction; there is no position state
- **Portfolio-level constraints: NOT APPLIED** — no at-most-one-position-per-instrument rule

### Backtest Engine
`backtest/engine.py` — full position tracking, SL/TP management, position sizing via `_historical_size()`

### Consistency Check
- ML walk-forward treats each bar as independent trade opportunity — **no position carry-over**
- Backtest engine manages open positions, SL/TP, sizing — **completely different model**
- **These are not comparable** — they're testing different things

**Verdict**: `[DIVERGENT]` — Walk-forward and backtest use fundamentally different position models. Walk-forward is a per-bar classifier; backtest is a portfolio simulation. They cannot validate each other.

---

## 7.5 — Performance Degradation

### IS vs OOS per Fold
- `scripts/walk_forward.py:188`: `train_acc = (model.predict(X_train) == y_train_cls).mean()`
- `scripts/walk_forward.py:204`: `oos_acc = (preds == y_test_cls).mean()`
- **Ratio not computed per fold** — `scripts/walk_forward.py:246-247` stores them separately; no OOS/IS calculation

### Parameter Sensitivity
- `scripts/walk_forward.py` default params: depth=5, n_estimators=100, learning_rate=0.1
- No ±20% sensitivity sweep
- `core/param_sweep.py` exists for sensitivity analysis but not integrated with walk_forward

### What's Missing
- IS Sharpe vs OOS Sharpe per fold: NOT TRACKED
- OOS/IS ratio: NOT COMPUTED in ML path
- Parameter perturbation (±20%): NOT TESTED
- `backtest/walk_forward.py:249-260` computes WFE (OOS Sharpe / IS Sharpe) but only for strategy backtests, not ML

**Verdict**: `[NOT MEASURED]` — Performance degradation is tracked in `backtest/walk_forward.py` but not in the primary `scripts/walk_forward.py` ML path.

---

## 7.6 — Final Verdict

> **Is there a statistically significant, cost-adjusted, out-of-sample edge?**

| Criterion | Value | Threshold | Pass? |
|-----------|-------|-----------|-------|
| OOS trades count | Unknown — depends on confidence threshold | ≥ 200 for statistical significance | UNVERIFIED |
| OOS Sharpe with CI | Not computed | — | ❌ |
| p-value (multiple-testing corrected) | Not computed | α_corrected | ❌ |
| Cost model complete? | NO — swap costs orphaned, crypto funding absent | All costs included | ❌ |
| Purge gap present? | NO — 0 bars | ≥ 5 bars | ❌ |
| Holdout final validation performed? | NO — infrastructure unused | — | ❌ |

### ANSWER: **INSUFFICIENT EVIDENCE**

The system has no verified OOS edge. The walk-forward pipeline has:
- No purge gap (autocorrelation bleed between IS/OOS)
- Zero-basis point difference from binary-classifier accuracy is indistinguishable from noise at n≤5,000 bars
- No confidence intervals on any metric
- No multiple-testing corrected p-value
- Walk-forward result files are not preserved in the repo
- The ensemble `_consensus_levels()` returned `(None, None)` until P0 fix, meaning historical results used no-stop-loss trading

---

## 7.7 — Tick-Level vs Bar-Level Reconciliation

### Tick Replay Infrastructure
- `execution/execution_simulator.py` defines `ExecutionQuality.TICK_REPLAY` as an **enum value** only (`:16`)
- `reports/deep_audit_v4/INTRABAR_EXECUTION_FIDELITY.md:178`: "Tick replay is not implemented. All execution simulation uses bar-level OHLCV data only."
- `ticks/` directory: Exists with tick data CSVs
- `tick/` directory: Exists with tick utilities

### Reconciliation
- **No tick-level backtest has been performed**
- No comparison between bar-level fill estimates and tick-level actual fills
- `mt5_connector/` has tick-fetching capability but not integrated with backtest engine

**Verdict**: `[NOT IMPLEMENTED]` — Tick replay is an aspirational enum value. All fills are bar-level OHLCV estimates.

---

## 7.8 — Historical Cost-Schedule Changes

- Cost assumptions are **static**, not time-varying
- `config/cost_calibration.json` — calibration values by symbol (exists, not read at time of audit)
- Session-based costs in `execution/cost_model.py:18-23` are fixed lookup tables per session (Asian: $0.28, London: $0.14, NY: $0.15, Overlap: $0.12)
- No historical spread widening events captured (e.g., FOMC, NFP, COVID 2020)
- No spread regime detection: "if spread widens to X, cost model should adjust"

**Verdict**: `[STATIC]` — Costs are point-in-time calibrated, not historically aware. Backtesting through crisis periods uses today's spread costs.

---

## 7.9 — Per-Instrument Walk-Forward Coverage

| # | Instrument | Asset Class | W-F Run? | Fold Count | OOS Sharpe (CI) | Data Sufficiency | Source |
|---|------------|-------------|----------|------------|-----------------|------------------|--------|
| 1 | EURUSD | FX | YES | ~22 | UNKNOWN | NO (5,001 M1) | `scripts/walk_forward.py:330` default |
| 2 | XAUUSD | Metals | YES | ~22 | UNKNOWN | NO (5,001 M1) | `scripts/walk_forward.py:330` default |
| 3 | GBPUSD | FX | NO | — | — | NO (5,001) | `build_features.py:292` — in instrument list |
| 4 | USDJPY | FX | NO | — | — | NO (5,001) | `build_features.py:294` |
| 5 | USDCAD | FX | NO | — | — | NO (5,001) | `build_features.py:294` |
| 6 | USDCHF | FX | NO | — | — | NO (5,001) | `build_features.py:294` |
| 7 | AUDUSD | FX | NO | — | — | NO (5,001) | `build_features.py:292` |
| 8 | NZDUSD | FX | NO | — | — | NO (5,001) | `build_features.py:293` |
| 9 | BTCUSD | Crypto | NO | — | — | NO (7,881) | `build_features.py:292` |
| 10 | ETHUSD | Crypto | NO | — | — | NO (7,881) | `build_features.py:292` |
| 11 | NAS100 | Indices | NO | — | — | NO (5,001) | `build_features.py:293` |
| 12 | US30 | Indices | NO | — | — | NO (5,001) | `build_features.py:293` |
| 13 | XAGUSD | Metals | NO | — | — | NO (5,001) | `build_features.py:294` |
| 14 | XPDUSD | Metals | NO | — | — | NO (5,001) | `build_features.py:294` |
| 15 | XPTUSD | Metals | NO | — | — | NO (5,001) | `build_features.py:294` |

**Summary**:
- 2 of 15 instruments have walk-forward runs (EURUSD, XAUUSD) — **both with buggy cost calculation**
- 0 of 15 have sufficient data by any reasonable bar-count threshold (minimum: 50,000 M1 bars = ~35 trading days)
- 0 of 15 have recorded OOS Sharpe results
- **13 of 15 instruments = ZERO OUT-OF-SAMPLE EVIDENCE**

---

## 7. — FINAL VERDICT (Phase 7)

| Criterion | Status |
|-----------|--------|
| Transaction cost model | PARTIAL — swap/funding incomplete, cost bug partially fixed |
| Fold construction | FAIL — no purge gap, row-count folds, 8-hour train windows |
| Order execution realism | PARTIAL — engine OK, ML path uses same-bar features |
| Position management | DIVERGENT — ML vs backtest are incompatible models |
| IS/OOS degradation | NOT MEASURED in ML path |
| Final edge verdict | INSUFFICIENT EVIDENCE |
| Tick replay | NOT IMPLEMENTED |
| Cost schedule changes | STATIC only |
| Per-instrument coverage | 13/15 = NO EVIDENCE; 2/15 = BUGGY |

**Overall**: `[FAIL]` — No verified OOS edge. Walk-forward has structural flaws (no purge gap, small folds). 87% of instruments have no OOS validation. The system cannot claim any cost-adjusted, statistically significant edge.
