# ARCHITECTURE OVERVIEW — COMPREHENSIVE DEEP REVIEW
**Date**: 2026-07-06 | **Status**: POST-DIRECTION-FAILURE REDESIGN
**Codebase**: 1,043 Python files / 217,342 lines / ~45 modules

---

## 1. MODULE MAP

### 1.1 Top-Level Architecture
```
quant_os/
├── core/              (90 files) — Config, enums, golden rules, event bus, agents, data, ML, risk
├── risk/              (24 files) — Position sizing, pre-trade risk, kill switch, circuit breaker
├── execution/         (34 files) — OMS, order state machine, fill model, adapters (MT5/Binance)
├── strategies/        (7 files)  — MTM, MRB, MLB, ensemble, walk-forward
├── backtest/          (17 files) — Backtest engine, metrics, data loader, dynamic spread
├── ml/                (6 files)  — ML pipeline, labeling, model registry, feature store
├── validation/        (44 files) — DSR, PBO, bootstrap, regime detector, experiment registry
├── api/               (21 files) — FastAPI: webhook, orders, positions, risk, admin, TV
├── broker/            (4 files)  — Contract specs, MT5 gateway (read-only)
├── shadow/            (42 files) — Shadow trading pipeline, broker observed runner
├── canary/            (32 files) — Demo canary: config, order lifecycle, drills
├── autonomous/        (13 files) — LLM-driven 24/7 trading loop
├── regime/            (13 files) — Regime detector, sweep classifier, risk overlay
├── alpha/             (3 files)  — Alpha engine, regime detector (alternative)
├── gold_bot/          (47 files) — XAUUSD AI bot: 13 strategies, Claude AI, MT5 adapter
├── market_data/       (12 files) — Tick recorder, spread monitor, feed health
├── monitoring/        (21 files) — Telegram notifier, health checks, Grafana
├── data/              (9 files)  — Data models, pipeline, quality gate, DuckDB
├── data_pipeline/     (17 files) — Storage (DuckDB, Chroma), sources, scheduler
├── governance/        (7 files)  — Validation stack, trial budget, ML policy
├── expansion/         (12 files) — Controlled expansion tracker, planner
├── micro_live/        (12 files) — Phase 9 micro-live
├── live_readiness/    (8 files)  — MT5 read-only client, account snapshots
├── news_events/       (7 files)  — Economic event models, event risk gate
├── events/            (15 files) — Event schema, event risk gate, event metrics
├── markets/           (15 files) — EURUSD session calendar, hypothesis, exit gate
├── tick/              (9 files)  — Tick schema, storage, metrics, MT5 recorder
├── ticks/             (9 files)  — Test files only (orphaned mirror of tick/)
├── repo_intelligence/ (15 files) — Backtrader/vectorbt/LEAN adapters, hooks
├── config/            (4 files)  — TV config, CDP config
├── runtime/           (9 files)  — Secret provider, redaction, broker identity guard
├── oracle/            (11 files) — Oracle adapter, differential comparator
├── analysis/          (3 files)  — Visual chart search, trade expectancy
├── research/          (2 files)  — Automated research pipeline
├── mt5_connector/     (3 files)  — MT5 connection, shadow runner
├── scripts/           (100+ files) — Build features, train, walk-forward, backtest suites
├── tests/             (100+ files) — Unit, integration, chaos, phase tests
└── infra/             (1 file)   — Empty __init__.py
```

### 1.2 Critical Statistics
| Metric | Count |
|--------|-------|
| Total Python files | 1,043 |
| Total lines of code | 217,342 |
| Modules (top-level dirs) | ~45 |
| Largest file | `backtest/engine.py` (1,467 lines) |
| Never-imported modules | 19 |
| Orphaned standalone scripts | 19 (~3,276 dead lines) |
| Duplicate filenames | 45+ |
| Duplicate function/class names | 50+ |
| Skipped/quarantined tests | 24 |
| TODO/FIXME/HACK markers | 14 (very clean) |
| Circular dependencies | 1 confirmed (core ↔ api) |

---

## 2. DATA FLOW (Current)

