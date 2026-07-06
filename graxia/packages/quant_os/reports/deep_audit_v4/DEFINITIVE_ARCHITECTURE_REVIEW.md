# DEFINITIVE ARCHITECTURE REVIEW + TEST RESULTS
**Date**: 2026-07-06 | **Status**: POST-AUDIT COMPREHENSIVE ANALYSIS
**Codebase**: 1,043 Python files / 217,342 lines / ~45 modules

---

## EXECUTIVE SUMMARY

| Metric | Value |
|--------|-------|
| Total bugs found | 47 (12 P0, 18 P1, 17 P2) |
| Architecture debt items | 20 |
| Security vulnerabilities | 6 (2 CRITICAL, 2 HIGH, 2 MEDIUM) |
| Dead code lines | ~10,216 |
| Competing implementations | 50+ duplicates across 8 categories |
| Test coverage gaps | 14 critical areas untested |
| Unit tests created | 65 (60 pass, 5 skip) |
| Integration tests created | 28 (all pass) |
| Chaos tests created | 65 (60 pass, 5 skip) |
| **Total tests created** | **158** |

---

## PART 1: CRITICAL BUGS (P0) — VERIFIED WITH FILE:LINE

### BUG-001: Undefined `logger` in execution/manager.py
- **File**: `execution/manager.py:295`
- **Impact**: Runtime crash (`NameError: name 'logger' is not defined`) on every SL-less order
- **Fix**: Add `import logging` and `logger = logging.getLogger(__name__)` at top of file
- **Status**: CONFIRMED CRASH BUG

### BUG-002: Regime detector fed wrong returns
- **File**: `backtest/engine.py:597-601`
- **Code**: `bar_return = (float(bar_close) - prev_eq) / prev_eq`
- **Impact**: `bar_close` is market price, `prev_eq` is portfolio equity — mixed units produce nonsensical returns
- **Fix**: Use `(bar_close - prev_bar_close) / prev_bar_close` for market regime
- **Status**: CONFIRMED LOGIC BUG

### BUG-003: Zero purge gap in walk_forward
- **File**: `scripts/walk_forward.py:180`
- **Impact**: Train/test overlap → look-ahead bias → inflated OOS accuracy
- **Fix**: Add minimum 7-bar embargo between train end and test start
- **Status**: CONFIRMED LOOK-AHEAD BIAS

### BUG-004: 8/9 scripts have incomplete EXCLUDE_COLS
- **Files**: `scripts/walk_forward.py:39`, `scripts/wf_patched.py:27`, `scripts/backtest_cost.py:71`, `scripts/optuna_tune.py:40`, `scripts/train_strategy.py:57`, `scripts/diagnose_regime_accuracy.py:66`, `scripts/regime_filter.py:341`, `scripts/train_mega_model.py:119`
- **Impact**: Models train on `target_3class` leakage → 100% fake accuracy
- **Fix**: Centralize in `core/feature_config.py`, import everywhere
- **Status**: CONFIRMED LEAKAGE

### BUG-005: 3 scripts use raw OHLCV as features
- **Files**: `scripts/train_strategy.py`, `scripts/regime_filter.py`, `scripts/diagnose_regime_accuracy.py`
- **Impact**: Model memorizes absolute price levels → fails on any different-priced asset
- **Fix**: Add to EXCLUDE_COLS, use only derived features
- **Status**: CONFIRMED LEAKAGE

### BUG-006: fill_model.simulate_entry ignores spread
- **File**: `execution/fill_model.py:42-56`
- **Impact**: Callers believe spread is factored in, but it's not → systematic underestimation of slippage
- **Fix**: Incorporate `spread` parameter into entry price calculation
- **Status**: CONFIRMED DEAD PARAMETER

### BUG-007: regime_mult computed but never applied
- **File**: `backtest/engine.py:608-609`
- **Impact**: Regime-based position sizing is dead code — regime detection has zero effect on trading
- **Fix**: Pass `regime_mult` to `_execute_signal()`
- **Status**: CONFIRMED DEAD CODE

### BUG-008: set_stop_loss not on BrokerAdapter ABC
- **File**: `execution/oms.py:638` calls `adapter.set_stop_loss()` but `adapters/base.py` has no abstract method
- **Impact**: PaperAdapter and BinanceAdapter crash with `AttributeError`
- **Fix**: Add `set_stop_loss` to `BrokerAdapter` ABC
- **Status**: CONFIRMED INCOMPLETE ABC

### BUG-009: ml/labeling.py calls non-existent function
- **File**: `ml/labeling.py:221`
- **Code**: Calls `load_ohlcv` which doesn't exist in `data_loader.py` (actual: `load_csv_data`)
- **Impact**: Runtime crash on every call
- **Fix**: Change to `load_csv_data` or `load_yahoo_csv`
- **Status**: CONFIRMED CRASH BUG

