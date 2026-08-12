# GRAXIA-OS + TSM Unified Mega Remediation Plan

Date: 2026-07-01
Scope: `quant_os` as one unified trading system, merging GRAXIA-OS data/signal/runtime layers with TSM portfolio/backtest realism work.
Priority order: security first, then completeness, then long-term maintainability.
Execution model: subagent-ready wave plan, with hard gates before any paper or live trading escalation.

## 0. Executive Verdict

Current verdict: `NO_GO` for live trading.

Paper trading can continue only as controlled dry-run or demo observation after Phase 0 and Phase 1 gates pass. No real-money live trading until security, OMS-risk coupling, kill-switch closeout behavior, data truth, realistic costs, and statistical validation are proven with evidence artifacts.

This plan supersedes narrower XAUUSD-only and TSM-only plans. TSM and GRAXIA-OS are treated as one system:

- GRAXIA-OS owns data ingestion, feature store, signal generation, SMC detectors, model training, risk controls, OMS, monitoring, and evidence.
- TSM owns multi-asset portfolio realism, backtest/live parity, regime exposure, cost realism, and paper-trade strategy parity.
- Shared runtime must expose one canonical path from data -> features -> signal -> risk -> OMS -> broker adapter -> ledger -> monitoring.

## 1. Source Facts To Preserve

### 1.1 Data and ML facts

- XAUUSD_D1 has severe historical-data contamination: 441 OHLC violations, 716 large gaps, and unusable early history around 1793.
- OB features are currently weak or mostly missing:
  - `ob_strength`: about 17 percent NaN in user-supplied audit.
  - `ob_mitigation_depth`: about 99 percent NaN.
  - `bars_since_sweep`: about 98 percent NaN.
- Repo audit summary confirms all four target symbols currently fail data-integrity health:
  - XAUUSD, EURUSD, BTCUSD, ETHUSD all score 73/100 and fail due to missing data, timestamp gaps, zero variance features, and highly missing OB fields.
- Current backtest results supplied by user are negative:
  - XAUUSD: return -29.4 percent, win rate 41.8 percent, Sharpe -2.49, max DD 29.8 percent.
  - EURUSD: return -5.2 percent, win rate 41.2 percent, Sharpe -4.27, max DD 5.6 percent.
  - BTCUSD: return -16.8 percent, win rate 42.9 percent, Sharpe -2.83, max DD 17.2 percent.
  - ETHUSD: return -0.5 percent, win rate 45.6 percent, Sharpe -1.70, max DD 0.5 percent.
- Good signals must not be thrown away:
  - swing high/low has real reversal signal according to supplied analysis.
  - SMC detector tests pass.
  - lookahead audit passed in generated audit summary.
  - walk-forward claims exist, but must be revalidated after data/cost/parity fixes.

### 1.2 TSM realism facts

- Claimed 20-year multi-asset backtest is not real full-overlap evidence. Full 8-asset overlap was reported as 637/7320 days, about 2.5 years.
- Backtest and paper bot calculate different returns:
  - Backtest `pct_change(fill_method="pad")`.
  - Paper bot `pct_change(fill_method=None)`.
  - Reported Sharpe drops from about 1.073 to 0.794.
- Real XAUUSD cost assumption was reported as far higher than modeled:
  - assumed 5 bps,
  - observed/estimated 72 bps round trip,
  - about 14x higher.
- TSM regime failure is critical:
  - trending Sharpe positive,
  - neutral Sharpe positive,
  - mean-reverting Sharpe about -2.775 with about -57.7 percent annualized loss.
- Dry-run/paper bot was reported as effectively single-asset, 100 percent XAUUSD, not a real multi-asset portfolio.

### 1.3 System audit facts

User supplied an 82-issue audit:

- 13 critical.
- 26 high.
- 43 medium.
- By category: security 15, risk 11, ML/strategy 8, code quality 16, performance 9, ops 12, testing 5, architecture 3, API design 3.
- Top issues:
  - rotate secrets and remove hardcoded credentials;
  - wire auth on every endpoint;
  - fix purged CV and early stopping;
  - wire OMS to risk engine;
  - kill switch must close positions, not only block new orders;
  - add PostgreSQL backup and restore test;
  - add CI/CD;
  - fix Sharpe annualization;
  - add Prometheus/Grafana;
  - consolidate shared utilities.

### 1.4 Constitutional constraints

The plan must preserve these invariants:

- Never claim guaranteed profit, zero loss, or zero drawdown.
- Never present backtest or demo results as live-profit evidence.
- No external model or repository may override risk controls.
- Every phase ends with exactly one verdict: `PASS_TO_NEXT_PHASE`, `CONDITIONAL_PASS`, `NO_GO`, `ARCHIVE_NO_EDGE`, or `INSUFFICIENT_SAMPLE`.
- Risk policy must be frozen and immutable.
- Pre-trade risk gate is mandatory before any order.
- Missing, invalid, or stale contract data must fail closed.
- Every sizing decision must bind to immutable contract snapshot ID.

## 2. Target End State

The target system is not "profitable by assertion." It is a truth-producing trading research and demo execution system that can honestly decide whether the edge exists.

Required end state:

- One canonical data contract for OHLCV, ticks, spreads, swap, broker contract specs, macro data, and features.
- One canonical feature pipeline with documented availability times and no macro leakage.
- One canonical cost model used by walk-forward, backtest, paper bot, OMS simulation, and reports.
- One canonical execution path where OMS cannot place, simulate, or route an order without risk pre-check approval.
- Kill switch closes or hedges open exposure according to written policy, persists across restart, and emits audit events.
- Paper trade bot trades the same strategy and assets as the validated backtest, or explicitly reports a scoped single-asset experiment.
- Monitoring has Prometheus metrics, Grafana dashboards, logs with correlation IDs, alert rules, and runbooks.
- Security has secret rotation, history cleanup plan, authn/authz on endpoints, replay protection, encryption/backups, and CI secret scanning.
- ML validation uses purged plus embargoed validation, realistic costs, regime analysis, PBO/deflated Sharpe, multiple-test correction, and walk-forward artifacts.

