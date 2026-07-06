# DEFINITIVE "WHAT'S LEFT" REPORT — quant_os

**Date**: 2026-07-06 | **Codebase**: 1,043 Python files / 217,342 lines | **Status**: PRE-LIVE AUDIT

---

## 1. CRITICAL BUGS STILL OPEN

### BUG-001: Undefined `logger` in execution/manager.py — Runtime Crash
- **File:Line**: `execution/manager.py:295`
- **Bug**: `_submit_to_broker()` references `logger.error(...)` but `logger` is never imported or defined at module level. The `import logging` is not present in the file.
- **Impact**: Any order submitted without a stop-loss triggers `logger.error("CRITICAL: Order %s has no stop-loss — blocking submission", order.id)` → `NameError: name 'logger' is not defined`. This crashes the entire order submission flow on a safety-critical path.
- **Fix**:
  ```python
  # execution/manager.py, add at top of file after imports:
  import logging
  logger = logging.getLogger(__name__)
  ```
- **Priority**: **P0** — Safety-critical path crashes on every SL-less order

### BUG-002: `asyncio.create_task` Without Error Handling — Silent Task Loss
- **File:Line**: `execution/manager.py:154`
- **Bug**: `asyncio.create_task(self._expire_order_after_delay(...))` creates a fire-and-forget task. If the task raises an exception, it is silently lost. The `_expire_order_after_delay` method (line 446) has a try/except that catches all exceptions but only calls `_log.getLogger` (line 458), which may not be configured — and critically, the task reference is never stored.
- **Impact**: Order expiry for MICRO mode may silently fail, leaving orders in `PENDING_HUMAN` state indefinitely.
- **Fix**:
  ```python
  # Line 154: Store task reference and add callback
  task = asyncio.create_task(self._expire_order_after_delay(order.id, GOLDEN_RULES.ORDER_EXPIRY_MICRO_SECONDS))
  task.add_done_callback(lambda t: logger.warning("order_expiry_task_done") if t.exception() else None)
  ```
- **Priority**: **P1** — MICRO mode orders may never expire

### BUG-003: Regime Detector Fed Strategy Equity Returns, Not Market Returns
- **File:Line**: `backtest/engine.py:597-601`
- **Bug**: `self._regime_detector.update(bar_return, i)` where `bar_return = (float(bar_close) - prev_eq) / prev_eq`. This computes the *strategy's equity return*, not the *market return*. The regime detector learns when the strategy is winning, not what the market is doing.
- **Impact**: Regime detection is circular — it identifies "regime when strategy works" rather than actual market states. The position sizing multiplier (line 608) then amplifies this bias.
- **Fix**:
  ```python
  # Line 597-601: Use market return, not equity return
  prev_close = float(self.ohlcv_data["close"][i-1]) if i > 0 else float(bar_close)
  bar_return = (float(bar_close) - prev_close) / prev_close if prev_close > 0 else 0
  self._regime_detector.update(bar_return, i)
  ```
- **Priority**: **P0** — Regime gating is fundamentally broken in backtest

### BUG-004: RiskPolicy Reconstructed on Every Env Override — DRY Violation
- **File:Line**: `core/config.py:177-216`
- **Bug**: Each environment variable override (`RISK_PER_TRADE_PCT`, `MAX_DAILY_LOSS_PCT`, `MAX_DRAWDOWN_PCT`, `MAX_POSITIONS`) creates a new `RiskPolicy(...)` by manually copying all fields except the one being changed. Adding a new field to `RiskPolicy` requires editing 4 separate constructors.
- **Impact**: Fragile maintenance — missed fields will silently reset to defaults. The `__post_init__` validation may also not trigger correctly when policy is replaced mid-construction.
- **Fix**:
  ```python
  # Replace the 4 separate constructors with a single mutable update:
  def _apply_env_overrides(self):
      env_map = {
          "RISK_PER_TRADE_PCT": ("risk_per_trade_bps", lambda v: int(float(v) * 100)),
          "MAX_DAILY_LOSS_PCT": ("max_daily_loss_bps", lambda v: int(float(v) * 100)),
          "MAX_DRAWDOWN_PCT": ("max_total_drawdown_bps", lambda v: int(float(v) * 100)),
          "MAX_POSITIONS": ("max_open_positions", lambda v: int(v)),
      }
      kwargs = {}
      for env_key, (field, convert) in env_map.items():
          val = os.getenv(env_key)
          if val is not None:
              kwargs[field] = convert(val)
      if kwargs:
          self.risk_policy = self.risk_policy.replace(**kwargs)  # dataclasses.replace()
  ```