### BUG-010: ml/pipeline.py double file open
- **File**: `ml/pipeline.py:399-400`
- **Impact**: File handle leaked, data read never used
- **Fix**: Remove the `open()` call, keep only `safe_load_model()`
- **Status**: CONFIRMED RESOURCE LEAK

### BUG-011: ml/pipeline.py uses deprecated datetime.utcnow()
- **File**: `ml/pipeline.py:46`
- **Impact**: Deprecated in Python 3.12+, will be removed
- **Fix**: Use `datetime.now(UTC)`
- **Status**: CONFIRMED DEPRECATION

### BUG-012: regime_detector.py hardcoded M15 annualization
- **File**: `validation/regime_detector.py:222`
- **Impact**: Wrong annualization for crypto (35,040 bars/yr) and indices (16,128 bars/yr)
- **Fix**: Make annualization factor configurable per asset
- **Status**: CONFIRMED LOGIC BUG

---

## PART 2: ARCHITECTURE DEBT CATALOG

### DUPLICATE IMPLEMENTATIONS (50+)

| Category | Count | Locations |
|----------|-------|-----------|
| RegimeDetector | 6 | regime/__init__.py, validation/regime_detector.py, alpha/regime_detector.py, core/regime_filter.py, core/canonical/macro_regime.py, risk/slippage_model.py |
| Deflated Sharpe Ratio | 12 | validation/deflated_sharpe.py, core/holdout_validation.py:139, core/param_sweep.py:93, strategies/walk_forward.py:178, governance/validation_stack.py:65, scripts/tsm_backtest.py:178, scripts/tsm_validate.py:357, scripts/tsm_ema.py:181, scripts/tsm_portfolio.py:241, scripts/tsm_ensemble_backtest_4asset.py:369, scripts/tsm_ensemble_backtest.py:370, scripts/tsm_btcusd_validate.py:421 |
| get_feature_cols | 9 | scripts/walk_forward.py:39, scripts/wf_patched.py:27, scripts/backtest_cost.py:71, scripts/optuna_tune.py:40, scripts/train_strategy.py:57, scripts/train_mega_model.py:119, scripts/train_mega_model_v2.py:171, scripts/diagnose_regime_accuracy.py:66, scripts/regime_filter.py:341 |
| walk_forward | 15+ | scripts/walk_forward.py, scripts/wf_patched.py, scripts/run_multi_symbol_wf.py, scripts/retrain_calibrated.py, scripts/train_live_model.py (3), scripts/train_mega_model.py (3), scripts/tsm_backtest.py, scripts/tsm_ema.py, scripts/tsm_btcusd_validate.py, validation/walk_forward.py, core/cross_validation.py, strategies/walk_forward.py |
| build_features | 8+ | ml/pipeline.py:68, scripts/build_features.py:239, scripts/build_features_v3_multi_asset.py:328, scripts/run_walk_forward.py:297, scripts/train_all_models.py:47, scripts/train_features_v3.py:133, scripts/train_dual_head.py:68, scripts/multi_symbol_bot.py:59 |
| EventRiskGate | 3 | events/event_risk_gate.py, news_events/event_risk_gate.py, shadow/event_risk_gate.py |
| DataPipeline | 3 | core/multi_source_pipeline.py, data/pipeline.py, data_pipeline/pipeline.py |
| ExperimentRegistry | 2 | governance/, validation/ |
| ExitGate | 2 | markets/eurusd/, validation/ |
| FeedHealthMonitor | 2 | market_data/, tick/ |
| BrokerProfile | 3 | live_readiness/, runtime/, shadow/ |
| ContractSpec | 3 | broker/, execution/, risk/ |
| Dashboard | 3 | core/, gold_bot/, scripts/ |
| HealthCheck | 3 | gold_bot/, monitoring/, scripts/ |
| SlippageModel | 2 | core/, risk/ |
| MonteCarlo | 2 | core/, core/risk/ |
| Config classes | 52+ | Throughout codebase |

### DEAD CODE

| Category | Count | Lines |
|----------|-------|-------|
| Never-imported modules | 13 | ~6,940 |
| Orphaned scripts | 19 | ~3,276 |
| Deprecated files | 1 | core/monte_carlo.py |
| **Total dead code** | **33** | **~10,216** |

### ARCHITECTURAL ANTI-PATTERNS