## 3. Hard Stop Rules

Stop immediately and return `NO_GO` if any condition occurs:

- Secret or credential exposure is found and not rotated.
- Any unauthenticated state-changing endpoint remains reachable.
- OMS can bypass risk pre-check or contract snapshot validation.
- Kill switch does not persist or cannot handle open positions.
- Data pipeline cannot prove timestamp, timezone, and no-lookahead integrity.
- Backtest and paper bot do not share the same return, fill, cost, and symbol universe semantics.
- Realistic costs turn net edge negative.
- Mean-reversion regime exposure remains materially negative without a tested exposure reducer.
- Any production/live credential is needed and not explicitly approved.

## 4. Subagent Topology

Use one coordinator plus specialized subagents. Each subagent writes a short evidence note under `reports/mega_plan_evidence/` and never changes shared contracts without coordinator approval.

| Agent | Ownership | Parallel? | Output |
|---|---|---:|---|
| coordinator | gates, dependencies, final verdicts, merge order | no | phase verdicts |
| security-agent | secrets, auth, webhook replay, SQL injection, encryption | yes after Phase 0 | security evidence |
| data-agent | OHLCV quality, manifests, gaps, feature NaNs, PIT joins | yes | data evidence |
| ml-agent | features, CPCV, early stopping, PBO, DSR, multiple testing | yes after data contract freezes | ML evidence |
| execution-agent | OMS, broker routing, fills, costs, paper/backtest parity | yes after risk contract freezes | execution evidence |
| risk-agent | RiskPolicy, pre-trade gate, kill switch, circuit breaker | yes after Phase 0 | risk evidence |
| ops-agent | CI/CD, backup/restore, metrics, Grafana, tracing, runbooks | yes | ops evidence |
| test-agent | boilerplate test cleanup, missing tests, release gate | yes | test matrix |
| reviewer-agent | independent diff and gate review | no, after each wave | review findings |

Subagent rules:

- No broad rewrites while another agent owns the same files.
- No migrations, secret reads, credential rotation, deployment, or live order actions without explicit human approval.
- All tasks must include acceptance criteria and verification command.
- If an agent cannot prove a claim, it marks `UNKNOWN`, not pass.

## 5. Wave Plan Overview

| Wave | Name | Goal | Parallelism | Exit verdict |
|---:|---|---|---|---|
| 0 | Freeze and Evidence Baseline | make current truth reproducible | low | baseline report |
| 1 | Security Closure | remove account/system takeover paths | high | security gate |
| 2 | Data Truth | rebuild usable datasets and feature contract | high | data gate |
| 3 | Risk and OMS Safety | prevent unsafe order lifecycle | medium | safety gate |
| 4 | Backtest/Paper Parity | make paper bot reflect tested strategy | medium | parity gate |
| 5 | ML/Feature Rebuild | remove leakage/noise, add real features | medium | model gate |
| 6 | Realistic Portfolio Validation | prove or reject edge after costs/regimes | medium | edge gate |
| 7 | Ops and Maintainability | make system operable long-term | high | ops gate |
| 8 | Paper Trade Campaign | controlled demo evidence collection | low | paper verdict |
| 9 | Live Readiness Review | decide live/no-live honestly | low | final verdict |

## 6. Wave 0: Freeze and Evidence Baseline

Goal: prevent moving targets. Establish truth before fixes.

### Task 0.1: Create change-control ticket

Description: Record this plan as the phase change request for strategy, data, execution, risk, and model changes.

Acceptance criteria:

- `CHANGE_CONTROL.md` or a phase-specific change request references this plan.
- Locked experiment outputs are not overwritten.
- No live trading is authorized by this task.

Verification:

- `git diff -- CHANGE_CONTROL.md Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md`

Dependencies: none.
Files likely touched: `CHANGE_CONTROL.md`, `Meta/*`.
Scope: XS.
Owner: coordinator.

### Task 0.2: Build current evidence index

Description: Create a machine-readable index of current reports, dry runs, readiness JSON, full audit, data audit, and backtest outputs.

Acceptance criteria:

- Report index lists source path, timestamp, command if known, verdict, and whether evidence is trusted/current/stale.
- User-supplied missing items #1-31 are explicitly marked `MISSING_DETAIL_RESCAN_REQUIRED`.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_repo_manifest.py -q`
- Manual: open generated `reports/mega_plan_evidence/index.md`.

Dependencies: none.
Files likely touched: `reports/mega_plan_evidence/index.md`.
Scope: S.
Owner: coordinator.

### Task 0.3: Run non-secret repo scan

Description: Scan code for hardcoded credentials, unsafe SQL, unauthenticated endpoints, risk bypasses, bare exceptions, `datetime.utcnow`, and test boilerplate. Do not print secret values.

Acceptance criteria:

- Findings are grouped by severity and file path.
- No secret plaintext is echoed into reports.
- If committed secret evidence exists, report only key type and path, not value.

Verification:

- `python scripts/secret_scan.py`
- `python -m pytest graxia/packages/quant_os/runtime/test_secret_provider.py -q`

Dependencies: none.
Files likely touched: `reports/mega_plan_evidence/security_scan.md`.
Scope: S.
Owner: security-agent.

## 7. Wave 1: Security Closure

Goal: remove takeover, replay, injection, and secret exposure paths.

### Task 1.1: Secret rotation and history plan

Description: Identify all credential types that have ever appeared in repo files or logs, then prepare rotation instructions. Actual rotation requires human approval.

Acceptance criteria:

- All suspected secret locations are listed with redacted values.
- Rotation owner/source is documented for MT5, Telegram, DB, API/JWT, broker, VPS, GitHub, and cloud providers.
- Git history cleanup plan exists if secrets were committed.

Verification:

