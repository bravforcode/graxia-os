# Master Gap Report — GRAXIA-TSM Unified Mega Remediation Plan

**Date:** 2026-07-01
**Method:** 8 subagents dispatched in parallel (security, data, ml, execution, risk, ops, test, reviewer). Coordinator aggregated.
**Mode:** Read-only domain mapping. No files modified by subagents.

---

## 0. Executive Summary

**Current verdict: `NO_GO` for live trading. Confirmed by codebase evidence.**

The plan's strategic framing is sound — security → data → risk → parity → ML → edge → ops → paper → live ordering is correct. However, **3 must-fix blockers** and **5 should-fix items** were identified by the reviewer-agent before Wave 0 can safely execute.

### Critical findings (cross-cutting)

1. **Circular dependency Task 2.5 ↔ Task 4.1** — hard-blocks both Wave 2 and Wave 4.
2. **~40% of plan source-facts are unverifiable** in the repo (82-issue audit, 72bps cost, MR Sharpe -2.775, 637/7320 overlap days).
3. **4 of 7 verdict gates require external dependencies** (broker, PostgreSQL, Prometheus stack, human approval) — unverifiable in local-only mode.
4. **OMS bypasses risk entirely** — `execution/oms.py` advances state machine through RISK_CHECKED with no actual risk engine call.
5. **Kill switch only blocks new orders** — does not close/hedge open positions, despite plan requirement.
6. **Circuit breaker and kill switch are completely decoupled** — CB cannot trigger KS.
7. **13+ of 24+ API endpoints have NO auth** — including `/risk/kill-switch` (critical).
8. **Overfit confirmed empirically** — train_acc≈0.89, test_acc≈0.48-0.51 across all symbols. CPCV fix exists but is dormant (only referenced from tests).
9. **No BH-FDR multiple testing correction anywhere** in the repo.
10. **Sharpe annualization uses sqrt(252) for all assets** — wrong for M15/intraday/crypto.

---

## 1. Wave-by-Wave Gap Summary

### Wave 0: Freeze and Evidence Baseline

| Task | Status | Key Finding |
|------|--------|-------------|
| 0.1 Change-control ticket | NOT STARTED | No CHANGE_CONTROL.md exists |
| 0.2 Evidence index | NOT STARTED | `reports/mega_plan_evidence/` just created; no index yet |
| 0.3 Non-secret repo scan | PARTIAL | `scripts/secret_scan.py` exists (155 lines) but coverage thin: skips test_* files, no JWT/PEM/AWS patterns, no CI integration |

### Wave 1: Security Closure — ❌ ALL TASKS FAIL ACCEPTANCE

| Task | Status | Critical Gap |
|------|--------|--------------|
| 1.1 Secret rotation | ❌ NOT MET | No rotation plan, no `SecretProvider.rotate()` API, no rotation tests |
| 1.2 Auth on endpoints | ❌ NOT MET | 13/24+ routes open. `/risk/kill-switch` fully open. `HTTPBearer` imported but never wired. Admin key uses `!=` (non-constant-time). CORS `*` + credentials=True |
| 1.3 SQL injection | ❌ NOT MET | `verify_bootstrap.py:14` CRITICAL f-string SQL with string-quoted symbol. 20+ unparameterized SQL sites. No parameterized helper. `duckdb_store.py:152` path traversal candidate |
| 1.4 Webhook replay | ❌ NOT MET | Fail-open when secret="" (webhook.py:97). No nonce/replay guard. ±60s window only. Two divergent webhook implementations with router name collision |
| 1.5 Encryption/backups | ❌ NOT MET | `scripts/backup_restore_smoke.py` does NOT EXIST. No encryption-at-rest. No KMS. Postgres volume is plaintext bind mount |

**Missing test files (hard blockers):**
- `tests/test_webhook_security.py` — MISSING
- `tests/test_bootstrap_security.py` — MISSING

### Wave 2: Data Truth