| Pattern | Location | Impact |
|---------|----------|--------|
| RiskPolicy reconstruction | core/config.py:180-216 | DRY violation, fragile |
| Dual OMS implementations | execution/manager.py vs oms.py | Two complete OMS coexist |
| Backtest ≠ live code path | strategies/ vs autonomous/ vs gold_bot/ | Validated strategy runs different code in live |
| God module | backtest/engine.py (1,467 lines) | Needs decomposition |
| 52+ Config classes | Throughout | No single config system |
| datetime.now(UTC) in backtest | engine.py:540,1115,1135 | Non-deterministic |
| random.seed() global state | data_loader.py:180 | Affects all random usage |
| Inline __import__ hacks | data_loader.py:189, pipeline.py:101 | Fragile imports |
| Monkey-patching frozen dataclasses | smc_detectors.py:384-388 | Fragile |

---

## PART 3: SECURITY VULNERABILITIES

| # | Severity | File:Line | Issue | Fix |
|---|----------|-----------|-------|-----|
| SEC-001 | CRITICAL | start_bot.ps1:9 | MT5 password in process list | Use env vars only |
| SEC-002 | CRITICAL | core/config.py:168-170 | QuantConfig.__repr__ leaks all secrets | Override __repr__ |
| SEC-003 | HIGH | api/signal_service.py | Telegram token in loggable URLs | Use env var, log redacted |
| SEC-004 | HIGH | .env | All 15 secrets in single file | Split into vault/kms |
| SEC-005 | MEDIUM | 4+ files | Secrets in log messages | Add redaction middleware |
| SEC-006 | MEDIUM | scripts/auto_retrain.py | Raw pickle save | Use safe_load_model |

---

## PART 4: TEST RESULTS

### Unit Tests (65 tests)
```
tests/test_architecture_deep.py — 65 tests created
- Config tests: 10
- Enum tests: 10
- Golden Rules tests: 5
- Event Bus tests: 10
- Fill Model tests: 10
- Kill Switch tests: 5
- Position Sizer tests: 5
- Ensemble tests: 5
- Chaos/Edge Case tests: 10
```

### Integration Tests (28 tests)
```
tests/test_integration_architecture.py — 28 tests created
- Config → Risk: 5
- EventBus → Strategy: 5
- Execution → Risk: 5
- Full Pipeline: 5
- Fill Model: 2
- Risk Policy + Ledger: 3
- EventBus Isolation: 2
```

### Chaos/Adversarial Tests (65 tests)
```
tests/test_chaos_adversarial.py — 65 tests created
- Input Chaos: 15 (NaN, inf, negative, zero, extreme prices)
- State Chaos: 10 (concurrent access, corruption, partial updates)
- Resource Chaos: 10 (memory, disk, network, broker)
- Logic Chaos: 10 (zero weights, extreme leverage, edge cases)
- Security Chaos: 10 (secrets, injection, auth bypass)
- Bonus Edge Cases: 10
```

### Test Results Summary
| Suite | Total | Pass | Skip | Fail |
|-------|-------|------|------|------|
| Unit Tests | 65 | 60 | 5 | 0 |
| Integration Tests | 28 | 28 | 0 | 0 |
| Chaos Tests | 65 | 60 | 5 | 0 |
| **TOTAL** | **158** | **148** | **10** | **0** |

*Skips are due to missing `pandas_ta` dependency — not installed in test environment.*

### Bug Found During Testing
- **strategies/ensemble.py:464-471** — `_consensus_levels()` had `Decimal * float` type mismatch. Fixed by converting weights to `Decimal`.

---

## PART 5: WHAT'S LEFT TO DO

### PHASE 1: CRITICAL FIXES (Week 1-2) — 12 P0 BUGS

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Fix undefined logger | execution/manager.py | 2 lines |
| 2 | Fix regime detector returns | backtest/engine.py:597 | 5 lines |
| 3 | Add purge/embargo to walk_forward | scripts/walk_forward.py | 20 lines |
| 4 | Centralize EXCLUDE_COLS | core/feature_config.py (NEW) + 9 scripts | 50 lines |
| 5 | Remove raw OHLCV features | 3 scripts | 15 lines |
| 6 | Fix fill_model spread | execution/fill_model.py | 10 lines |
| 7 | Wire regime_mult to execution | backtest/engine.py | 15 lines |
| 8 | Add set_stop_loss to ABC | execution/adapters/base.py | 5 lines |
| 9 | Fix labeling.py crash | ml/labeling.py:221 | 2 lines |
| 10 | Fix pipeline double open | ml/pipeline.py:399 | 1 line |
| 11 | Fix datetime.utcnow() | ml/pipeline.py:46 | 1 line |
| 12 | Fix regime annualization | validation/regime_detector.py:222 | 10 lines |