- **Priority**: **P1** — Maintenance hazard, silent bugs on RiskPolicy changes

### BUG-005: Walk-Forward Has Zero Purge Gap — Look-Ahead Bias
- **File:Line**: `scripts/walk_forward.py:180-184`
- **Bug**: `train_end = train_start + train_window; test_end = train_end + test_window`. There is no embargo/purge gap between training and test windows. The last training labels and first test features overlap.
- **Impact**: Feature autocorrelation bleeds from train to test. OOS accuracy is inflated because the model has seen the most recent training labels that overlap with early test features.
- **Fix**:
  ```python
  # Line 182: Add purge gap (minimum 7 bars for M15, proportional for higher TFs)
  purge_gap = 7  # Minimum gap between train and test
  test_start = train_end + purge_gap
  test_end = test_start + test_window
  ```
- **Priority**: **P0** — Walk-forward results are overfitting by construction

### BUG-006: `backtest/engine.py` Regime Update Uses Previous Equity Index
- **File:Line**: `backtest/engine.py:597-600`
- **Bug**: `prev_eq = self.equity_curve[-1].equity` — this reads from the equity curve which is updated *after* the regime check (line 617). On the first iteration, `self.equity_curve` may be empty.
- **Impact**: `IndexError` on first bar, or stale equity used for regime calculation.
- **Fix**: Guard with `if self.equity_curve:` check (already present) but also initialize with `equity_curve` having at least one entry at `_reset()`.
- **Priority**: **P1** — Edge case crash on short backtests

### BUG-007: ML Pipeline Uses `datetime.utcnow()` (Deprecated)
- **File:Line**: `ml/pipeline.py:46,318`
- **Bug**: `trained_at: datetime = field(default_factory=datetime.utcnow)` — deprecated since Python 3.12, will be removed in 3.14. Also `datetime.now(UTC)` used inconsistently.
- **Impact**: Deprecation warnings, eventual breakage on Python 3.14+.
- **Fix**: Replace all `datetime.utcnow()` with `datetime.now(UTC)`.
- **Priority**: **P2** — Future compatibility

### BUG-008: `stop_loss == 0 or stop_loss is None` — Wrong Order in position_sizer_v2.py
- **File:Line**: `risk/position_sizer_v2.py:85`
- **Bug**: `if stop_loss == 0 or stop_loss is None` — if `stop_loss` is `None`, the `== 0` comparison succeeds first in some Decimal contexts (depends on type). More importantly, the `is None` check should come first for correctness and clarity.
- **Impact**: Minor — `None` is caught either way, but wrong ordering is confusing.
- **Fix**: `if stop_loss is None or stop_loss == 0`
- **Priority**: **P3** — Code clarity

---

## 2. ARCHITECTURE DEBT CATALOG