```
Market Data (MT5/EA)
    │
    ▼
BarEvent (core.events)
    │
    ▼
Strategies (mtm/mrb/mlb) → Signal
    │
    ▼
StrategyEnsemble → EnsembleResult (weighted consensus)
    │
    ▼
PositionSizer (risk/position_sizer_v2) → SizingResult
    │
    ▼
PreTradeRisk (risk/pre_trade_risk) → RiskCheckResult
    │
    ▼
OrderManager (execution/manager) → Order lifecycle (9 steps)
    │
    ▼
BrokerManager / MT5Adapter → Fill
    │
    ▼
BacktestExecutionSimulator → PnL Accounting
```

### 1.3 Data Flow for NEW Architecture
```
Cross-Asset Data (15 instruments)
    │
    ▼
┌─────────────────────────────────┐
│  Stage 1: VOLATILITY ENGINE     │
│  HAR model + XGBoost regime     │
│  Output: σ̂ per instrument       │
└───────────────┬─────────────────┘
                │ σ̂
┌───────────────▼─────────────────┐
│  Stage 2: REGIME GATE           │
│  4-class classifier             │
│  Output: position_scale [0,1.5] │
└───────────────┬─────────────────┘
                │ scale
┌───────────────▼─────────────────┐
│  Stage 3: FACTOR SIGNALS        │
│  TSMOM + Carry + Pairs MR       │
│  Output: signal ∈ {-1,0,+1}     │
└───────────────┬─────────────────┘
                │
┌───────────────▼─────────────────┐
│  FINAL: VOL-TARGETED SIZING     │
│  position = signal × scale      │
│            × (σ_target/σ̂)       │
│            × capital             │
└─────────────────────────────────┘
```

---

## 3. DUPLICATE IMPLEMENTATIONS (Critical)

### 3.1 RegimeDetector — 4+ competing implementations
| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `regime/__init__.py` | `RegimeDetector` | ADX+EMA+ATR voting | **ACTIVE** (regime/ module) |
| `validation/regime_detector.py` | `RegimeDetector` | Vol + correlation regime | **ACTIVE** (validation) |
| `alpha/regime_detector.py` | `RegimeDetector` | 6-regime model (BULL/BEAR/CHOP/etc.) | **ORPHANED** (0 imports) |
| `core/regime_filter.py` | `RegimeFilter` | BULL/BEAR/RANGE/CHOP | **ACTIVE** (core/) |
| `core/canonical/macro_regime.py` | `MacroRegimeCache` | Macro regime state | **ACTIVE** (canonical) |
| `risk/slippage_model.py` | `VolatilityRegime` | Enum only (LOW/MED/HIGH) | Partial |

**Impact**: No single source of truth for "what regime are we in?"

### 3.2 Deflated Sharpe Ratio — 10+ implementations
| File | Implementation |
|------|---------------|
| `validation/deflated_sharpe.py:39` | **Canonical** (Bailey-López de Prado) |
| `core/holdout_validation.py:139` | Simplified duplicate |
| `core/param_sweep.py:93` | Wrapper duplicate |
| `strategies/walk_forward.py:178` | Private duplicate |
| `governance/validation_stack.py:65` | Governance wrapper |
| `scripts/tsm_backtest.py:178` | Inline duplicate |
| `scripts/tsm_validate.py:357` | Full reimplementation |
| `scripts/tsm_ema.py:181` | Inline duplicate |
| `scripts/tsm_portfolio.py:241` | Inline duplicate |
| `scripts/tsm_ensemble_backtest_4asset.py:369` | Inline duplicate |
| `scripts/tsm_ensemble_backtest.py:370` | Inline duplicate |
| `scripts/tsm_btcusd_validate.py:421` | Inline duplicate |

**Impact**: Different DSR formulas give different results — no single truth for strategy validation.

### 3.3 get_feature_cols — 9 implementations
All in `scripts/`, each with DIFFERENT exclude sets:
- `walk_forward.py:39` — excludes 16 cols
- `wf_patched.py:27` — excludes 16 cols
- `backtest_cost.py:71` — excludes 16 cols
- `optuna_tune.py:40` — excludes 16 cols
- `train_strategy.py:57` — excludes 17 cols
- `train_mega_model.py:119` — EXCLUDE_COLS set
- `train_mega_model_v2.py:171` — EXCLUDE_COLS set (**gold standard**)
- `diagnose_regime_accuracy.py:66` — only 5 cols
- `regime_filter.py:341` — only 5 cols

**Impact**: Only `train_mega_model_v2.py` has complete leakage exclusion.