| Task | Status | Key Finding |
|------|--------|-------------|
| 2.1 XAUUSD_D1 quarantine | ❌ NOT STARTED | XAUUSD_D1 has 20,300 rows from 1793. 441 OHLC violations, 716 gaps confirmed in `reports/data_validation.json`. Manifest is STALE (claims 5000 bars from 2007, VALIDATED, known_gaps=[]). No quarantine mechanism exists |
| 2.2 Multi-asset overlap | ❌ NOT STARTED | No overlap truth table exists. No script builds it. Warehouse partitions only cover EURUSD/GBPUSD/XAUUSD (BTCUSD/ETHUSD flat-CSV only). TSM sleeves use yfinance names (BTC_YF) vs MT5 names (BTCUSD) — coverage undocumented |
| 2.3 Feature deletion | ❌ NOT STARTED | 5 features confirmed high-NaN + 2 zero-variance: `bars_since_sweep` (98.3% NaN, zero-var), `ob_strength` (83-88% NaN, zero-var), `ob_mitigation_depth` (98.9% NaN), `ob_distance_atr` (83% NaN), `ob_age_bars` (83% NaN). Active builder still emits all of them. No deletion gate |
| 2.4 PIT macro store | ⚠️ INFRA EXISTS, NOT WIRED | `core/data/point_in_time_store.py` + `core/data/macro_features.py` with `PUBLICATION_LAG_DAYS` exist. But `build_features_v3_multi_asset.py` uses naive `reindex(method="ffill")` → 1-day FRED leak, 3-4 day COT leak. Task is rewiring, not greenfield |
| 2.5 Weekend/missing-bar | ⚠️ PARTIAL | `tsm_backtest.py` (3 sites) uses default fill_method (legacy "pad"). `tsm_paper_trade.py` uses `fill_method=None`. **CIRCULAR DEP with Task 4.1**. 88 total `pct_change` callers, no shared utility |

**Data quality per symbol (from `reports/data_validation.json`):**
- XAUUSD_D1: **FAIL** (441 OHLC violations, 716 gaps, 1793 contamination)
- EURUSD_D1: WARN (99.8% zero-volume)
- BTCUSD_D1: WARN (71.8% zero-volume, H4 has low=0.0 rows at 2010)
- ETHUSD_D1: WARN (58.6% zero-volume)
- All 4 symbols: 73/100 health score, FAILED

### Wave 3: Risk and OMS Safety — ❌ CRITICAL GAPS

| Task | Status | Critical Gap |
|------|--------|--------------|
| 3.1 Consolidate RiskPolicy | ⚠️ PARTIAL | ONE `class RiskPolicy` exists (frozen=True) ✅. But: pct alias properties still present, `position_sizer_v2.py:53` uses pct alias, `docker/paper_executor.py:37` has independent env-float, `paper_trade_config.json` uses pct floats (1.0% vs canonical 10bps), `historical_sizing_provider.py:61` takes raw bps scalar. INV-009 (pre-trade gate mandatory) UNENFORCED — no production caller requires `RiskCheckResult.approved` |
| 3.2 OMS calls pre-trade risk | ❌ CRITICAL | `OMS.submit_order` advances state machine through RISK_CHECKED with **no actual risk engine call** — hardcoded "pre-trade risk passed" reason string. `OrderManager` (manager.py) calls risk if provided, else silently skips (not fail-closed). **BTC/ETH routing bug CONFIRMED**: `VENUE_MAP["crypto"]="binance"` but other bots send BTCUSD to MT5 directly. 3 disjoint crypto paths |
| 3.3 Kill switch closes positions | ❌ NOT IMPLEMENTED | Kill switch ONLY blocks new orders. No close/hedge. No CLOSE_ALL/CLOSE_RISK_INCREASING_ONLY modes. No broker adapter integration. No reconciliation. Pre-trade gate also ignores PAUSED and per-asset-class kill states |
| 3.4 Circuit breaker integration | ❌ NOT IMPLEMENTED | CB and KS completely decoupled. CB.trip() never activates KS. Manual CB reset has no auth/reason/audit. Pre-trade gate doesn't even import CB |
| 3.5 Order lifecycle tests | ❌ MISSING | `tests/test_oms_order_lifecycle.py` DOES NOT EXIST. `test_execution.py` covers submit/fill/cancel/idempotency-key only. Missing: broker reject, partial fill, close, restart reconciliation |