| # | Debt Item | Location | Effort | Blocks | Priority |
|---|-----------|----------|--------|--------|----------|
| D-01 | **5+ competing RegimeDetector implementations** | `regime/`, `validation/`, `alpha/`, `core/regime_filter.py`, `core/canonical/macro_regime.py` | 8 weeks | 3-stage architecture, consistent regime gating | **P0** |
| D-02 | **10+ competing DSR implementations** | `validation/deflated_sharpe.py`, `core/holdout_validation.py`, `core/param_sweep.py`, 7+ scripts | 4 weeks | Strategy validation, reproducible results | **P0** |
| D-03 | **9 inconsistent `get_feature_cols` implementations** | `scripts/walk_forward.py:39`, `scripts/train_strategy.py:57`, `scripts/train_mega_model_v2.py:171`, etc. | 2 weeks | Feature leakage prevention, ML validity | **P0** |
| D-04 | **4 separate feature generators** | `ml/pipeline.py`, `backtest/engine.py`, `scripts/build_features.py`, `core/regime_filter.py` | 3 weeks | Consistent feature sets across backtest/live | **P1** |
| D-05 | **15+ `walk_forward` implementations** | `scripts/`, `validation/`, `core/`, `strategies/` | 3 weeks | Reproducible validation | **P1** |
| D-06 | **8 duplicate `build_features` implementations** | `scripts/build_features.py`, `scripts/build_features_v3_multi_asset.py`, etc. | 2 weeks | Feature pipeline consistency | **P1** |
| D-07 | **`backtest/engine.py` is 1,467 lines** | `backtest/engine.py` | 5 weeks | Maintainability, testability | **P2** |
| D-08 | **3 competing EventRiskGate implementations** | `events/event_risk_gate.py`, `news_events/event_risk_gate.py`, `shadow/event_risk_gate.py` | 2 weeks | Consistent event risk handling | **P2** |
| D-09 | **3 competing DataPipeline implementations** | `core/multi_source_pipeline.py`, `data/pipeline.py`, `data_pipeline/pipeline.py` | 2 weeks | Data consistency | **P2** |
| D-10 | **3 competing ContractSpec implementations** | `broker/`, `execution/`, `risk/` | 1 week | Contract consistency | **P2** |
| D-11 | **3 competing BrokerProfile implementations** | `live_readiness/`, `runtime/`, `shadow/` | 1 week | Broker config consistency | **P2** |
| D-12 | **`gold_bot/` semi-autonomous (47 files)** | `gold_bot/` | 6 weeks | Integration, no shared risk engine | **P2** |
| D-13 | **`core ↔ api` circular dependency** | `core/tv_integration.py` ↔ `api/` | 2 weeks | Import order fragility | **P2** |
| D-14 | **OrderStatus has 2 parallel state machines merged** | `core/enums.py:27-63` | 3 weeks | State confusion, bug magnet | **P2** |
| D-15 | **`api/signal_service.py` duplicates config via `os.getenv`** | `api/signal_service.py:61-65` | 1 week | Parallel config paths | **P2** |
| D-16 | **Backtest ≠ live code path** | `strategies/` vs `autonomous/` vs `gold_bot/` | 6 weeks | Live trading uses different code | **P1** |
| D-17 | **No purge/embargo in any walk_forward** | All `walk_forward` implementations | 2 weeks | Overfitting detection | **P0** |
| D-18 | **RiskPolicy has no `replace()` method** | `risk/risk_policy.py` | 0.5 weeks | Config DRY violation | **P3** |
| D-19 | **4+ competing config systems** | `core/config.py`, `gold_bot/core/config.py`, `api/signal_service.py`, `runtime/secret_provider.py` | 3 weeks | Config consistency | **P2** |
| D-20 | **2 ExperimentRegistry implementations** | `governance/`, `validation/` | 1 week | Experiment tracking | **P2** |

---

## 3. MISSING TEST COVERAGE

