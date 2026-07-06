# LIVE / BACKTEST PARITY AUDIT — Phase 8
**Date:** 2026-07-05 | **Auditor:** Strategist Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md

---

## 8.1 — Code Path Mapping

### Feature Computation

| Function/Class | Backtest Path | Live Path | Shared? | Source |
|---------------|---------------|-----------|---------|--------|
| Standard indicators (SMA, EMA, RSI, MACD) | `backtest/engine.py:_calculate_indicators()` — batch via pandas_ta/Numba | `strategies/*.py` — per-bar rolling computation | **DIVERGENT** — different implementation | `backtest/engine.py:338-380` |
| SMC detectors (fractals, sweeps, OB, FVG, structure, pools) | `core/smc_detectors.py:*` — called from `build_features_v3_multi_asset.py:121-166` | Same `core/smc_detectors.py` — likely same functions | **SHARED** ✅ | `core/smc_detectors.py:1-17` |
| Volume profile features | `build_mega_features.py:1120-1215` | Same function? | **UNCERTAIN** — volume_profile_features exists but live path import unknown | `core/smc_detectors.py:1120-1215` |
| Macro features (FRED, COT) | `build_features_v3_multi_asset.py:169-252` — batch join with PIT-safe lag | Not called live | **DIVERGENT** — macro features absent from live path | `build_features_v3_multi_asset.py` |

### Signal Generation

| Component | Backtest | Live | Shared? | Source |
|-----------|----------|------|---------|--------|
| Strategy `generate_signal()` | `strategies/*.py:generate_signal()` | Same method called in `run_paper_trading.py` | **SHARED** ✅ | `strategies/walk_forward.py:50-57` |
| Ensemble combination | `strategies/ensemble.py:get_ensemble_signal()` | Same method | **SHARED** ✅ | — |
| XGBoost model weights | Loaded from same parquet/pickle artifact | Loaded from same artifact | **SHARED** ✅ | — |
| Signal sign convention | +1 = BUY, -1 = SELL | Consistent | **SHARED** ✅ | — |

### Execution

| Component | Backtest | Live | Shared? | Source |
|-----------|----------|------|---------|--------|
| Order submission | `execution/execution_simulator.py` — simulated fill at next-bar estimate | `execution/adapters/mt5.py:MT5Adapter.submit_order()` — `mt5.order_send()` | **DIVERGENT** | `execution_simulator.py`, `execution/adapters/mt5.py:195-225` |
| Fill price | Next-bar bid/ask estimate from OHLC + spread model | Real bid/ask from MT5 terminal | **DIVERGENT** | — |
| SL/TP management | `execution_simulator.py:evaluate_open_positions()` | MT5 terminal handles natively (server-side SL/TP) | **DIVERGENT** | — |
| Position sizing | `backtest/engine.py:_historical_size()` — `InlineContractSpec` | `risk/position_sizer.py` — separate implementation | **DIVERGENT** | — |

### Summary