**Constitution violations found:**
- INV-009 (pre-trade gate mandatory): ❌ UNENFORCED
- INV-010 (contract fail-closed): ❌ `require_contract_snapshot` flag never read
- INV-011 (sizing binds to snapshot ID): ⚠️ PARTIAL — `RiskCheckResult` has no `contract_snapshot_id` field
- INV-002 (bps only): ⚠️ PARTIAL — pct aliases, env-floats, JSON pct config

### Wave 4: Backtest/Paper Parity

| Task | Status | Key Finding |
|------|--------|-------------|
| 4.1 Canonical return calc | ❌ NOT STARTED | 5 different return code paths. No shared utility. `fill_method` inconsistency confirmed. **CIRCULAR DEP with Task 2.5** |
| 4.2 Account size truth | ❌ NOT STARTED | 8+ equity sources: backtest=$10K, gold_bot=$49.8K, tsm_paper=$100K, position_manager=$10K hardcoded, portfolio_manager=$10K fallback, tasks.py=$10K, campaign=$100K, risk/engine.py divides by literal 10000 (buggy for $49.8K) |
| 4.3 Canonical cost model | ❌ NOT STARTED | Hardcoded spread/commission/slippage in BacktestConfig (2.0/3.5/0.5). No 72bps XAUUSD stress. Swap model exists but unused by engine (`enable_swap=True` is no-op). No force-flatten-before-rollover |
| 4.4 Multi-asset paper parity | ⚠️ PARTIAL | `tsm_paper_trade.py` correctly vol-target-weights 8 assets. BUT `launch_7day.py` launches `gold_bot/run_paper.py` which is 100% XAUUSD. Production paper path IS effectively 100% XAUUSD. Paper bot uses 5bps flat cost, backtest uses dynamic spread+commission — disjoint |

### Wave 5: ML and Feature Rebuild

| Task | Status | Key Finding |
|------|--------|-------------|
| 5.1 Build features_v3 | ⚠️ PARTIAL | `build_features_v3_multi_asset.py` exists (229 lines) but feature set is SMC+macro only. Missing from plan requirement: RSI14 (exists in pipeline.py), MACD (exists), BB width (exists), ATR ratio (exists), ADX (exists), **session returns (MISSING)**, **MTF alignment (MISSING)**, **MA distance (MISSING)**, **regime labels (MISSING)**. Production trainer uses only 17 basic features |
| 5.2 Purged+embargoed CV | ⚠️ INFRA EXISTS, NOT WIRED | `core/cross_validation.combine_purged_k_fold_cv` (purged=12, embargo=12) EXISTS and is tested. But `validation/walk_forward.walk_forward_split` has `embargo_bars=0` default. Production trainer uses plain chronological `iloc[:split]` with no purge/embargo → **label leakage at split boundary** (5-bar forward label) |
| 5.3 Early stopping + overfit | ❌ NOT IMPLEMENTED | No `early_stopping_rounds` anywhere. `model.fit(X_train, y_train)` with no eval_set. ModelMetadata missing: random_seed, split IDs, feature_hash, data_manifest_hash, hyperparams. `governance.MLModelRecord` has training_data_hash + feature_schema_hash but is NOT persisted by trainer. Trainer bypasses ModelRegistry entirely (direct pickle.dump) |
| 5.4 Multiple testing correction | ❌ NOT IMPLEMENTED | No Benjamini-Hochberg anywhere. Two parallel experiment registries (validation vs governance) with divergent schemas, neither persisted, neither called by trainer |
| 5.5 ML training test suite | ❌ MISSING | `tests/test_ml_pipeline_training.py` DOES NOT EXIST. `tests/test_model_training.py` DOES NOT EXIST. `tests/test_model_versioning.py` only in chaos/ (broad smoke) |

**Overfit evidence (from `ml/models/training_results.json`):**
| Symbol | train_acc | test_acc | gap |
|--------|-----------|----------|-----|
| XAUUSD | 0.892 | 0.477 | +0.42 |
| EURUSD | 0.878 | 0.492 | +0.39 |
| US30 | 0.881 | 0.494 | +0.39 |
| NAS100 | 0.896 | 0.479 | +0.42 |
| BTCUSD | 0.891 | 0.511 | +0.38 |