| # | Untested Module/Function | Risk | Priority |
|---|--------------------------|------|----------|
| T-01 | **`execution/manager.py` entire file** | No tests for order lifecycle, idempotency, human approval, broker submission, cancel flow. Risk of silent order corruption. | **P0** |
| T-02 | **`risk/pre_trade_risk.py`** | Pre-trade risk gate untested. Kill switch check, daily/weekly/drawdown limits, position count, order rate — all unverified. | **P0** |
| T-03 | **`risk/position_sizer_v2.py`** | Position sizing with portfolio exposure cap, broker-native calculation, rounding — all untested. | **P0** |
| T-04 | **`strategies/ensemble.py`** | Signal combination, weighted voting, dynamic weight adjustment, ATR fallback — no tests. | **P1** |
| T-05 | **`ml/pipeline.py` — DriftDetector** | Drift detection logic (`check_drift`) has no tests. Model staleness goes undetected. | **P1** |
| T-06 | **`core/config.py` — `_enforce_hard_limits`** | Hard limit enforcement only tested implicitly. No direct test for edge cases (exactly at limit, above limit, below limit). | **P1** |
| T-07 | **`core/config.py` — `_validate_mode_consistency`** | Mode consistency validation untested. Could allow invalid mode combinations. | **P1** |
| T-08 | **`backtest/engine.py` — `_calculate_swap_cost`** | Swap cost calculation untested. Returns 0 on failure, silently. | **P2** |
| T-09 | **`backtest/engine.py` — `_check_risk_halt`** | Risk halt (daily loss, drawdown) untested. Could allow over-trading. | **P1** |
| T-10 | **`ml/pipeline.py` — walk-forward training** | `train_walk_forward` has no test. Window slicing, OOS evaluation unverified. | **P1** |
| T-11 | **`validation/deflated_sharpe.py` — `min_backtest_length`** | Min BTL calculation untested. Could give incorrect minimum data requirements. | **P2** |
| T-12 | **`scripts/walk_forward.py` — `compute_fold_pnl`** | P&L calculation per fold untested. Dollar conversion, cost application unverified. | **P1** |
| T-13 | **24 skipped/quarantined tests** | See `tests/quarantine_manifest.json` — these are known untested paths. | **P2** |
| T-14 | **19 never-imported modules** | Zero test coverage by definition. Dead code still affects maintainability. | **P3** |

---

## 4. SECURITY VULNERABILITIES STILL OPEN

### VULN-001: Plaintext MT5 Credentials on Disk
- **File:Line**: `Meta/pepperstone_creds.txt.backup:5-6`
- **Vulnerability**: Login `61547941` and password `Graxia-12345` stored in plaintext on filesystem.
- **Exploit**: Any process with filesystem access reads the credentials directly.
- **Fix**: (1) Delete the file. (2) Rotate the password immediately. (3) Store in password manager or OS keychain only.
- **Priority**: **P0** — Active credential leak

### VULN-002: `QuantConfig` Stores Secrets in Plain String
- **File:Line**: `core/config.py:31,42-44,47`
- **Vulnerability**: `mt5_password`, `jwt_secret_key`, `webhook_hmac_secret`, `admin_api_key`, `telegram_bot_token` are all plain strings. Default `__repr__` prints all fields. Any log of `config` object leaks secrets.
- **Exploit**: `print(config)` or `logging.debug(config)` or `str(config)` in any error path outputs all secrets.
- **Fix**:
  ```python
  # Add __repr__ override to QuantConfig
  def __repr__(self):
      return f"<QuantConfig trading_mode={self.trading_mode} system_state={self.system_state}>"
  ```
- **Priority**: **P0** — Secret leak via repr

### VULN-003: SecretProvider Bypassed by Config
- **File:Line**: `core/config.py:147-216`
- **Vulnerability**: `runtime/secret_provider.py` exists with `__repr__` protection, but `config.py` reads all secrets via direct `os.getenv()` — the SecretProvider is never used.
- **Exploit**: Bypasses any future secret rotation, vault integration, or audit logging.
- **Fix**: Replace `os.getenv()` calls with `SecretProvider` instances.
- **Priority**: **P1** — Secrets infrastructure unused

### VULN-004: `api/signal_service.py` Duplicates Config via `os.getenv`
- **File:Line**: `api/signal_service.py:61-65`
- **Vulnerability**: `SYMBOL`, `LOT_SIZE`, `B2_STOP_DOLLARS`, `MIN_CONFIDENCE` all read via `os.getenv` — parallel to `QuantConfig`, no validation, no golden rules enforcement.
- **Exploit**: Environment variable manipulation bypasses all risk limits.
- **Fix**: Import and use `get_config()` instead.
- **Priority**: **P1** — Bypasses risk controls