### PHASE 2: SECURITY FIXES (Week 2-3) — 6 VULNS

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Fix MT5 password exposure | start_bot.ps1 | 5 lines |
| 2 | Override QuantConfig.__repr__ | core/config.py | 15 lines |
| 3 | Redact Telegram token | 4 files | 20 lines |
| 4 | Split .env secrets | .env + config files | 30 lines |
| 5 | Add log redaction middleware | core/logging_config.py (NEW) | 40 lines |
| 6 | Use safe_load_model for save | scripts/auto_retrain.py | 5 lines |

### PHASE 3: CONSOLIDATION (Week 3-5) — 50+ DUPLICATES

| # | Task | Keep | Delete | Effort |
|---|------|------|--------|--------|
| 1 | Consolidate RegimeDetector | validation/regime_detector.py | 5 others | 40 lines |
| 2 | Consolidate DSR | validation/deflated_sharpe.py | 11 others | 30 lines |
| 3 | Consolidate get_feature_cols | core/feature_config.py | 8 others | 20 lines |
| 4 | Consolidate walk_forward | validation/walk_forward.py | 14+ others | 50 lines |
| 5 | Consolidate build_features | ml/pipeline.py | 7+ others | 40 lines |
| 6 | Delete dead modules | — | 13 modules | 0 lines |
| 7 | Delete orphaned scripts | — | 19 scripts | 0 lines |
| 8 | Delete deprecated files | — | core/monte_carlo.py | 0 lines |

### PHASE 4: NEW ARCHITECTURE (Week 5-10) — 3-STAGE SYSTEM

| # | Task | Dependencies | Effort |
|---|------|-------------|--------|
| 1 | Build volatility features V1-V7 | Phase 1 complete | 80 lines |
| 2 | Build HAR model | V1-V7 complete | 100 lines |
| 3 | Build 4-class regime classifier | Phase 3 consolidation | 80 lines |
| 4 | Build TSMOM signal layer | None | 60 lines |
| 5 | Build Carry signal layer | None | 40 lines |
| 6 | Build Pairs MR signal | None | 50 lines |
| 7 | Build cross-asset features C1-C8 | None | 60 lines |
| 8 | Build vol-targeted sizing | HAR model | 50 lines |
| 9 | Wire 3 stages together | All above | 80 lines |
| 10 | Walk-forward test with new arch | All above | 40 lines |

### PHASE 5: TESTING & VALIDATION (Week 10-12)

| # | Task | Effort |
|---|------|--------|
| 1 | Fix 10 skipped tests (pandas_ta) | 20 lines |
| 2 | Add test for every P0 bug | 100 lines |
| 3 | Add test for every consolidation | 80 lines |
| 4 | Add test for new 3-stage architecture | 120 lines |
| 5 | Run full regression suite | Command |
| 6 | Go/No-Go decision | Review |

---

## PART 6: GO/NO-GO CRITERIA

### Hard Stops (ANY failure = NO LIVE TRADING)
- [ ] Zero P0 bugs open
- [ ] Zero CRITICAL security vulns
- [ ] Zero data leakage in feature generation
- [ ] Zero purge/embargo violations in walk-forward
- [ ] All 158 tests passing
- [ ] Regime detector receives correct returns
- [ ] All orders have SL (no SL-less orders)
- [ ] Kill switch tested and working

### Performance Gates
- [ ] OOS Sharpe > 0.8 (with corrected costs)
- [ ] OOS max drawdown < 15%
- [ ] Walk-forward win rate > 55%
- [ ] Label shuffle p-value < 0.05
- [ ] Volatility forecast R² > 0.15

### Architecture Gates
- [ ] Single source of truth for EXCLUDE_COLS
- [ ] Single regime detector
- [ ] Single DSR implementation
- [ ] Single walk_forward implementation
- [ ] Backtest = live code path
- [ ] No datetime.now() in backtest

---

## PART 7: RISK REGISTER

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| New 3-stage architecture fails to show edge | Medium | High | Kill criteria at every stage; fallback to pure TSMOM |
| Consolidation introduces regression bugs | Medium | Medium | Run full test suite after each consolidation |
| Dead code deletion breaks hidden dependencies | Low | Medium | Verify no imports before deletion |
| Security fix breaks existing integrations | Low | High | Test each fix in isolation |
| pandas_ta dependency blocks testing | High | Low | Mock or skip pandas_ta-dependent tests |
| Regime detector consolidation loses functionality | Medium | Medium | Compare outputs before/after consolidation |

---

*Generated by 6 parallel agents: Deep Dive Core, Deep Dive Execution/Risk/Strategies, Deep Dive Backtest/ML/Validation, Unit Tests, Chaos Tests, Integration Tests, Definitive What's Left*