Test accuracy ≈ 0.48-0.51 = coin-flip on binary target. Model adds no edge.

### Wave 6: Realistic Portfolio Validation

| Task | Status | Key Finding |
|------|--------|-------------|
| 6.1 Sharpe/Sortino | ❌ NOT STARTED | `backtest/metrics._sharpe_ratio` uses fixed `sqrt(252)` for all assets. Wrong for M15 (should be ~sqrt(7776)). No CI computation. No per-asset calendar |
| 6.2 Regime filter for MR | ❌ NOT STARTED | No per-regime Sharpe attribution. MR Sharpe -2.775 NOT FOUND in any report (must be regenerated). `strategies/mrb.py` (MeanReversionBollinger) exists. Regime analyzer returns counts only, no Sharpe-by-regime |
| 6.3 Portfolio PBO/DSR | ⚠️ SKELETON | `validation/probability_overfitting.calculate_pbo` is a SIMPLIFIED PLACEHOLDER (not real CSCV). `validation/deflated_sharpe.deflated_sharpe_ratio` is real math. No portfolio-level aggregator |
| 6.4 Realistic backtest rerun | ❌ NOT STARTED | All components individually present but NOT assembled into one end-to-end runnable script |

### Wave 7: Ops and Maintainability

| Task | Status | Key Finding |
|------|--------|-------------|
| 7.1 CI/CD | ⚠️ PARTIAL | `quant_os.yml` exists (test/chaos/lint/typecheck). But: no fast-PR tier, no nightly schedule, no quant_os-scoped secret scan, release gate NOT wired into CI, typecheck non-blocking (`continue-on-error: true`), `run_release_gate.py` has hardcoded REPO_ROOT path |
| 7.2 Prometheus/Grafana | ⚠️ ARTIFACTS EXIST, NOT DEPLOYED | Two exporter implementations (redundant). Two Grafana dashboards. Alert rules YAML exists. BUT: no compose services for prometheus/grafana/alertmanager. `/metrics` endpoint not mounted in api/main.py. 4/8 required alerts missing (hung trainer, MT5 disconnect, risk denial, order reject). Runbook URLs are placeholders |
| 7.3 Correlation IDs | ⚠️ PARTIAL | `Event.trace_id` exists, canonical payloads have trace_id. BUT: OMS Order has no trace_id field. EventBus doesn't bind contextvar. API has no request_id middleware. Each Event generates NEW uuid (not inherited). Structured logging not wired into api/main.py lifespan |
| 7.4 Trainer healthcheck | ❌ NOT IMPLEMENTED | No compose healthcheck on graxia-trainer. No heartbeat endpoint. No model staleness metric/alert. Primitives exist (heartbeat.py, dead_mans_switch.py) but unused for trainer |
| 7.5 DB migrations | ⚠️ FRAMEWORK EXISTS | Alembic bootstrapped (ini, env.py, 001_initial.py with 17 tables). BUT: orphaned `alembic_migration.py` duplicate. `init.sql` creates `trading.*` schema vs Alembic `quant_*` — schema drift. No CI migration job |
| 7.6 Code quality | ❌ LARGE SURFACE | `datetime.utcnow()`: ~96 calls/47 files (critical path: execution/order.py, api/webhook.py). `except Exception`: ~401/135 files. `print()` in non-script prod: ~150-300. `Any` types: several hundred. Magic strings: only 2 actual offenders. tick/ticks: confirmed inconsistency (tick/=prod, ticks/=tests — confusing but not lossy) |
| 7.7 Performance | ❌ HOTSPOTS CONFIRMED | `_safe_slope`: rolling np.polyfit per window (api/signal_service.py:329). `_log_trade`: full Parquet read+rewrite per trade (core/position_manager.py:341). Sync file writes in async endpoints (api/signal_service.py:595). Duplicate predict+predict_proba calls (3 sites). EventBus opens file on every publish |
| 7.8 Runbooks | ⚠️ THIN | `reports/RUNBOOK.md` (45 lines, quick-reference only). Missing: MT5 disconnect, stale data, DB restore, migration rollback, trainer hang, dashboard down |