### 3.4 walk_forward — 15+ implementations
| Location | Count |
|----------|-------|
| `scripts/walk_forward.py` | 1 |
| `scripts/wf_patched.py` | 1 |
| `scripts/run_multi_symbol_wf.py` | 1 |
| `scripts/retrain_calibrated.py` | 1 |
| `scripts/train_live_model.py` | 3 |
| `scripts/train_mega_model.py` | 3 |
| `scripts/train_mega_model_v2.py` | 3 |
| `scripts/tsm_backtest.py` | 1 |
| `scripts/tsm_ema.py` | 1 |
| `scripts/tsm_btcusd_validate.py` | 1 |
| `validation/walk_forward.py` | 1 |
| `core/cross_validation.py` | 1 |
| `strategies/walk_forward.py` | 1 |

### 3.5 build_features — 8 implementations
| File | Version |
|------|---------|
| `scripts/build_features.py` | v1 (main) |
| `scripts/build_features_v3_multi_asset.py` | v3 (multi-asset) |
| `scripts/run_walk_forward.py` | pipeline variant |
| `scripts/train_all_models.py` | inline duplicate |
| `scripts/train_features_v3.py` | inline duplicate |
| `scripts/train_dual_head.py` | wrapper |
| `scripts/multi_symbol_bot.py` | live variant |
| `scripts/download_cot_gold.py` | COT variant |

### 3.6 EventRiskGate — 3 competing implementations
| File | Status |
|------|--------|
| `events/event_risk_gate.py` | **ACTIVE** |
| `news_events/event_risk_gate.py` | **ACTIVE** |
| `shadow/event_risk_gate.py` | **ACTIVE** |

### 3.7 Other Duplicates
- **DataPipeline**: 3 implementations (`core/multi_source_pipeline.py`, `data/pipeline.py`, `data_pipeline/pipeline.py`)
- **ExperimentRegistry**: 2 implementations (`governance/`, `validation/`)
- **ExitGate**: 2 implementations (`markets/eurusd/`, `validation/`)
- **FeedHealthMonitor**: 2 implementations (`market_data/`, `tick/`)
- **BrokerProfile**: 3 implementations (`live_readiness/`, `runtime/`, `shadow/`)
- **ContractSpec**: 3 implementations (`broker/`, `execution/`, `risk/`)
- **Dashboard**: 3 implementations (`core/`, `gold_bot/`, `scripts/`)
- **HealthCheck**: 3 implementations (`gold_bot/`, `monitoring/`, `scripts/`)
- **SlippageModel**: 2 implementations (`core/`, `risk/`)
- **MonteCarlo**: 2 implementations (`core/`, `core/risk/`)

---

## 4. NEVER-IMPORTED MODULES

| Module | Lines | Status |
|--------|------:|--------|
| `alpha/` | ~535 | **DEAD** — never imported anywhere |
| `cost/` | ~11 files | **DEAD** — never imported |
| `data_pipeline/` | ~17 files | **DEAD** — never imported |
| `events/` | ~15 files | **DEAD** — never imported |
| `expansion/` | ~12 files | **DEAD** — never imported |
| `live_readiness/` | ~8 files | **DEAD** — never imported |
| `micro_live/` | ~12 files | **DEAD** — never imported |
| `news_events/` | ~7 files | **DEAD** — never imported |
| `regime/` | ~13 files | **DEAD** — never imported |
| `research/` | ~2 files | **DEAD** — never imported |
| `runtime/` | ~9 files | **DEAD** — never imported |
| `_scripts/` | ~1 file | **DEAD** — never imported |
| `infra/` | ~1 file | **EMPTY** — just `__init__.py` |

**Impact**: ~100+ files, ~10,000+ lines of dead code never executed.

---

## 5. ORPHANED STANDALONE SCRIPTS

19 root-level scripts never imported:
```
check_data_count.py, check_quality.py, download_d1.py, download_mt5.py,
download_mt5_symbols.py, download_xauusd_multi_tf.py, launch_7day.py,
quarantine_manager.py, run_backtest.py, run_backtest_real.py,
run_labeling.py, run_ml_train.py, run_paper_trading.py, run_scheduled.py,
run_shadow.py, tasks.py, test_shadow.py, test_smoke_overfitting.py,
verify_bootstrap.py
```
**~3,276 lines of dead code.**

---

## 6. ARCHITECTURE ISSUES BY SEVERITY