### VULN-005: ZERO Secrets Encrypted at Rest
- **File:Line**: All `.env` files
- **Vulnerability**: No secret uses encryption at rest. No vault, no HSM, no key rotation.
- **Exploit**: Full account compromise if `.env` or filesystem is accessed.
- **Fix**: Integrate with HashiCorp Vault, AWS Secrets Manager, or Azure Key Vault.
- **Priority**: **P1** — No secret protection

### VULN-006: Docker Default Database Password
- **File:Line**: `docker-compose.yml` (DATABASE_URL)
- **Vulnerability**: `postgres:postgres` default credentials in connection string.
- **Exploit**: Anyone on the network can access the database.
- **Fix**: Use strong password, inject via environment variable.
- **Priority**: **P2** — Dev default in deployment

---

## 5. PERFORMANCE BOTTLENECKS

| # | Bottleneck | Where | Severity | Fix |
|---|-----------|-------|----------|-----|
| P-01 | **`backtest/engine.py` bar_dicts() O(n×Decimal)** | `backtest/engine.py:1290-1312` | Medium (mitigated by P2 cache) | Already cached via `_cached_bar_dicts` |
| P-02 | **Indicators computed per-bar (was O(n²))** | `backtest/engine.py:512-516` | Low (mitigated by P1 precompute) | Already fixed via `_precomputed_indicators` |
| P-03 | **RiskPolicy instantiated per-bar in backtest** | `backtest/engine.py:518-523` | Low (mitigated by P3 hoist) | Already fixed via `_risk_policy` hoist |
| P-04 | **Numba JIT fallback to pandas_ta** | `backtest/engine.py:753-778` | Medium | Ensure Numba installed for production backtests |
| P-05 | **`ml/pipeline.py` pickle.dump for model persistence** | `ml/pipeline.py:322` | Low | Already uses `safe_load_model` for loading |
| P-06 | **Feature generation imports pandas_ta inside loop** | `ml/pipeline.py:83-86` | Medium | Move imports to module level |
| P-07 | **`scripts/walk_forward.py` loads features per-symbol from disk** | `scripts/walk_forward.py:19-36` | Low | Parquet is fast, acceptable |
| P-08 | **`_calculate_indicators_pandas` creates DataFrame per call** | `backtest/engine.py:780-835` | Medium | Pre-compute once (already done in `_precomputed_indicators`) |
| P-09 | **`backtest/engine.py` spread model import inside loop** | `backtest/engine.py:885,1006,1072,1157,1274,1319` | Medium | Hoist imports to method level or cache |
| P-10 | **`risk/position_sizer_v2.py` no memoization of contract specs** | `risk/position_sizer_v2.py` | Low | `InlineContractSpec.for_symbol` already caches via dict lookup |

---

## 6. DEAD CODE TO DELETE

### 6.1 Never-Imported Modules (~10K+ lines)
| Module | Lines | Files | Reason |
|--------|-------|-------|--------|
| `alpha/` | ~535 | 3 | Never imported. Duplicates regime detection. |
| `cost/` | ~500 | 11 | Never imported. Superseded by `core/cost_model.py`. |
| `data_pipeline/` | ~1200 | 17 | Never imported. Duplicates `data/pipeline.py`. |
| `events/` | ~1000 | 15 | Never imported. Duplicates `news_events/`. |
| `expansion/` | ~700 | 12 | Never imported. Unfinished feature. |
| `live_readiness/` | ~400 | 8 | Never imported. Superseded by `live_readiness/` mirror. |
| `micro_live/` | ~600 | 12 | Never imported. Phase 9 abandoned. |
| `news_events/` | ~400 | 7 | Never imported. Duplicates `events/`. |
| `regime/` | ~700 | 13 | Never imported. Superseded by `validation/regime_detector.py`. |
| `research/` | ~100 | 2 | Never imported. One-time research scripts. |
| `runtime/` | ~500 | 9 | Never imported. Secret provider unused. |
| `infra/` | ~5 | 1 | Empty `__init__.py` only. |
| `ticks/` | ~200 | 9 | Orphaned test mirror of `tick/`. |

**Total dead modules**: ~6,940 lines across 109 files