### Wave 8: Paper Trade Campaign — BLOCKED by Waves 1-7

### Wave 9: Live Readiness — BLOCKED by Wave 8

---

## 2. Missing Test Files (Hard Blockers)

| Test File | Wave | Status |
|-----------|------|--------|
| `tests/test_webhook_security.py` | 1 | ❌ MISSING |
| `tests/test_bootstrap_security.py` | 1 | ❌ MISSING |
| `tests/test_oms_order_lifecycle.py` | 3 | ❌ MISSING |
| `tests/test_ml_pipeline_training.py` | 5 | ❌ MISSING |
| `tests/test_model_training.py` | 5 | ❌ MISSING |
| `tests/test_model_versioning.py` | 5 | ⚠️ Only in chaos/ (broad smoke) |

**Boilerplate tests needing conversion or quarantine:**
- `tests/test_ema_rsi.py` — script-only, import-time IO crash
- `tests/test_label_shuffling.py` — script-only, no test_* functions
- `tests/test_feature_parity.py` — substring-on-source assertions, returns silently on missing file
- `tests/test_repo_hooks.py` — only negative path tested
- `loadtests/test_throughput.py` — `run()` not `test_*`, not collected by pytest

**Test config issue:** `testpaths = ["tests"]` excludes ~90+ module-local tests in cost/, regime/, shadow/, oracle/, micro_live/, events/, ticks/, canary/, etc.

---

## 3. Plan Defects (from Reviewer-Agent)

### Must-fix before Wave 0 (blocking)

1. **Circular dependency Task 2.5 ↔ Task 4.1.** Both explicitly depend on each other. Recommended fix: move Task 2.5 into Wave 4 as Task 4.0 (missing-bar policy is a parity concern). Keep Task 4.1 dependency on new 4.0.

2. **Externally-sourced "82-issue audit" unverifiable.** 5 of 12 verified assumptions are unconfirmable in repo (Sharpe 1.073→0.794, 72bps cost, MR Sharpe -2.775, 82-issue audit, 637/7320 overlap). Either import the user's audit file into `Meta/` or re-state §1.3 as "user-supplied, unverifiable — Task 0.4 will reproduce."

3. **No task for audit items 1-31.** Plan only re-scans them (Task 0.3). Need Task 0.4: Triage items 1-31 into existing tasks or create stubs.

### Should-fix before Wave 0 (de-risk)

4. **ob_strength NaN figure wrong in plan:** plan says ~17%, audit shows 83-88% NaN. Fix prevents mis-prioritizing.

5. **Classify each gate by external dependency** (local / broker / DB / human) so local-only dev knows which gates need escalation.

6. **Map wave exit gates to canonical 5-verdict vocabulary** (PASS_TO_NEXT_PHASE, CONDITIONAL_PASS, NO_GO, ARCHIVE_NO_EDGE, INSUFFICIENT_SAMPLE).

7. **Add per-wave file-ownership matrix** to prevent parallel-agent contention on execution/oms.py, risk/kill_switch.py, core/event_bus.py (each claimed by ≥2 tasks).

8. **Task 3.2 must explicitly retire legacy pre-trade path** in execution/manager.py:115-116, not just add new gate alongside.

---

## 4. What Already Works (Don't Rebuild)

These are confirmed good — leverage them:

- **RiskPolicy frozen dataclass** — one canonical class, @dataclass(frozen=True), bps-based
- **SMC detectors** — `core/smc_detectors.py` tested, swing high/low has real signal
- **CPCV implementation** — `core/cross_validation.combine_purged_k_fold_cv` (purged=12, embargo=12), tested — just needs WIRING into trainer
- **Deflated Sharpe math** — `validation/deflated_sharpe.deflated_sharpe_ratio` is real
- **PointInTimeStore** — `core/data/point_in_time_store.py` with as_of filtering, publication lag — just needs WIRING into feature builder
- **MTF cursor** — `backtest/mtf_cursor.py` with slice_as_of for PIT multi-TF
- **AccountSnapshot** — `live_readiness/account_snapshot_service.py` frozen dataclass with SHA-256 hash — just needs WIRING into sizer
- **Event trace_id** — `core/events.py` Event.trace_id + canonical payloads — needs API middleware + OMS Order.trace_id field
- **Alembic framework** — env.py + 001_initial.py with 17 tables — needs CI job + duplicate cleanup
- **Structured logging infra** — `monitoring/structured_formatter.py` + `core/observability.py` — needs api/main.py lifespan wiring
- **Prometheus exporters** — two implementations exist — needs compose services + consolidation
- **Test infrastructure** — pytest configured, asyncio_mode=auto, 175+ test files — needs testpaths expansion + missing test authoring