| Category | Shared Functions | Divergent Functions | Risk Level |
|----------|-----------------|-------------------|------------|
| Feature computation | SMC detectors, XGBoost model | Standard indicators (batch vs rolling) | **MEDIUM** |
| Signal generation | Strategy.generate_signal(), Ensemble | — | **LOW** |
| Execution | Cost model (when wired) | Order submit, fill price, SL/TP, position sizing | **HIGH** |
| Risk checks | risk/*.py (shared library) | Pre-trade check order/validation may differ | **MEDIUM** |

---

## 8.2 — Feature Computation Parity

### Backtest: Vectorial (batch)
```python
# backtest/engine.py:358-361
ema_9 = ta.ema(df["close"], length=9)     # Full-array pandas_ta
ema_20 = ta.ema(df["close"], length=20)
ema_50 = ta.ema(df["close"], length=50)
ema_200 = ta.ema(df["close"], length=200)
```

### Live: Rolling (one bar at a time)
- Strategies access indicator data passed as `indicators` dict or compute from rolling state
- `strategies/base.py` and `strategies/mtm.py`/`mrm.py`/`mlb.py` use `required_features()` which maps to pre-computed feature names
- Live path pre-computes indicators per-bar (inferred from `run_paper_trading.py` flow) but the exact computation method is **not explicitly confirmed** in shared code

### Differences That Matter

1. **Initialization (warm-up)**: Backtest computes indicators over full history → first values use full lookback. Live starts from bar 0 → early warm-up values differ (NaN until window fills).

2. **EMA seeding**: `ewm(adjust=False)` in backtest is equivalent to recursive EMA, but the first EMA value uses the first bar's price vs. rolling true EMA which settles differently. Over hundreds of bars, this converges. Within first 20 bars per restart, values differ.

3. **Numerical precision**: Batch pandas_ta vs per-bar float operations may differ by ~1e-15 — negligible for signal generation.

4. **Data boundary**: Backtest sees the full dataset at once; live only sees bars up to current time. For lookback-sensitive features (SMA 200), this is semantically identical after warm-up.

### Verification Test

| Check | Status |
|-------|--------|
| Test comparing live-path indicator output vs backtest-path for same input data | **NOT FOUND** — `[NO PARITY TEST]` |
| Test verifying feature values at bar N match between batch and rolling computation | **NOT FOUND** |
| Numerical tolerance test | **NOT FOUND** |

**Verdict**: `[NO PARITY TEST FOUND]` — Feature computation is structurally different (batch vectorial vs incremental rolling). While conceptually equivalent for most indicators after warm-up, no quantitative test verifies parity. The SMC detectors are shared and should be identical. Macro features (FRED, COT) are not available in the live path — this is a **data-gap**, not just a code-gap.

---

## 8.3 — Signal Generation Parity

### Thresholding / Signal Logic
- **Strategies**: Same `generate_signal()` method called in both modes ✅
- **Ensemble**: Same `get_ensemble_signal()` called in both modes ✅
- **Confidence threshold**: `scripts/walk_forward.py:81-82` — `mask = confs >= min_confidence` (default 0.85). Live path likely uses same threshold — unconfirmed.
- **ML model weights**: XGBoost model saved as parquet/pickle artifact, loaded identically

### Potential Discrepancies
- **Feature set**: Live path may use a subset of features (lacks FRED, COT, yfinance cross-asset data)
- **Model expects N features**: If live path feeds fewer features than training, XGBoost will raise error or produce garbage
- **Default value for missing features**: Not handled — no fallback logic for macro features

### Sign Convention
- Signal output: +1 = BUY, -1 = SELL (consistent across all implementations)
- `strategies/ensemble.py:69-78` — `EnsembleVote` carries direction as +1/-1
- `scripts/walk_forward.py:79` — `direction = 2 * preds.astype(float) - 1`

**Verdict**: `[LIKELY SHARED]` — Signal generation logic is shared. Sign convention is consistent. **But**: feature availability differs (macro features missing in live path), creating a data-gap in signal parity.

---

## 8.4 — Order Execution Parity

### Systematic Gap Matrix

| Aspect | Backtest | Live | Parity Gap | Impact |
|--------|----------|------|-------------|--------|
| Fill timing | Bar N+1 open | Real-time market order | ~0-60 seconds latency | Direction-dependent in fast markets |
| Fill price | Estimated from OHLC + spread model + slippage | Actual mt5.order_send() fill | Real fills may be ~1-5 pips worse | **MATERIAL** |
| Spread | Modeled (session-based static table) | Actual bid/ask from MT5 | Real spreads widen in stress | **MATERIAL** |
| Slippage | Modeled (half-spread + impact) | Actual execution latency | Real slippage may exceed model | **MATERIAL** |
| Rejection risk | None (all signals fill at estimated price) | Real orders can be rejected, unfilled, partially filled | Model assumes 100% fill rate | **MATERIAL** |
| SL/TP execution | Simulated bar-level stop hitting | MT5 server-side stop orders | Server-side stops execute at exact level; bar-level model can miss intrabar hits | **MATERIAL** |
| Swap/rollover | `backtest/engine.py:_calculate_swap_cost()` | MT5 terminal deducts actual swap | Different rates, different timing | MINOR |

### Fill-Model Verification
- `execution/execution_simulator.py:145` — `fill on next bar OHLC + estimated bid/ask`
- No comparison between modeled fills and actual MT5 fills
- `shadow/broker_observed_runner.py` — designed to compare observed fills with hypothetical, but **no comparison output found**

**Verdict**: `[DIVERGENT — SYSTEMATIC GAP]` — The backtest fill model is an abstraction. Real execution introduces: fill uncertainty, order rejection, spread widening, and intrabar SL/TP behavior that the bar-level model cannot capture. The gap direction (optimistic vs pessimistic) is unknown without live-vs-backtest fill comparison data.

---

## 8.5 — Drift Detection

### Monitoring Infrastructure
| Component | Exists? | Source |
|-----------|---------|--------|
| Health check | YES | `monitoring/health_check.py` |
| Telegram alerts | YES | `monitoring/health_check.py` (via `config/telegram_config.toml`) |
| Observability | YES | `core/observability.py` |
| Metrics collection | YES | `monitoring/metrics.py` |

### Drift-Specific Detection
| Check | Status |
|-------|--------|
| Signal frequency drift (live signal count vs backtest expectation) | NOT IMPLEMENTED |
| Win rate drift (rolling β-out-of-control chart) | NOT IMPLEMENTED |
| Feature distribution drift (Kolmogorov-Smirnov test between backtest and live feature statistics) | NOT IMPLEMENTED |
| Model accuracy drift (live OOS accuracy vs training accuracy threshold) | NOT IMPLEMENTED |
| Sharpe ratio monitoring (rolling live Sharpe vs backtest expected) | NOT IMPLEMENTED |
| Cost model drift (live spread vs modeled spread) | NOT IMPLEMENTED |

### What Does Exist
- `core/walk_forward_production.py:WalkForwardDashboard` — renders HTML with drift alerts (boolean `drifted` field) but the `drifted` flag is set manually by the caller — **no automated drift detection logic** (`core/walk_forward_production.py:28`)
- `core/observability.py` — monitoring infrastructure but no drift-specific metrics

**Verdict**: `[NO DRIFT DETECTION]` — The system has no mechanism to detect when live signal statistics diverge from backtest expectations. The WalkForwardDashboard `drifted` flag is cosmetic — it must be set externally.

---

## 8.6 — Shadow-Mode Parallel Validation

### Shadow Infrastructure

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| Shadow pipeline | `shadow/shadow_pipeline.py` | Tick → signal → hypothetical fill → ledger | ✅ IMPLEMENTED |
| Shadow campaign manager | `shadow/shadow_campaign.py` | Campaign lifecycle (start/stop/status) | ✅ IMPLEMENTED |
| Canonical tick source | `shadow/canonical_tick_source.py` | Tick data ingestion | ✅ IMPLEMENTED |
| Canonical bar builder | `shadow/canonical_bar_builder.py` | Build bars from ticks | ✅ IMPLEMENTED |
| Broker observed runner | `shadow/broker_observed_runner.py` | Run against live broker data | ✅ IMPLEMENTED |
| Time reconciler | `shadow/terminal_time_reconciler.py` | MT5 time sync | ✅ IMPLEMENTED |
| Tick watermarks | `shadow/tick_watermark.py` | Tick dedup/sequencing | ✅ IMPLEMENTED |
| Pepperstone campaign | `shadow/pepperstone_campaign.py` | Broker-specific campaign | ✅ IMPLEMENTED |

### Has Shadow Mode Ever Produced Parity Comparisons?

| Question | Answer | Evidence |
|----------|--------|----------|
| Shadow logs exist on disk? | UNKNOWN — `shadow_results/` directory exists but content not checked | `shadow_results/` |
| Signal-agreement rate computed? | NOT FOUND — no output comparing live signals with shadow signals | `shadow/shadow_pipeline.py` stores signals but computes no agreement rate |
| Parity report generated? | NOT FOUND — `shadow_pass_criteria.py` defines criteria but no output file preserved | `shadow/shadow_pass_criteria.py` |

### Shadow Pipeline Limitations
`shadow/shadow_pipeline.py:66-99`:
```python
def process_tick(self, tick: dict) -> ShadowSignal | None:
    # Generate hypothetical signal (simplified strategy)
    signal = ShadowSignal(
        direction="BUY" if tick.get("bid", 0) < tick.get("ask", 0) else "SELL",
        ...
    )
```
- **The shadow pipeline uses a mock strategy** — direction is literally `BUY if bid < ask` (always true in normal markets = always BUY)
- This is a placeholder that does NOT exercise the actual strategy logic
- Shadow mode tests plumbing (tick → signal → ledger) but NOT strategy parity

**Verdict**: `[INFRASTRUCTURE EXISTS, NOT USED FOR PARITY]` — Shadow infrastructure is extensive and well-structured. But:
1. Uses a placeholder strategy (always BUY), not actual strategy logic
2. No signal-agreement rate computed between live and shadow
3. No parity comparison reports preserved
4. Campaign management (`shadow/shadow_campaign.py`) is a state machine with no actual campaign execution recorded

---

## 8.7 — Independent Execution-Path Validation

### Cross-Engine Validation

| Engine | Integration | Used for Parity? |
|--------|------------|------------------|
| NautilusTrader | `repo_intelligence/adapters/` — evaluated, no MT5 adapter | ❌ |
| Backtrader | Adapter exists | ❌ |
| VectorBT | Adapter exists | ❌ |
| Backtesting.py | Oracle integration (`repo_intelligence/adapters/`) | ❌ |

### Scope Limitation
- `reports/deep_audit_v4/LIVE_BACKTEST_PARITY.md:60` (existing): "No independently-implemented backtest engine found"
- All oracle adapters integrate external libraries for **reference only** — they are not used to validate the primary backtest
- **No independent engine has been run on the same strategy+data to cross-check results**

**Verdict**: `[NO INDEPENDENT ENGINE]` — All parity claims about the backtest engine are based on internal self-consistency. No independent implementation exists to validate that the backtest's cost model, fill model, or signal generation is correct. This is a **scope limitation of all parity claims**.

---

## 8. — FINAL VERDICT (Phase 8)

| Criterion | Status |
|-----------|--------|
| Feature computation parity | NO PARITY TEST — batch vs rolling, macro features absent live |
| Signal generation parity | LIKELY SHARED — same strategy code, but feature data differs |
| Order execution parity | DIVERGENT — simulated vs real, systematic gap in fill quality |
| Drift detection | NOT IMPLEMENTED — no automated monitoring of live-backtest divergence |
| Shadow mode validation | INFRASTRUCTURE EXISTS — placeholder strategy, no agreement rates computed |
| Independent engine validation | NONE — no independent backtest engine cross-check |

### Summary of Parity Gaps

| Gap | Severity | Likely Direction |
|-----|----------|-----------------|
| Live lacks macro features → different predictions | **HIGH** | Unknown — missing features could improve or degrade |
| Backtest uses next-bar estimated fill, live gets real fill | **HIGH** | Optimistic — real fills typically worse than modeled |
| Backtest assumes 100% fill rate | **MEDIUM** | Optimistic — real world has rejections |
| SL/TP: bar-level model vs server-side stops | **MEDIUM** | Unknown — bar model can miss intrabar stops |
| No drift detection | **HIGH** | Backtest edge may decay silently in live |
| Position sizing: divergent implementations | **MEDIUM** | Unknown — different lot sizes for same signal |
| Shadow mode uses placeholder strategy | **LOW** | Fixable — swap in real strategy |

**Overall**: `[PARTIAL]` — Infrastructure exists for many parity checks but none have been executed. The critical gaps are: (1) no feature computation parity test, (2) no fill-model validation, (3) no drift detection, and (4) shadow mode placeholder strategy. **Live results will not match backtest results, and no mechanism exists to detect or quantify this mismatch.**