### 6.2 Orphaned Root-Level Scripts (~3,276 lines)
```
check_data_count.py, check_quality.py, download_d1.py, download_mt5.py,
download_mt5_symbols.py, download_xauusd_multi_tf.py, launch_7day.py,
quarantine_manager.py, run_backtest.py, run_backtest_real.py,
run_labeling.py, run_ml_train.py, run_paper_trading.py, run_scheduled.py,
run_shadow.py, tasks.py, test_shadow.py, test_smoke_overfitting.py,
verify_bootstrap.py
```

### 6.3 Duplicate Implementations to Consolidate
| Original | Duplicate | Action |
|----------|-----------|--------|
| `validation/deflated_sharpe.py` | 9+ inline copies in scripts | Delete all inline copies, import from `validation/` |
| `scripts/walk_forward.py` | 14+ implementations | Keep canonical, delete duplicates |
| `scripts/build_features.py` | 7 duplicates | Keep v3, delete v1 and inlines |
| `regime/__init__.py` (orphaned) | `validation/regime_detector.py` | Consolidate to 1 in `core/` |
| `news_events/event_risk_gate.py` | `events/`, `shadow/` | Keep `events/`, delete others |
| `data/pipeline.py` | `core/multi_source_pipeline.py`, `data_pipeline/pipeline.py` | Keep `data/pipeline.py` |
| `broker/contract_spec.py` | `execution/`, `risk/` | Keep `broker/contract_spec.py` |

---

## 7. CONSOLIDATION OPPORTUNITIES

### 7.1 RegimeDetector (5 → 1)
| Location | Keep? | Reason |
|----------|-------|--------|
| `validation/regime_detector.py` | **KEEP** | Most mature, vol+correlation based |
| `core/regime_filter.py` | MERGE into above | Adds BULL/BEAR/RANGE classification |
| `regime/__init__.py` | DELETE | Orphaned, never imported |
| `alpha/regime_detector.py` | DELETE | Orphaned, never imported |
| `core/canonical/macro_regime.py` | INTEGRATE | Macro state → regime labels |

**New location**: `core/regime_detector.py` — single 4-class classifier (trending-up/down/ranging/crash)

### 7.2 Deflated Sharpe (10+ → 1)
| Location | Keep? |
|----------|-------|
| `validation/deflated_sharpe.py` | **KEEP** (canonical) |
| All inline copies in scripts | DELETE |
| `core/holdout_validation.py` DSR | DELETE, import from `validation/` |
| `core/param_sweep.py` DSR | DELETE, import from `validation/` |

### 7.3 `get_feature_cols` (9 → 1)
| Location | Keep? | Reason |
|----------|-------|--------|
| `scripts/train_mega_model_v2.py:171` | **KEEP** | Most complete exclusion set |
| All others | DELETE, import from `core/feature_config.py` | Create canonical `EXCLUDE_COLS` |

### 7.4 Walk-Forward (15+ → 2)
| Location | Keep? |
|----------|-------|
| `scripts/walk_forward.py` | **KEEP** (simplified) |
| `validation/walk_forward.py` | **KEEP** (library) |
| All script duplicates | DELETE |

### 7.5 Feature Generation (4 → 1)
| Location | Keep? |
|----------|-------|
| `scripts/build_features.py` | **KEEP** (v3 multi-asset) |
| `ml/pipeline.py FeatureEngineer` | RENAME → `core/feature_engineer.py` |
| `backtest/engine.py` indicators | KEEP (performance) |
| All script inlines | DELETE |

---

## 8. NEW ARCHITECTURE IMPLEMENTATION PLAN

### Phase 1: Foundation (Week 1-2)
| Component | Dependencies | Effort | Priority |
|-----------|-------------|--------|----------|
| **VOL-001: Volatility feature set (V1-V7)** | OHLCV data for 15 instruments | 3 days | **P0** |
| **VOL-002: HAR model with regime-switching** | V1-V7 features | 4 days | **P0** |
| **VOL-003: Risk-targeted position sizer** | `risk/position_sizer_v2.py` (extend) | 3 days | **P0** |

