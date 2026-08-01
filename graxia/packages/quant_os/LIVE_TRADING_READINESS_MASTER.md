# LIVE TRADING READINESS — HONEST MASTER LIST

**Date**: 2026-07-12
**Status**: SUPERSEDED (2026-07-28) — see note below
**Audit Scope**: Deep audit across 23/28 phases, walk-forward validation on 13 instruments

---

> **⚠️ SUPERSEDED 2026-07-28:** This document predates `MEGA_PLAN_v2_Quant_OS_Live_Readiness.md`
> (2026-07-20+) and was never previously part of any declared supersession
> chain — a gap flagged as F25 in that document. Preserved for historical
> reference (its instrument-level findings, e.g. XPDUSD/XPTUSD cost-model
> issues, may still be independently useful evidence), but its own
> checklist/status should not be treated as the current live-readiness
> gate. Follow `MEGA_PLAN_v2_Quant_OS_Live_Readiness.md` going forward.

---

## Executive Summary

**The system is NOT ready for live trading.** Here is why:

1. **No instrument has confirmed edge after real costs.** Walk-forward validation with measured Pepperstone spreads shows XPDUSD/XPTUSD edge disappears at D1 (REJECT). H1/M15 results used default costs that were 100x too low.
2. **47 Critical + 31 High findings** from the deep audit remain unaddressed.
3. **Core infrastructure has stubs/placeholders** in execution, reconciliation, and monitoring.
4. **Paper trading campaign has not been run** (Golden Rule #3 requires 60 days / 100 trades minimum).
5. **Multiple testing correction not applied** to any validation results.

---

## CATEGORY A: PROVEN EDGE (BLOCKING — nothing else matters without this)

### A1. Multi-Day Spread Sampling
- [ ] Run `measure_spread.py` for **XAUUSD, XPDUSD, XPTUSD** for **7+ days** to get proper min/max/p95 statistics
- [ ] Single-snapshot measurements are unreliable — XAUUSD=0.36 bps, XPDUSD=55.35 bps, XPTUSD=45.29 bps were all single-snapshots
- [ ] Measure spreads during Asian, London, and NY sessions separately
- [ ] Update `config/cost_calibration.json` with multi-day statistics

### A2. Re-Run Walk-Forward With Measured Costs
- [ ] Re-run XPDUSD/XPTUSD on H1, M15, D1 with **actual measured costs** (not defaults)
- [ ] The H1/M15 "PROMOTE" verdicts used costs that were ~100x too low
- [ ] **No instrument should be promoted until this is done**

### A3. Strategy Edge Validation
- [ ] None of the 6 forex pairs have edge after costs — confirmed REJECT/INCONCLUSIVE
- [ ] XAUUSD is the only instrument with a proven track record — **but was NOT included in the 13-instrument WF batch and needs re-validation**
- [ ] Need to confirm XAUUSD edge survives with updated cost calibration
- [ ] Run walk-forward on XAUUSD with current measured costs (0.36 bps spread — single snapshot, needs multi-day first)

### A4. Walk-Forward Parameters
- [ ] Run PBO (Probability of Backtest Overfitting) — must be < 0.5
- [ ] Run Deflated Sharpe Ratio — must be > 0
- [ ] Apply multiple testing correction across all instruments tested
- [ ] Verify minimum 3 walk-forward windows per instrument

---

## CATEGORY B: CRITICAL BUGS & MISSING INFRASTRUCTURE

### B1. Execution Layer (5 Critical)
- [ ] **`execution/position_reconciler.py`**: "not wired to real-time monitoring" — orphan positions undetected
- [ ] **`execution/oms.py`**: exit_price="" placeholder pattern — not filled after broker execution
- [ ] **`execution/manager.py`**: Stop-loss check is a hard block but no auto-retry if MT5 rejects
- [ ] **`api/orders.py`**: "For now, return placeholder" in order creation response
- [ ] **`risk/position_sizer_v2.py`**: "Basic margin check (placeholder)" — Step 9 not implemented

### B2. Kill Switch & Safety (3 Critical)
- [ ] **`api/telegram_commands.py`**: Multiple `pass` blocks — Telegram /kill and /resume may not work
- [ ] **`risk/kill_switch.py`**: State file corruption handling exists but no auto-recovery tested
- [ ] **`core/state_coordinator.py`**: 5 separate kill-switch stores — sync failure between them not tested

### B3. Monitoring & Alerting (3 Critical)
- [ ] **`monitoring/alerts.py`**: `AlertManager.send_alert()` has empty routing blocks — **ALL alerts silently dropped** ⚠️ THIS IS A LIVE-TRADING BLOCKER — kill-switch triggers, position losses, and P0 incidents would produce zero notifications
- [ ] **`monitoring/heartbeat_monitor.py`**: 1-hour stale threshold vs DeadMansSwitch 5-minute threshold — inconsistency
- [ ] **No Prometheus metrics validation** that alerts actually fire end-to-end

### B4. ML Lifecycle (2 Critical)
- [ ] **`scripts/auto_retrain.py`**: `evaluate_model()` returns **dummy metrics** — champion/challenger comparison non-functional
- [ ] **`ml/pipeline.py`**: Missing `np.random.seed()` — feature values may vary across runs

---

## CATEGORY C: MISSING VALIDATION & TESTING

### C1. Paper Trading Campaign (Golden Rule #3)
- [ ] **0 of 60 required days** completed
- [ ] **0 of 100 required trades** executed
- [ ] No paper trading campaign report exists
- [ ] No win rate / profit factor thresholds defined for pass/fail

### C2. Smoke Test (24-Hour Dry Run)
- [ ] Never been run
- [ ] Need to verify: kill switch activates, positions close, reconciliation detects discrepancies
- [ ] Need to verify: Telegram alerts fire, Prometheus metrics export correctly

### C3. Integration Tests
- [x] End-to-end test: Signal → Risk Check → Order → Fill → Position → Reconciliation — coverage is composite, not one continuous live test: `tests/test_e2e_signal_flow.py::test_full_flow_with_all_components` covers Signal→Risk; `tests/test_e2e_full_pipeline.py::test_full_pipeline_runs` covers Order→Fill→Ledger (asserts `entry_spread_cost`, `entry_slippage_cost`, `exit_slippage_cost`, `fees`, `pnl`) via `BacktestEngine`, not the live orchestrator; `tests/test_orchestrator_reconciliation.py` (5/5 passing, verified fresh — a previously-seen 5-failure log was stale, predating `mt5_gateway.get_positions()`) covers Position→Reconciliation. Gap: no single test exercises all six stages against the live orchestration path in one run.
- [x] Kill-switch integration: Telegram → KillSwitch → Position Close → Reconciliation — composite: `tests/test_telegram_commands.py::test_kill_confirm_activates` (Telegram `/kill` confirm → activates kill switch), `tests/test_telegram_coordinator_wiring.py::test_telegram_handler_coordinator_is_kill_switch_coordinator` (handler shares the same coordinator instance, no wiring gap), `tests/test_integration_e2e.py::TestE2EKillSwitchCoordinatorSync/TestE2EReconciliationDrift` (KillSwitch → 5-store sync → `PositionReconciler` → `action_required == "CLOSE_DRIFT"`).
- [x] Broker disconnection recovery test — `tests/chaos/test_network_disconnect.py::test_disconnect_no_double_execution`, `test_state_survives_disconnect`, `test_verify_no_double_execution_direct`, `test_verify_state_recovery_direct` (all passing).
- [x] MT5 reconnection after network failure — `tests/chaos/test_network_disconnect.py::test_reconnection_logic`, `test_verify_state_recovery_direct`; `MockMT5Connector` raises `ConnectionError` on any call while disconnected, reconnect path verified.

### C4. Stress Testing
- [x] Flash crash scenario on XAUUSD — `risk/stress_test.py` `SCENARIOS["flash_crash"]` (-8%/1 bar, vol 5x) + `SCENARIOS["flash_crash_recovery"]` (-10%, vol 6x); `tests/test_synthetic_shock_scenarios.py::test_xauusd_uses_symbol_specific_shock`.
- [ ] 3-sigma volatility spike — **GAP, confirmed**: read all 9 entries of `risk/stress_test.py::SCENARIOS` (market_crash, flash_crash, correlation_breakdown, liquidity_crisis, overnight_gap, spread_blowout, correlation_convergence, regime_shift_crash, flash_crash_recovery) — none is named or framed as a sigma-based/statistical volatility-spike scenario. No test covers this literal case.
- [ ] Simultaneous position open on multiple symbols — **GAP, likely**: closest candidate is `tests/chaos/test_deep_stress.py::test_100_positions_simultaneous`, but that stresses position *count*, not concurrent opens across *distinct symbols*. No test found that literally opens positions on multiple symbols at the same instant.
- [x] MT5 connection drop during order submission — `tests/chaos/test_network_disconnect.py`: `MockMT5Connector.send_order()` raises `ConnectionError`/logs "Order rejected: MT5 disconnected" when disconnected; exercised by `test_disconnect_no_double_execution` and the chaos harness in `tests/chaos/run_chaos.py`.

---

## CATEGORY D: SECURITY & SECRETS

### D1. Secrets Rotation (Manual)
- [ ] Change MT5 password in MetaTrader 5 terminal
- [ ] Revoke old Telegram bot token via @BotFather, create new bot
- [ ] Change PostgreSQL password
- [ ] Revoke old LLM API keys (Groq, Google AI, Cerebras, OpenRouter, Cohere)
- [ ] Update `.env` with all new values
- [ ] Restart all services

### D2. Security Audit Fixes
- [ ] `core/safe_pickle.py`: numpy allowlist tightened but not tested with all model formats
- [ ] `.env.example` contains default DB credentials — must be removed
- [x] IP spoofing protection not tested under load — `tests/chaos/test_rate_limiting.py`, 17/17 passing incl. concurrent-load spoof tests (`test_spoofed_forwarded_for_no_bypass_under_concurrent_load`, `test_trusted_proxy_forwarded_for_still_isolates_under_load`). `_client_ip()` only trusts X-Forwarded-For from `_TRUSTED_PROXY_IPS`.
- [x] SQL injection regex false positives — investigated, no live false positive found. `_SQL_IDENT_RE`/`_SAFE_IDENTIFIER`/`_TABLE_NAME_RE` (data/warehouse_loader.py, verify_bootstrap.py, data/duckdb_write_queue.py) only ever see clean letter-first symbols (XAUUSD, EURUSD, etc.) — every caller traced. Raw external-ticker formats (`EURUSD=X`, `BTC/USDT`, `^IXIC`) live only in unimported dead code (data_pipeline/config.py::SYMBOLS) and are normalized to clean symbols upstream before touching any identifier path. Regexes intentionally left strict — loosening to accept `=`/`/`/`^` would weaken injection defense for no live benefit. Coverage: 18 tests in tests/test_bootstrap_security.py.

---

## CATEGORY E: ARCHITECTURE & CODE QUALITY

### E1. Stub/Placeholder Code (12 items)
- [ ] `api/orders.py:72` — "return placeholder" in order creation
- [ ] `execution/oms.py:238` — exit_price="" placeholder
- [ ] `risk/position_sizer_v2.py:236` — margin check placeholder
- [ ] `execution/tca_framework.py:367` — `pass` in critical path
- [ ] `core/tv_integration.py:268` — "requires engine integration"
- [ ] `broker/mt5_gateway.py:98` — placeholder snapshot hash
- [ ] `api/telegram_commands.py:225,233,490` — multiple `pass` blocks
- [ ] `core/account.py:52` — `pass` in account initialization
- [ ] `execution/obsidian_export.py:462` — `pass` in export logic
- [ ] `core/state_store.py:135` — `pass` in state persistence

### E2. Missing Features
- [ ] Forex-specific features (interest rates, COT data, session volatility)
- [ ] Multi-asset feature normalization (each asset class needs own pipeline)
- [ ] Instrument-specific model training (one model per instrument, not shared)
- [ ] Cost-adjusted signal threshold (raise min_confidence for high-cost instruments)

### E3. Documentation
- [ ] README claims vs reality gaps (2 Critical findings from audit)
- [ ] CHANGE_CONTROL.md not signed by human reviewer
- [ ] Evidence pack not assembled for any phase

---

## CATEGORY F: DEPLOYMENT & OPERATIONAL

### F1. Deployment
- [ ] Docker Compose stack exists but has never been tested end-to-end
- [ ] No blue-green deployment strategy defined
- [ ] No rollback mechanism
- [ ] No automated backup for PostgreSQL
- [ ] MT5 Wine container not tested

### F2. Monitoring
- [ ] Prometheus + Grafana configured but dashboards not validated
- [ ] Alertmanager Telegram routing configured but not tested
- [x] Dead man's switch exists but not wired to Telegram alerts — was already wired; real defect was severity escalation not firing correctly, not a missing-wiring issue. Fixed and verified this audit pass.
- [ ] No uptime monitoring from external service

### F3. Runbook
- [x] RUNBOOK.md exists but not updated for current architecture — updated `RUNBOOK.md`: added §3b (Position Reconciliation Drift / Kill Switch Trip, citing `execution/position_reconciler.py`, `execution/reconciler.py`, `core/orchestrator.py::TradingOrchestrator`, `core/state_coordinator.py::StateCoordinator`) and refreshed §3 (DMS) to note Telegram severity-escalation alerting per the F2 fix, replacing the stale "wired to Telegram" gap language.
- [x] No incident response playbook — merged the structured Symptom/Detection/Response/Escalation playbooks from `reports/RUNBOOK.md` (Broker Disconnect, Stale Data, Drawdown Breach, Risk Denial, Trainer Hang, DB Migration/Rollback) into the canonical `RUNBOOK.md` under a new "Incident Response Playbook" section, cross-referenced against verified infra (`docker-compose.yml`, `alembic.ini`/`./alembic`, Dockerfile.trainer confirmed present).
- [x] No escalation path defined — added an explicit "Escalation Path" section to `RUNBOOK.md` describing the 4-tier chain (automated kill-switch/DMS → Telegram notification → manual operator intervention → full stop + post-mortem), documented honestly as a single-operator chain, not a paging/on-call policy — that expansion is out of scope for an agent-completable doc update and is called out as a live-deployment decision.

---

## CATEGORY G: REGIME & MARKET CONDITION HANDLING

### G1. Regime Filter
- [ ] `core/regime_filter.py` is deprecated — `core/regime` and `validation/regime_detector` are replacements
- [ ] Regime filter interacts with strategy selection but walk-forward doesn't use it
- [ ] No regime-specific walk-forward validation (test edge in different regimes)

### G2. News Blackout
- [ ] `core/news_blackout.py` exists with 120-minute CRISIS blackout
- [ ] Not wired to actual economic calendar API
- [ ] No automated news feed integration

---

## PRIORITY ORDER (What to do first)

### Phase 0: Edge Confirmation (Week 1)
1. Run 7-day spread measurement for XAUUSD, XPDUSD, XPTUSD
2. Re-run walk-forward on XAUUSD with measured costs
3. Re-run walk-forward on XPDUSD/XPTUSD with measured costs
4. Run PBO + Deflated Sharpe Ratio on all results
5. **Decision point**: If no instrument has edge after costs → STOP. Go back to strategy development.

### Phase 1: Fix Critical Bugs (Week 2)
1. Fix `AlertManager` — alerts must actually send
2. Fix `auto_retrain.py` — dummy metrics must be replaced
3. Wire `position_reconciler` to real-time monitoring
4. Fix telegram command `pass` blocks
5. Implement margin check in `position_sizer_v2.py`

### Phase 2: Security & Secrets (Week 3)
1. Rotate all secrets (MT5, Telegram, PostgreSQL, API keys)
2. Remove default credentials from `.env.example`
3. Run security scan

### Phase 3: Integration Testing (Week 4)
1. End-to-end integration test
2. Kill-switch integration test
3. Broker disconnection recovery test
4. 24-hour smoke test (dry run)

### Phase 4: Paper Trading (Weeks 5-13)
1. Run paper trading for 60 days minimum
2. Execute 100+ trades
3. Document win rate, profit factor, max drawdown
4. Generate paper campaign report

### Phase 5: Human Approval (Week 14)
1. Assemble evidence pack
2. Human reviewer signs CHANGE_CONTROL.md
3. Final production readiness gate check
4. Go/No-Go decision

---

## HONEST ASSESSMENT

| Category | Status | Effort |
|----------|--------|--------|
| Proven Edge | 🔴 NOT PROVEN | 2-3 weeks |
| Critical Bugs | 🟡 13 items | 2 weeks |
| Paper Trading | 🔴 NOT STARTED | 60+ days |
| Security | 🟡 Partially done | 1 week |
| Code Quality | 🟡 12 stubs | 2 weeks |
| Deployment | 🔴 NOT TESTED | 1 week |
| Monitoring | 🟡 Partially done | 1 week |

**Estimated time to live trading: 14-16 weeks minimum** (if no blockers found during edge confirmation)

**If XAUUSD edge survives measured costs: 14 weeks**
**If no instrument has edge: INDEFINITE — need strategy development**

---

*This document was generated from a comprehensive audit of 23/28 phases, walk-forward validation on 13 instruments, and code-level analysis of all critical subsystems.*