### P0 — CRITICAL (Must fix before any new architecture)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | **8/9 scripts have incomplete EXCLUDE_COLS** | scripts/*.py | Models train on leakage → 100% fake accuracy |
| 2 | **3 scripts use raw OHLCV as features** | train_strategy, regime_filter, diagnose_regime_accuracy | Model memorizes absolute price levels |
| 3 | **No purge/embargo in walk_forward** | walk_forward.py:180 | Train/test overlap → look-ahead bias |
| 4 | **Regime detector fed equity returns, not market returns** | backtest/engine.py:597 | Regime learns strategy PnL, not market state |
| 5 | **5+ competing RegimeDetector implementations** | regime/, validation/, alpha/, core/ | No single source of truth for regime |
| 6 | **10+ competing DSR implementations** | validation/, core/, scripts/ | Different results from different DSRs |
| 7 | **No shared feature generation** | build_features, ml/pipeline, engine._calculate_indicators | 4 separate feature generators with different sets |
| 8 | **Backtest ≠ live code path** | strategies/ vs autonomous/ vs gold_bot/ | Validated strategy runs different code in live |
| 9 | **Execution/manager.py:295 undefined logger** | execution/manager.py | Runtime crash on any SL-less order |
| 10 | **19 never-imported modules** | alpha/, cost/, data_pipeline/, events/, etc. | ~10K+ lines of dead code |

### P1 — HIGH (Fix within first 2 weeks)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 11 | **MT5 password visible in process list** | start_bot.ps1:9 | Any user/malware can read it |
| 12 | **Telegram bot token in loggable URLs** | 4+ files | Anyone with logs can steal token |
| 13 | **All 15 secrets in single .env** | .env | One leak = total compromise |
| 14 | **core ↔ api circular dependency** | core/tv_integration.py ↔ api/ | Lazy loading workaround hides the issue |
| 15 | **OrderStatus has 2 parallel state machines merged** | core/enums.py | Source of confusion and bugs |
| 16 | **RiskPolicy reconstructed on every env override** | core/config.py | DRY violation, fragile when fields added |
| 17 | **api/signal_service.py duplicates config via os.getenv** | api/signal_service.py | Parallel config path, no QuantConfig |
| 18 | **fill_model.simulate_entry ignores spread parameter** | execution/fill_model.py | Dead parameter, misleading interface |
| 19 | **auto_retrain.py uses raw pickle for save** | scripts/auto_retrain.py | Bypasses safe_load_model validation |
| 20 | **mr.rb uses datetime.now() in signal generation** | strategies/mrb.py | Breaks deterministic backtesting |

### P2 — MEDIUM (Fix within first month)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 21 | **backtest/engine.py is 1,467 lines** | backtest/engine.py | God module, needs decomposition |
| 22 | **scripts/tsm_paper_trade.py is 1,634 lines** | scripts/ | Largest script, likely god module |
| 23 | **gold_bot/ is semi-autonomous** | gold_bot/ (47 files) | Separate architecture, not integrated |
| 24 | **45+ duplicate filenames** | across codebase | Confusion, copy-paste drift |
| 25 | **50+ duplicate class names** | across codebase | Semantic duplicates |
| 26 | **15+ duplicate walk_forward implementations** | scripts/ | Different purge, different results |
| 27 | **8 duplicate build_features implementations** | scripts/ | Different feature sets per script |
| 28 | **ticks/ is orphaned test mirror** | ticks/ | Dead directory |
| 29 | **infra/ is empty module** | infra/ | Dead directory |
| 30 | **24 skipped/quarantined tests** | tests/ | Untested code paths |

---

## 7. CODE QUALITY SCORE

| Category | Score | Evidence |
|----------|-------|---------|
| **Architecture** | 3/10 | 45+ modules, 19 dead, 5 competing regime detectors, 10+ DSR |
| **Duplication** | 2/10 | 50+ duplicate class names, 15+ walk_forward, 9 get_feature_cols |
| **Test Coverage** | 4/10 | 24 skipped tests, 19 never-imported modules untested |
| **Type Safety** | 5/10 | Mostly typed, but `Any` in critical paths, inconsistent style |
| **Security** | 3/10 | 6 CRITICAL vulns, secrets in process list, .env single point |
| **Error Handling** | 6/10 | Kill switch works, golden rules enforced, but silent failures exist |
| **Documentation** | 6/10 | Good docstrings in core modules, but no architecture docs |
| **Consistency** | 3/10 | 4 different config systems, 4 feature generators, inconsistent naming |
| **Dead Code** | 2/10 | ~10K+ lines dead, 19 orphaned scripts, 19 never-imported modules |
| **Determinism** | 5/10 | Some n_jobs=1 fixed, but datetime.now(), global state issues remain |