### Phase 2: Regime Gate (Week 3-4)
| Component | Dependencies | Effort | Priority |
|-----------|-------------|--------|----------|
| **REG-001: Regime feature set (R1-R7)** | OHLCV data | 3 days | **P0** |
| **REG-002: Cross-asset features (C1-C8)** | Multi-instrument OHLCV | 4 days | **P0** |
| **REG-003: 4-class regime classifier** | R1-R7 + C1-C8 | 4 days | **P0** |
| **REG-004: Regime-gated position controller** | REG-003 + VOL-003 | 3 days | **P0** |

### Phase 3: Signal Layer (Week 5-6)
| Component | Dependencies | Effort | Priority |
|-----------|-------------|--------|----------|
| **SIG-001: TSMOM (1M/3M/12M)** | Multi-instrument OHLCV | 3 days | **P0** |
| **SIG-002: Carry overlay** | Interest rate data | 3 days | **P1** |
| **SIG-003: Pairs mean-reversion** | Cointegration testing | 4 days | **P1** |
| **SIG-004: Microstructure features (M1-M6)** | Tick or M1 data | 3 days | **P2** |

### Phase 4: Integration (Week 7-8)
| Component | Dependencies | Effort | Priority |
|-----------|-------------|--------|----------|
| **INT-001: Wire Stage 1→2→3** | All above | 3 days | **P0** |
| **INT-002: Walk-forward test (2022-2026)** | INT-001 | 3 days | **P0** |
| **INT-003: Label shuffling** | INT-002 | 1 day | **P0** |
| **INT-004: Cost perturbation sweep** | INT-002 | 2 days | **P0** |

### Phase 5: Validation (Week 9)
| Component | Dependencies | Effort | Priority |
|-----------|-------------|--------|----------|
| **VAL-001: Go/No-Go assessment** | All above | 1 day | **P0** |
| **VAL-002: Paper trade setup** | VAL-001 pass | 3 days | **P0** |
| **VAL-003: Live readiness checklist** | VAL-002 stable | 2 days | **P1** |

**Total estimated effort**: 8-10 weeks for 1 developer, 4-5 weeks for 2 developers.

---

## 9. GO/NO-GO CRITERIA

### Must Pass ALL Before Live Trading

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| G-01 | **Volatility prediction R²** | > 0.15 | Walk-forward OOS R² per instrument |
| G-02 | **Regime classification accuracy** | > 55% | Confusion matrix on OOS data |
| G-03 | **TSMOM OOS Sharpe** | > 0.3 | Walk-forward across 2022-2026 |
| G-04 | **Integrated system OOS Sharpe** | > 0.5 | Full 3-stage walk-forward |
| G-05 | **Label shuffle p-value** | < 0.05 | 1000-shuffle permutation test |
| G-06 | **2× cost survival** | Sharpe > 0.0 | Walk-forward at 2× costs |
| G-07 | **Paper trading days** | ≥ 60 | Calendar days with 100+ trades |
| G-08 | **Paper trading win rate** | > 50% | After costs |
| G-09 | **Max drawdown (paper)** | < 15% | Hard stop from `golden_rules.py:38` |
| G-10 | **Kill switch tested** | Pass | Manual trigger + auto trigger verified |
| G-11 | **Security audit clean** | 0 P0 | All P0 vulns fixed |
| G-12 | **All critical tests passing** | 100% | `pytest tests/ -x --tb=short` |
| G-13 | **No undefined variables in critical paths** | 0 | Static analysis (mypy/pylint) |
| G-14 | **Reconciliation verified** | Pass | Broker positions match internal state |
| G-15 | **Slippage model calibrated** | Within 20% | Observed vs modeled slippage |

### Hard Stop (Auto-Kill)
| Criterion | Trigger | Action |
|-----------|---------|--------|
| Daily loss > 5% | `golden_rules.py:110` | Close all, halt |
| Drawdown > 15% | `golden_rules.py:38` | Close all, halt |
| Any order without SL | `execution/manager.py:294-298` | Reject |
| Kill switch triggered | `risk/kill_switch.py` | Close all, halt |