---

## 5. Recommended Execution Order (Revised from Plan §17)

Based on gap analysis, the plan's first-10-commits order is mostly correct but needs adjustment:

1. **Fix plan defects** (circular dep, audit import, Task 0.4) — coordinator only, no code change
2. **Task 0.1:** Create CHANGE_CONTROL.md
3. **Task 0.2:** Build evidence index
4. **Task 0.3:** Expand secret scan coverage
5. **Task 3.1:** Consolidate RiskPolicy (remove pct aliases, fix docker/paper_executor, fix config JSON)
6. **Task 3.2:** Wire OMS to risk pre-check (fail-closed) + fix BTC/ETH routing to MT5
7. **Task 3.3:** Kill switch close-open-position policy
8. **Task 1.2:** Auth on all endpoints (parallel with 3.x after Phase 0)
9. **Task 2.1:** Quarantine XAUUSD_D1
10. **Task 4.1+2.5 (merged):** Canonical return calculation + missing-bar policy

---

## 6. External Dependency Map

| Gate | Local? | Broker? | DB? | Human? |
|------|--------|---------|-----|--------|
| Security | ✅ | ❌ | ✅ (restore test) | ✅ (rotation approval) |
| Data | ✅ | ⚠️ (if raw data needs download) | ❌ | ❌ |
| Risk/Execution | ✅ | ✅ (kill switch drill) | ❌ | ❌ |
| Parity | ✅ | ❌ | ❌ | ❌ |
| ML | ✅ | ❌ | ❌ | ❌ |
| Edge | ✅ | ❌ | ❌ | ❌ |
| Ops | ✅ | ❌ | ✅ (migration CI) | ❌ |
| Paper | ❌ | ✅ (demo orders) | ❌ | ✅ (credential approval) |
| Final | ✅ | ❌ | ❌ | ✅ (human review) |

**Local-only environment can reach: Security (partial), Data, Parity, ML, Edge.**
**Cannot fully verify: Risk/Execution (kill switch drill), Ops (migration CI), Paper, Final.**

---

## 7. Subagent Reports Index

| Agent | Domain | Key Output |
|-------|--------|------------|
| security-agent | Wave 1 | 13/24+ routes open, fail-open webhook, 20+ SQLi sites, no backup script |
| data-agent | Wave 2 | XAUUSD_D1 20,300 rows from 1793, manifest stale, PIT infra exists but bypassed, 5 bad features confirmed |
| ml-agent | Wave 5+6 | Overfit confirmed (train 0.89/test 0.48), CPCV dormant, no early stopping, no BH-FDR, Sharpe sqrt(252) wrong |
| execution-agent | Wave 3+4 | OMS bypasses risk, 3 disjoint crypto paths, 5 return code paths, $10K vs $49.8K vs $100K equity mismatch |
| risk-agent | Wave 3 | One frozen RiskPolicy but pct aliases + parallel policies, kill switch blocks-only, CB/KS decoupled, INV-009/010 unenforced |
| ops-agent | Wave 7 | CI exists but no fast tier/nightly, Prometheus artifacts exist but not deployed, 96 utcnow calls, 401 except Exception |
| test-agent | cross-cutting | 6 missing test files (hard blockers), 5 boilerplate tests, testpaths excludes 90+ module-local tests |
| reviewer-agent | plan review | 1 circular dep (2.5↔4.1), 5 unverified claims, 3 missing scope items, plan needs revision before Wave 0 |

---

*Generated by coordinator from 8 parallel subagent reports. 2026-07-01.*