**OVERALL: 3.9/10**

---

## 8. STRENGTHS (What Works)

| Component | Why It Works |
|-----------|-------------|
| **RiskPolicy is immutable & centralized** | BPS-based, fail-closed, golden rules enforced |
| **Kill switch is persistent** | Survives restarts, Telegram control, 3 close modes |
| **Execution simulator is canonical** | No shortcut close-price fills allowed |
| **Lazy imports in core/** | Prevents circular dependency explosion |
| **Strategy base class** | Supports Optuna, Numba, hyperparameter search |
| **Golden rules are hardcoded** | Cannot be overridden by config |
| **Very few TODO/FIXME/HACK** | Only 14 markers = clean code maintenance |
| **Lean-ctx + OpenWolf tools** | 51 MCP tools for context engineering |

---

## 9. MIGRATION COMPLEXITY FOR NEW 3-STAGE

| Component | Reuse? | Migration Effort |
|-----------|--------|-----------------|
| `execution/fill_model.py` | ✅ REUSE | 0 (stays as-is) |
| `execution/execution_simulator.py` | ✅ REUSE | 0 |
| `execution/manager.py` | ✅ REUSE | 1 (fix logger crash) |
| `risk/kill_switch.py` | ✅ REUSE | 0 |
| `risk/circuit_breaker.py` | ✅ REUSE | 0 |
| `risk/risk_policy.py` | ✅ REUSE | 0 |
| `core/config.py` | ⚠️ EXTEND | 3 (add vol/regime config) |
| `core/enums.py` | ⚠️ EXTEND | 2 (add 4-class RegimeType) |
| `strategies/ensemble.py` | ⚠️ REUSE PATTERN | 4 (adapt for factor combination) |
| `risk/position_sizer_v2.py` | 🔄 REWRITE | 7 (vol-targeted sizing) |
| `risk/pre_trade_risk.py` | ⚠️ EXTEND | 3 (add regime gate) |
| `backtest/engine.py` | ⚠️ EXTEND | 5 (integrate vol/regime/signal) |
| `ml/pipeline.py` | 🔄 REWRITE | 7 (target: vol + regime, not direction) |
| `strategies/mtm/mrb/mlb` | 🔄 REPLACE | 6 (replace with TSMOM + Carry + Pairs) |
| `scripts/walk_forward.py` | 🔄 REWRITE | 5 (add purge/embargo, multi-asset) |
| `scripts/build_features.py` | 🔄 REWRITE | 6 (vol features, regime labels, cross-asset) |
| ALL regime detectors | 🔄 CONSOLIDATE | 8 (merge 5 into 1) |
| ALL DSR implementations | 🔄 CONSOLIDATE | 4 (use canonical validation/deflated_sharpe.py) |
| HAR model | ❌ BUILD NEW | 8 (from scratch) |
| TSMOM signal | ❌ BUILD NEW | 5 |
| Carry signal | ❌ BUILD NEW | 5 |
| Pairs MR signal | ❌ BUILD NEW | 6 |
| Cross-asset features | ❌ BUILD NEW | 7 |
| Vol-targeted sizing | ❌ BUILD NEW | 6 |

**Overall migration**: ~70% rewrite, ~30% reuse. Estimated 8-12 weeks for a focused team.

---

## 10. TOP 5 IMMEDIATE ACTIONS

1. **Create `core/feature_config.py`** — single `EXCLUDE_COLS` constant, import everywhere. Kills 8/9 inconsistent exclusions.
2. **Add purge/embargo to walk_forward** — minimum 7-bar gap between train/test. Kills look-ahead bias.
3. **Consolidate regime detectors** — merge 5 into 1 authoritative 4-class classifier in `core/`.
4. **Consolidate DSR** — use `validation/deflated_sharpe.py` everywhere, delete the other 9.
5. **Delete dead code** — remove 19 orphaned scripts, 19 never-imported modules, ticks/ directory.

---

*Generated by 3 parallel agents: Module Map, Orphan Hunter, Core Architecture Analysis*