- Secret scan returns no plaintext high-confidence secrets in current tree.
- CI secret scan added in Wave 7 catches seeded fake secret.

Dependencies: Task 0.3.
Files likely touched: `SECURITY.md`, `reports/mega_plan_evidence/security_secrets.md`, CI config.
Scope: M.
Owner: security-agent.

### Task 1.2: Authn/authz on all API endpoints

Description: Enforce authentication on every endpoint and role/permission checks on every state-changing endpoint.

Acceptance criteria:

- All `api/admin.py`, `api/risk.py`, `api/orders.py`, `api/positions.py`, and webhook surfaces have explicit auth policy.
- State-changing endpoints require idempotency key and audit entry.
- Tests prove anonymous calls fail.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_api_endpoints.py -q`
- New security tests for unauthenticated and wrong-role requests.

Dependencies: Task 1.1 can run in parallel, but endpoint policy must not depend on secrets.
Files likely touched: `api/*.py`, `api/models.py`, tests.
Scope: M.
Owner: security-agent.

### Task 1.3: SQL injection closure

Description: Replace f-string DuckDB/PostgreSQL query interpolation with parameterized APIs or safe identifier whitelists.

Acceptance criteria:

- `verify_bootstrap.py` and any similar query builders use bound parameters.
- Dynamic identifiers are whitelisted enums, never raw user strings.
- Tests include malicious strings.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_bootstrap_security.py -q`
- Static search finds no risky query f-string patterns in DB modules.

Dependencies: Task 0.3.
Files likely touched: `verify_bootstrap.py`, DB/query modules, tests.
Scope: S.
Owner: security-agent.

### Task 1.4: Webhook replay and signature hardening

Description: Make webhook replay protection robust against attacker-controlled timestamps.

Acceptance criteria:

- Signature validation happens before business logic.
- Nonce/event ID is stored with TTL.
- Timestamp skew is checked using server receipt time.
- Duplicate, old, future, invalid-signature, and wrong-body tests pass.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_webhook_security.py -q`

Dependencies: Task 1.2.
Files likely touched: `api/webhook.py`, `api/webhook_receiver.py`, tests.
Scope: M.
Owner: security-agent.

### Task 1.5: Encryption at rest and backups

Description: Define and test encryption-at-rest posture for PostgreSQL/DuckDB/artifacts, plus backup/restore.

Acceptance criteria:

- Docker/infra docs state where encryption is provided: disk, volume, DB, or host.
- Backup job exists for PostgreSQL and critical local state.
- Restore test creates a clean DB and verifies row counts/checksums.

Verification:

- `python scripts/backup_restore_smoke.py --dry-run`
- Restore evidence saved under `reports/mega_plan_evidence/backup_restore.md`.

Dependencies: none.
Files likely touched: `docker-compose.yml`, `docs/runbooks/*`, scripts, tests.
Scope: M.
Owner: ops-agent.

## 8. Wave 2: Data Truth

Goal: make datasets auditable, clean, and point-in-time correct.

### Task 2.1: XAUUSD_D1 quarantine and 20-year trim

Description: Quarantine contaminated XAUUSD_D1 history and create a clean 20-year-or-less canonical dataset with manifest.

Acceptance criteria:

- Rows before the trusted start date are excluded from canonical training data.
- OHLC violations are zero in canonical set.
- Large gaps are either filled by approved source reconciliation or marked as market closures/unusable.
- Original raw file remains untouched.

Verification:

- `python scripts/validate_data_multi_asset.py --symbol XAUUSD --timeframe D1`
- Manifest hash changes only for new canonical output.

Dependencies: Task 0.2.
Files likely touched: `data/manifests/*`, `reports/mega_plan_evidence/data_xauusd_d1.md`, canonical data output.
Scope: M.
Owner: data-agent.

### Task 2.2: Multi-asset overlap truth table

Description: Produce exact date coverage, overlap, missingness, and tradability table for XAUUSD, EURUSD, BTCUSD, ETHUSD, and any TSM sleeve symbols.

Acceptance criteria:

- Reports per-symbol rows, start/end, missing days, trading-session gaps, all-asset overlap, cluster overlap.
- Full portfolio backtest period cannot be labeled 20 years unless all required assets exist and are tradable for that period.

Verification:

- `python scripts/mt5_portfolio_verify.py`
- Generated report: `reports/mega_plan_evidence/multi_asset_overlap.md`.

Dependencies: Task 2.1 can run in parallel.
Files likely touched: reports only unless validator code needs repair.
Scope: S.
Owner: data-agent.

### Task 2.3: Feature deletion list

Description: Remove or quarantine known bad features from model inputs: macro leakage/noise features, redundant feature pairs, and high-NaN OB fields.

Initial removal candidates:

- Drop 9 macro features from FRED/COT until point-in-time joins are proven.
- Drop 5 redundant feature pairs identified by correlation audit.
- Drop `bars_since_sweep` and `ob_mitigation_depth` from v3 model inputs.
- Quarantine `ob_strength` until zero-variance and NaN behavior is fixed.

Acceptance criteria:

- Model feature list is explicit and versioned.
- Removed features are not silently used in training, inference, or explainability.
- Feature removal has regression tests.

Verification:

- `python scripts/diagnose_features.py`
- `python -m pytest graxia/packages/quant_os/tests/test_feature_parity.py -q`

Dependencies: Task 2.2.
Files likely touched: `ml/feature_store.py`, `scripts/build_features_v3_multi_asset.py`, docs/tests.
Scope: M.
Owner: data-agent and ml-agent.

### Task 2.4: Point-in-time macro feature store

Description: Re-introduce macro features only through as-of joins using published-at timestamps.

Acceptance criteria:

- Every macro row stores value date, published-at timestamp, source, revision if available, and ingestion timestamp.
- Feature builder cannot join future macro values.
- Tests simulate delayed publication and revision.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_macro_data.py graxia/packages/quant_os/tests/test_lookahead_regression.py -q`

Dependencies: Task 2.3.
Files likely touched: `core/data/*`, `data_pipeline/*`, tests, docs.
Scope: M.
Owner: data-agent.

### Task 2.5: Weekend and missing-bar policy

Description: Make bot and backtest use identical missing-bar semantics.

Acceptance criteria:

- Weekend forward-fill policy is explicit per asset class.
- `pct_change` fill method is identical in backtest and paper bot.
- No silent fill across real trading gaps.

Verification:

- New parity test with weekend window.
- `python -m pytest graxia/packages/quant_os/tests/test_feature_parity.py -q`

Dependencies: Task 4.1.
Files likely touched: data loaders, paper bot, backtest loaders, tests.
Scope: M.
Owner: data-agent and execution-agent.

## 9. Wave 3: Risk and OMS Safety

Goal: order path cannot bypass risk, and emergency controls handle open exposure.

### Task 3.1: Consolidate RiskPolicy

Description: Replace duplicate mutable RiskPolicy classes with one frozen, basis-point policy.

Acceptance criteria:

- Only canonical `risk/risk_policy.py::RiskPolicy` is used in production paths.
- No mutable risk-policy dataclass remains in `pre_trade_risk.py` or position sizer.
- Tests prove mutation raises error.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_risk_engine.py graxia/packages/quant_os/tests/test_phase_2a.py -q`

Dependencies: none.
Files likely touched: `risk/pre_trade_risk.py`, `risk/position_sizer_v2.py`, `risk/risk_policy.py`, tests.
Scope: M.
Owner: risk-agent.

### Task 3.2: OMS must call pre-trade risk

Description: Enforce risk gate inside OMS before any broker route or simulated order.

Acceptance criteria:

- Every OMS state-modifying path requires `RiskCheckResult.approved`.
- Risk denial creates an event and no broker call.
- Contract snapshot ID is attached to every sizing/order decision.
- Crypto routing bug fixed: BTC/ETH route to the configured MT5 CFD broker when paper trading MT5 symbols, not Binance by default.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_execution.py graxia/packages/quant_os/tests/test_e2e_signal_flow.py -q`
- New OMS risk-bypass regression test.

Dependencies: Task 3.1.
Files likely touched: `execution/oms.py`, `execution/manager.py`, broker adapters, tests.
Scope: M.
Owner: execution-agent and risk-agent.

### Task 3.3: Kill switch closes open positions

Description: Extend kill switch behavior from "block new orders" to "handle existing exposure by policy."

Acceptance criteria:

- Policy supports at least: `CLOSE_ALL`, `CLOSE_RISK_INCREASING_ONLY`, `NO_NEW_ORDERS_ONLY`.
- Default for live/paper emergency is `CLOSE_ALL` unless explicitly configured otherwise.
- Close attempts are idempotent, audited, and alert on failure.
- System reconciles actual broker position state after close attempts.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_e2e_critical_incident.py graxia/packages/quant_os/canary/test_demo_order_guard.py -q`

Dependencies: Task 3.2.
Files likely touched: `risk/kill_switch.py`, `risk/circuit_breaker.py`, `execution/oms.py`, `canary/*`, tests.
Scope: M.
Owner: risk-agent and execution-agent.

### Task 3.4: Circuit breaker integration

Description: Circuit breaker and kill switch must share state transitions and audit trail.

Acceptance criteria:

- Circuit breaker can trigger kill switch.
- Kill switch state is visible to circuit breaker status.
- Manual reset requires auth, reason, and audit entry.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_risk_edge_cases.py -q`

Dependencies: Task 3.3.
Files likely touched: `risk/circuit_breaker.py`, `risk/kill_switch.py`, monitoring/tests.
Scope: S.
Owner: risk-agent.

### Task 3.5: Order lifecycle tests

Description: Add dedicated OMS order lifecycle tests.

Acceptance criteria:

- Tests cover submit, risk reject, broker reject, partial fill, fill, cancel, close, duplicate idempotency, restart reconciliation.
- Tests prove no order can skip required states.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_oms_order_lifecycle.py -q`

Dependencies: Task 3.2.
Files likely touched: tests, possibly `execution/order_state_machine.py`.
Scope: M.
Owner: test-agent and execution-agent.

## 10. Wave 4: Backtest/Paper Parity

Goal: paper bot must trade the same strategy semantics as validated backtest.

### Task 4.1: Canonical return calculation

Description: One function owns return calculation, fill method, and missing-bar handling.

Acceptance criteria:

- Backtest and paper bot call the same return utility.
- `fill_method` cannot differ by caller.
- Weekend and asset-session behavior is configured, not implicit pandas default.

Verification:

- New test reproduces old Sharpe 1.073 vs 0.794 divergence and proves it is gone.
- `python -m pytest graxia/packages/quant_os/tests/test_backtest_refactor_b1_b3_c4.py -q`

Dependencies: Task 2.5.
Files likely touched: `backtest/*`, `scripts/tsm_backtest.py`, `scripts/tsm_paper_trade.py`, tests.
Scope: M.
Owner: execution-agent.

### Task 4.2: Account size truth

Description: Use actual configured/demo account equity consistently.

Acceptance criteria:

- Paper readiness, sizing, backtest normalization, and reports all use the same account-equity source.
- User-reported `$49.8K` demo account is not mixed with `$10K` config unless intentionally simulated and labeled.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_position_sizer_numeric.py -q`

Dependencies: Task 3.1.
Files likely touched: `config/paper_trade_config.json`, `live_readiness/account_snapshot_service.py`, sizing tests.
Scope: S.
Owner: risk-agent.

### Task 4.3: Canonical cost model

Description: Unify cost model across backtest engine, walk-forward, paper bot, OMS simulator, and reports.

Acceptance criteria:

- No hardcoded spread, commission, slippage, or contract size in backtest production path.
- Cost uses broker contract spec and observed spreads.
- XAUUSD metals commission model is not double-counted.
- Swap/rollover is either modeled or positions are force-flattened before rollover.
- Real spread scenarios include XAUUSD 72 bps stress case and session buckets.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_cost_unit_regression.py graxia/packages/quant_os/cost/test_cost_model_labeled.py -q`
- `python scripts/backtest_cost.py` with generated evidence.

Dependencies: Task 2.2, Task 3.2.
Files likely touched: `core/cost_model.py`, `execution/cost_model.py`, `backtest/engine.py`, `execution/swap_model.py`, tests.
Scope: M.
Owner: execution-agent.

### Task 4.4: Multi-asset paper bot parity

Description: Paper bot must either trade all validated assets with configured weights or label itself a single-asset XAUUSD experiment.

Acceptance criteria:

- Dry-run report shows per-asset target weight, actual position weight, signal count, rejected count, and reason.
- No hidden 100 percent XAUUSD allocation in a report labeled multi-asset.
- BTC/ETH route correctly through intended broker adapter.

Verification:

- `python scripts/mt5_portfolio_verify.py`
- `python scripts/run_dry_run_1hr.py`
- New test for asset allocation report.

Dependencies: Task 3.2, Task 4.3.
Files likely touched: `scripts/tsm_paper_trade.py`, `scripts/multi_symbol_bot.py`, reports/tests.
Scope: M.
Owner: execution-agent.

## 11. Wave 5: ML and Feature Rebuild

Goal: rebuild features and models only after data and parity are honest.

### Task 5.1: Build `features_v3`

Description: Remove bad features and add momentum/trend/volatility/session/MTF context.

Required additions:

- RSI 14.
- MACD.
- Bollinger Band width.
- ATR ratio: current ATR divided by historical ATR.
- ADX.
- Session returns: Asian, London, NY, overlap.
- Multi-timeframe alignment: M15/H1/H4/D1 trend agreement.
- Distance from MA 20, 50, 200.
- Regime labels and regime confidence.

Acceptance criteria:

- Feature list is documented.
- Every feature has availability timestamp and no-lookahead test.
- Feature missingness and zero-variance report passes thresholds.

Verification:

- `python scripts/build_features_v3_multi_asset.py`
- `python scripts/diagnose_features.py`
- `python -m pytest graxia/packages/quant_os/tests/test_feature_parity.py graxia/packages/quant_os/tests/test_mtf_leak.py -q`

Dependencies: Wave 2 complete.
Files likely touched: `scripts/build_features_v3_multi_asset.py`, `ml/feature_store.py`, docs/tests.
Scope: M.
Owner: ml-agent and data-agent.

### Task 5.2: Purged plus embargoed CV

Description: Replace leaky or insufficient validation with purged and embargoed cross-validation appropriate for label horizon and serial correlation.

Acceptance criteria:

- Embargo default is not zero.
- Purge size covers label lookahead horizon.
- Split report proves no overlap between train labels and test targets.
- CPCV/PurgedKFold selection is explicit and documented.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_mtf_leak.py graxia/packages/quant_os/tests/test_lookahead_regression.py -q`
- Generated split audit under `reports/mega_plan_evidence/cv_split_audit.md`.

Dependencies: Task 5.1.
Files likely touched: `validation/walk_forward.py`, `backtest/walk_forward.py`, `scripts/run_walk_forward.py`, tests.
Scope: M.
Owner: ml-agent.

### Task 5.3: Early stopping and overfit controls

Description: Fix model training so train accuracy cannot hit 100 percent without failing overfit diagnostics.

Acceptance criteria:

- Early stopping works for supported models.
- Train/OOS gap thresholds are enforced.
- Model registry stores training params, seed, split IDs, features hash, data manifest hash.
- Overfit fail produces `NO_GO`, not "best model."

Verification:

- `python scripts/train_all_models.py --dry-run`
- `python -m pytest graxia/packages/quant_os/tests/test_model_training.py -q`

Dependencies: Task 5.2.
Files likely touched: `ml/pipeline.py`, `run_ml_train.py`, `scripts/train_all_models.py`, `ml/model_registry.py`, tests.
Scope: M.
Owner: ml-agent.

### Task 5.4: Multiple testing correction

Description: Apply BH-FDR or stricter correction across tested features, strategies, symbols, regimes, and hyperparameter attempts.

Acceptance criteria:

- Experiment registry records number of hypotheses.
- Reports show raw p-value and adjusted p-value.
- Edge claims require adjusted significance plus economic significance after cost.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_phase_5_statistical.py -q`

Dependencies: Task 5.3.
Files likely touched: `validation/*`, `governance/experiment_registry.py`, reports/tests.
Scope: M.
Owner: ml-agent.

### Task 5.5: ML training test suite

Description: Add tests for training pipeline contract.

Acceptance criteria:

- Tests cover feature schema, train/test split, model save/load, predict/predict_proba single-call efficiency, early stopping, and registry metadata.
- No test relies on mock DB if real local test DB/fixture exists.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_ml_pipeline_training.py -q`

Dependencies: Task 5.3.
Files likely touched: tests and `ml/*`.
Scope: M.
Owner: test-agent and ml-agent.

## 12. Wave 6: Realistic Portfolio Validation

Goal: decide whether edge exists after all realism fixes.

### Task 6.1: Recalculate Sharpe and Sortino correctly

Description: Fix annualization, downside deviation, and fill semantics.

Acceptance criteria:

- Sharpe annualization uses correct bar frequency and trading calendar per asset.
- Sortino downside deviation uses full sample denominator or clearly documented standard formula.
- Reports include confidence interval, not only point estimate.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_benchmark_baseline.py graxia/packages/quant_os/tests/test_phase_5_statistical.py -q`

Dependencies: Task 4.1.
Files likely touched: `backtest/metrics.py`, `core/metrics.py`, tests.
Scope: S.
Owner: ml-agent.

### Task 6.2: Regime filter for mean-reversion damage

Description: Reduce or block exposure during regimes where TSM historically loses heavily.

Acceptance criteria:

- Regime classifier is trained only on past data.
- Mean-reversion regime reduces exposure, switches sleeve, or blocks entries according to pre-registered rule.
- Results are reported by regime with net cost and drawdown.

Verification:

- `python scripts/diagnose_regime_accuracy.py`
- `python -m pytest graxia/packages/quant_os/regime/test_risk.py graxia/packages/quant_os/tests/test_phase_3b_regime.py -q`

Dependencies: Task 5.1, Task 6.1.
Files likely touched: `regime/*`, `core/regime_filter.py`, strategy configs/tests.
Scope: M.
Owner: ml-agent and risk-agent.

### Task 6.3: Combined portfolio PBO and deflated Sharpe

Description: Test combined 20+120 sleeve and any TSM/GRAXIA ensemble as a separate strategy, not as an untested aggregation.

Acceptance criteria:

- Combined portfolio is strategy ID in experiment registry.
- PBO, DSR, PSR, and minimum track record length are computed.
- Portfolio cluster correlation is reported: XAU/XAG, EUR/GBP, BTC/ETH, etc.

Verification:

- `python tests/run_holdout_and_deflated.py`
- `python -m pytest graxia/packages/quant_os/tests/test_phase_5_verdict.py -q`

Dependencies: Task 5.4, Task 6.2.
Files likely touched: `validation/probability_overfitting.py`, `validation/deflated_sharpe.py`, reports/tests.
Scope: M.
Owner: ml-agent.

### Task 6.4: Realistic backtest rerun

Description: Rerun backtests with clean data, features_v3, canonical costs, corrected metrics, and parity semantics.

Acceptance criteria:

- Per-symbol and portfolio results include return, win rate, Sharpe, Sortino, max DD, DD duration, regime metrics, cost breakdown, and confidence intervals.
- A negative result is accepted as valid and can produce `ARCHIVE_NO_EDGE`.
- No report claims live profitability.

Verification:

- `python scripts/backtest_suite.py`
- `python scripts/run_walk_forward.py`
- `python scripts/run_release_truth.py`

Dependencies: Wave 2 through Wave 5 complete.
Files likely touched: reports/artifacts only unless runner bugs are found.
Scope: M.
Owner: coordinator and ml-agent.

## 13. Wave 7: Ops and Maintainability

Goal: make system operable and maintainable.

### Task 7.1: CI/CD pipeline

Description: Add automated test, lint/type, secret scan, and release gate jobs.

Acceptance criteria:

- CI runs targeted fast tests on PR.
- Nightly or manual job runs full regression.
- Secret scan fails on seeded fake secret.
- Release gate artifact is uploaded.

Verification:

- CI green on branch.
- Local: `python scripts/run_release_gate.py`.

Dependencies: Task 1.1, enough tests stable.
Files likely touched: `.github/workflows/*`, scripts.
Scope: M.
Owner: ops-agent.

### Task 7.2: Prometheus and Grafana

Description: Metrics export exists but must be viewed and alerted.

Acceptance criteria:

- Prometheus scrapes API, trainer, signal service, OMS, paper bot, DB, and scheduler.
- Grafana dashboards cover health, data freshness, model version, order lifecycle, PnL, risk, and latency.
- Alert rules exist for stale data, hung trainer, MT5 disconnect, risk denial spike, order reject, drawdown, kill switch, and no heartbeat.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_live_monitoring.py -q`
- Manual local Prometheus target check documented.

Dependencies: none.
Files likely touched: `monitoring/*`, `docker-compose.yml`, `monitoring/grafana/*`, docs.
Scope: M.
Owner: ops-agent.

### Task 7.3: Correlation IDs and tracing

Description: Add request/signal/order correlation IDs across service boundaries.

Acceptance criteria:

- Every signal, risk check, OMS event, broker call, ledger write, and alert shares a correlation ID.
- Logs are structured JSON where practical.
- API responses include request ID.

Verification:

- New integration test asserts one ID flows through signal -> risk -> OMS -> ledger.

Dependencies: Task 3.2.
Files likely touched: `core/event_bus.py`, `api/*`, `execution/*`, `monitoring/*`, tests.
Scope: M.
Owner: ops-agent and execution-agent.

### Task 7.4: Trainer healthcheck

Description: Detect hung trainer and stale model pipeline.

Acceptance criteria:

- Trainer exposes health endpoint or heartbeat.
- Docker healthcheck is active.
- Alert fires when training hangs or model registry is stale.

Verification:

- `docker compose ps`
- `python -m pytest graxia/packages/quant_os/tests/test_model_versioning.py -q`

Dependencies: Task 5.3.
Files likely touched: `docker-compose.yml`, trainer scripts, monitoring/tests.
Scope: S.
Owner: ops-agent and ml-agent.

### Task 7.5: DB migrations automation

Description: Make schema changes reproducible through Alembic or existing migration tool.

Acceptance criteria:

- Migration command runs from clean DB to current schema.
- Downgrade/rollback policy documented for non-destructive changes.
- CI applies migrations to test DB.

Verification:

- `alembic upgrade head`
- `python -m pytest graxia/packages/quant_os/tests/integration/ -q`

Dependencies: Task 1.5.
Files likely touched: `alembic/*`, docs, CI.
Scope: M.
Owner: ops-agent.

### Task 7.6: Code quality cleanup batch

Description: Reduce high-impact debt without changing behavior.

Targets:

- Replace boilerplate tests such as `assert is not None` where they do not test behavior.
- Convert `test_ema_rsi.py` and `test_label_shuffling.py` into real tests or quarantine them.
- Reduce `Any` where used to bypass circular imports.
- Replace bare `except:` and broad `except Exception` in critical paths with explicit handling.
- Move root scratch files into archive or delete only with approval.
- Consolidate `tick/` vs `ticks/` naming plan.
- Normalize MT5 timeout defaults.
- Replace `datetime.utcnow()` with timezone-aware UTC.
- Replace magic order-state strings with enums.
- Replace critical-path `print()` with logging.
- Add Pydantic response models to API endpoints.

Acceptance criteria:

- Behavior-preserving cleanup only unless tests are added first.
- No broad refactor without file owner and tests.
- Root scratch cleanup does not delete user work without approval.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_repo_hooks.py -q`
- Lint/static checks if configured.

Dependencies: safety and test gates.
Files likely touched: many small files; split into sub-batches.
Scope: M per batch.
Owner: test-agent and coordinator.

### Task 7.7: Performance fixes

Description: Fix known hot spots only with measurement.

Targets:

- `_safe_slope` rolling `np.polyfit` hot path.
- `_log_trade` full-Parquet read per trade.
- synchronous file writes in async endpoints.
- duplicate `predict_proba` and `predict` calls.
- EventBus opening file on every publish.

Acceptance criteria:

- Baseline benchmark exists before optimization.
- New implementation has equivalent tests.
- Improvement or no-improvement is reported honestly.

Verification:

- `python -m pytest graxia/packages/quant_os/tests/test_hot_path_latency.py graxia/packages/quant_os/loadtests/test_throughput.py -q`

Dependencies: Task 7.3 for tracing helps but not required.
Files likely touched: `api/signal_service.py`, `core/position_manager.py`, `core/event_bus.py`, tests.
Scope: M.
Owner: ops-agent.

### Task 7.8: Runbooks and on-call docs

Description: Make operator handoff realistic.

Acceptance criteria:

- Runbook covers startup, shutdown, paper campaign, kill switch, MT5 disconnect, stale data, failed order, DB restore, rollback, dashboard, and escalation.
- On-call path names human action points without exposing secrets.
- Every alert links to a runbook section.

Verification:

- Reviewer-agent performs tabletop drill from runbook only.

Dependencies: Tasks 7.1 through 7.5.
Files likely touched: `reports/RUNBOOK.md`, `docs/runbooks/*`.
Scope: M.
Owner: ops-agent.

## 14. Wave 8: Paper Trade Campaign

Goal: collect honest demo evidence after gates pass.

### Task 8.1: Paper preflight v2

Description: Replace loose readiness check with hard blocker semantics.

Acceptance criteria:

- Telegram/alerts are required for campaign, not optional.
- MT5 account equity, server, broker, symbol contract specs, and routing are captured.
- Risk, kill switch, data freshness, model version, and cost calibration are all required.
- Readiness fails if any required item fails.

Verification:

- `python scripts/paper_trade_checklist.py`
- `python -m pytest graxia/packages/quant_os/tests/test_phase_10_micro_live.py -q`

Dependencies: Waves 1-7.
Files likely touched: `scripts/paper_trade_checklist.py`, `reports/paper_trade_readiness.json`, tests.
Scope: S.
Owner: coordinator.

### Task 8.2: 24-hour dry run

Description: Run without broker order placement and prove signals, risk checks, OMS decisions, and alerts.

Acceptance criteria:

- Report includes all cycles, signals, rejections, risk denials, costs, data freshness, and model version.
- No hidden single-asset behavior if campaign is multi-asset.
- Any failed alert or missing heartbeat returns `NO_GO`.

Verification:

- `python scripts/run_dry_run_24hr.py`
- Review `reports/dry_run_*.json`.

Dependencies: Task 8.1.
Files likely touched: reports only unless bugs found.
Scope: M.
Owner: coordinator and ops-agent.

### Task 8.3: 7-day demo paper campaign

Description: Run demo orders only after dry-run pass.

Acceptance criteria:

- Every order has signal ID, risk check ID, contract snapshot ID, OMS event ID, ledger ID, and broker ticket.
- Reconciliation runs on restart and daily.
- Report includes real fills, spread, slippage, swap/rollover, rejects, and regime performance.
- Kill switch drill is executed in demo and proves open-position handling.

Verification:

- `python launch_7day.py`
- `python scripts/monitor_paper_trades.py`
- `python scripts/evaluate_b2_paper.py`

Dependencies: Task 8.2.
Files likely touched: reports/artifacts only unless bugs found.
Scope: M.
Owner: coordinator.

## 15. Wave 9: Live Readiness Review

Goal: decide, not assume.

### Task 9.1: Final evidence pack

Description: Assemble all artifacts into one promotion review.

Acceptance criteria:

- Evidence pack references security, data, ML, risk, execution, ops, tests, dry-run, and paper campaign.
- Missing evidence is explicitly listed.
- User approval is required before any live credential use or live order route.

Verification:

- `python scripts/run_release_gate.py`
- `python -m pytest graxia/packages/quant_os/tests/ --tb=short -q`

Dependencies: Wave 8.
Files likely touched: `reports/FINAL_LIVE_READINESS_REVIEW.md`, artifacts.
Scope: M.
Owner: coordinator and reviewer-agent.

### Task 9.2: Final verdict

Description: Produce one constitutional verdict.

Allowed verdicts:

- `PASS_TO_NEXT_PHASE`: only if all hard blockers are closed and evidence supports limited next phase.
- `CONDITIONAL_PASS`: only for non-critical gaps with explicit controls.
- `NO_GO`: any critical gap remains.
- `ARCHIVE_NO_EDGE`: system is safe enough to test but strategy has no economic/statistical edge.
- `INSUFFICIENT_SAMPLE`: safety is acceptable but sample size is too small.

Acceptance criteria:

- Verdict includes exact reasons.
- No profit promise.
- No live action without separate approval.

Verification:

- Human review.

Dependencies: Task 9.1.
Files likely touched: `reports/FINAL_LIVE_READINESS_REVIEW.md`.
Scope: XS.
Owner: coordinator.

## 16. Issue Mapping: User Audit Items 32-70

| Item | Plan task |
|---:|---|
| 32 No Prometheus/Grafana | 7.2 |
| 33 No request tracing | 7.3 |
| 34 Trainer no healthcheck | 7.4 |
| 35 No encryption at rest | 1.5 |
| 36 No on-call docs | 7.8 |
| 37 Runbook too short | 7.8 |
| 38 No DB migration automation | 7.5 |
| 39 Boilerplate tests | 7.6 |
| 40 Non-tests | 7.6 |
| 41 SentimentAgent no chaos test | 7.6 plus chaos test batch |
| 42 OMS lifecycle no dedicated test | 3.5 |
| 43 ML pipeline no training test | 5.5 |
| 44 `Any` type debt | 7.6 |
| 45 Bare/broad exceptions | 7.6 |
| 46 Root scratch files | 7.6 |
| 47 `tick/` vs `ticks/` | 7.6 |
| 48 MT5 timeout defaults | 7.6 |
| 49 `datetime.utcnow()` | 7.6 |
| 50 Magic order strings | 7.6 |
| 51 `print()` instead logging | 7.6 |
| 52 API raw dicts | 7.6 |
| 53 `_safe_slope` slow | 7.7 |
| 54 `_log_trade` reads Parquet | 7.7 |
| 55 Revenue OS DB session dependency | architecture review in 7.6 |
| 56 Monkey-patching frozen dataclass | 7.6 |
| 57 Incomplete regime map | 6.2 |
| 58 Circuit breaker not integrated with kill switch | 3.4 |
| 59 No idempotency on state endpoints | 1.2 |
| 60 Duplicate alerting systems | 7.2 and 7.8 |
| 61 Health check does not check DB | 7.2 |
| 62 Sortino downside deviation | 6.1 |
| 63 Embargo default zero | 5.2 |
| 64 Feature docs missing | 5.1 |
| 65 DB index on equity snapshots | 7.5 or 7.7 |
| 66 Sync file write in async endpoint | 7.7 |
| 67 DuckDB SQL injection | 1.3 |
| 68 Webhook replay protection | 1.4 |
| 69 Duplicate predict calls | 7.7 |
| 70 EventBus opens file every publish | 7.7 |

Items 1-31 from the user audit were not included with file-level details. Treat them as high-priority rescans in Task 0.3 and do not mark them closed from summary alone.

## 17. Recommended Execution Order For First 10 Commits

1. Add this plan and change-control entry.
2. Add non-secret scan evidence and issue index.
3. Consolidate RiskPolicy to frozen policy.
4. Wire OMS to risk pre-check and fix BTC/ETH routing.
5. Add kill-switch close-open-position policy in demo/paper path.
6. Quarantine bad XAUUSD_D1 history and generate data truth report.
7. Build feature deletion list and freeze `features_v3` contract.
8. Unify return calculation and missing-bar policy.
9. Unify cost model and add swap/rollover decision.
10. Add CI secret scan plus fast risk/execution/data parity tests.

Reason: these commits close the highest probability "lose money or lie to yourself" paths before improving model sophistication.

## 18. Acceptance Gates Summary

### Security gate

- No current plaintext secrets.
- Rotation plan for any exposed historical secrets.
- Auth on every endpoint.
- Replay protection fixed.
- SQL injection fixed.
- Backup/restore tested.

### Data gate

- Canonical datasets have manifests.
- XAUUSD_D1 contamination removed from training.
- Multi-asset overlap truth report exists.
- Feature missingness below threshold or feature excluded.
- Macro joins are point-in-time or excluded.

### Risk/execution gate

- OMS cannot bypass risk.
- Kill switch handles open positions.
- Circuit breaker integrates with kill switch.
- Contract snapshot binds sizing.
- BTC/ETH routing correct for MT5 paper symbols.

### Parity gate

- Backtest and paper bot share return, fill, cost, symbol, and missing-bar semantics.
- Paper bot report proves actual asset weights.
- Account equity source consistent.

### ML gate

- `features_v3` documented.
- Purge and embargo proven.
- Early stopping and overfit checks active.
- Multiple testing correction applied.
- Model registry captures data and feature hashes.

### Edge gate

- Net edge positive after realistic costs, if any.
- Mean-reverting regime risk controlled.
- Portfolio PBO and DSR pass.
- DD duration acceptable.
- If not, verdict is `ARCHIVE_NO_EDGE` or `NO_GO`.

### Ops gate

- CI/CD exists.
- Prometheus/Grafana/alerts active.
- Correlation IDs present.
- Trainer healthcheck active.
- DB migrations automated.
- Runbook can guide operator handoff.

## 19. Commands To Keep As Release Spine

Run from monorepo root unless noted.

```powershell
python -m pytest graxia/packages/quant_os/tests/ --tb=short -q
python scripts/run_release_gate.py
python scripts/run_release_truth.py
python scripts/audit_full.py
python scripts/validate_data_multi_asset.py
python scripts/run_walk_forward.py
python scripts/backtest_suite.py
python scripts/paper_trade_checklist.py
```

Focused iteration commands:

```powershell
python -m pytest graxia/packages/quant_os/tests/test_risk_engine.py -q
python -m pytest graxia/packages/quant_os/tests/test_execution.py -q
python -m pytest graxia/packages/quant_os/tests/test_feature_parity.py -q
python -m pytest graxia/packages/quant_os/tests/test_lookahead_regression.py -q
python -m pytest graxia/packages/quant_os/tests/test_cost_unit_regression.py -q
python -m pytest graxia/packages/quant_os/tests/test_phase_10_micro_live.py -q
```

## 20. Final Rule

The system is allowed to become safer and more honest even if that makes reported performance worse.

If corrected evidence says there is no tradable edge, the correct outcome is not to force paper trading. The correct outcome is `ARCHIVE_NO_EDGE` or return to research with the parts that are proven useful: SMC detectors, swing high/low signal, risk engine, and auditable execution infrastructure.