---

## 10. RISK REGISTER

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R-01 | **ML direction prediction continues to fail** | HIGH | HIGH | 3-stage architecture replaces ML direction with TSMOM+carry+pairs |
| R-02 | **Volatility prediction R² < 0.15** | MEDIUM | CRITICAL | Kill criteria: if vol not predictable, system stops. No vol-targeted sizing without vol prediction. |
| R-03 | **Regime detector accuracy < 55%** | MEDIUM | HIGH | Regime gate becomes optional (default multiplier=1.0). No forced regime gating. |
| R-04 | **Walk-forward overfitting (purge gap)** | HIGH | HIGH | Mandatory 7-bar purge gap. Label shuffling as validation gate. |
| R-05 | **Live ≠ backtest code path** | MEDIUM | CRITICAL | Shared execution engine. Backtest uses same fill model, same risk checks, same OMS. |
| R-06 | **Security breach via plaintext credentials** | HIGH | CRITICAL | Rotate credentials immediately. Integrate SecretProvider. Delete plaintext file. |
| R-07 | **Regime detector fed wrong data** | HIGH | HIGH | BUG-003 fix: feed market returns, not equity returns. |
| R-08 | **Walk-forward results not reproducible** | HIGH | MEDIUM | Single canonical `walk_forward.py` with purge/embargo. One `EXCLUDE_COLS` constant. |
| R-09 | **Position sizer exceeds risk limits** | LOW | CRITICAL | `pre_trade_risk.py` gate already exists. Needs testing (T-02). |
| R-10 | **Order manager crashes on SL-less order** | HIGH | HIGH | BUG-001 fix: add `logger` import. Already rejects (line 294-298). |
| R-11 | **Cost model underestimates real costs** | MEDIUM | HIGH | Cost perturbation sweep (INT-004). Walk-forward includes realistic costs. |
| R-12 | **MT5 connection drops during live trading** | MEDIUM | HIGH | `BrokerManager` has health check (line 301). Reconnection logic exists in adapter. |
| R-13 | **Feature leakage in ML pipeline** | HIGH | CRITICAL | Single `EXCLUDE_COLS` in `core/feature_config.py`. Purge gap mandatory. |
| R-14 | **Backtest engine god module (1467 lines)** | MEDIUM | MEDIUM | Decompose into: indicator calc, execution, risk check, reporting. |
| R-15 | **`gold_bot/` operates independently** | HIGH | HIGH | Integrate with main risk engine. Shared OMS, shared kill switch. |

---

## SUMMARY: PRIORITY ACTION LIST

### Immediate (This Week)
1. **Fix BUG-001**: Add `logger` to `execution/manager.py`
2. **Fix BUG-003**: Feed market returns to regime detector in `backtest/engine.py`
3. **Fix VULN-002**: Add `__repr__` override to `QuantConfig`
4. **Fix VULN-001**: Delete `Meta/pepperstone_creds.txt.backup`, rotate password
5. **Create `core/feature_config.py`**: Single `EXCLUDE_COLS` constant

### Week 1
6. **Add purge gap to walk_forward** (BUG-005)
7. **Consolidate regime detectors** to single implementation
8. **Add tests for `execution/manager.py`** (T-01)
9. **Add tests for `risk/pre_trade_risk.py`** (T-02)
10. **Delete dead modules** (6.1 list above)

### Month 1
11. **Consolidate DSR implementations** (10+ → 1)
12. **Consolidate walk_forward** (15+ → 2)
13. **Fix config DRY violation** (BUG-004)
14. **Integrate SecretProvider** (VULN-003)
15. **Decompose backtest engine** (D-07)

### Quarter 1
16. **Build volatility engine** (VOL-001 to VOL-003)
17. **Build regime gate** (REG-001 to REG-004)
18. **Build signal layer** (SIG-001 to SIG-003)
19. **Integration testing** (INT-001 to INT-004)
20. **Go/No-Go assessment** (VAL-001)

---

*Generated from comprehensive analysis of 14 core files + architecture review + security audit + codebase search across 1,043 Python files.*
