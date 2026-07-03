# Evidence Index — Quant OS Mega Plan

**Generated:** 2026-07-01
**Scope:** All evidence artifacts in `reports/`, `Meta/`, `artifacts/`

---

## Summary

| Metric | Count |
|--------|-------|
| **Total files indexed** | 67 |
| **Current (< 7 days)** | 22 |
| **Stale (> 7 days)** | 34 |
| **Missing (referenced but absent)** | 11 |

---

## Legend

- **Trust:** HIGH = recent, machine-generated, deterministic | MEDIUM = older but still relevant | LOW = stale, partial, or contradicted | N/A = not applicable
- **Status:** PASS / FAIL / WARN / INFO / STALE / MISSING
- **Verdict:** machine-extracted result from the file content

---

## 1. Data Validation

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/data_validation.json` | 2026-07-01 | FAIL | 10/16 PASS, 5 WARN, 1 FAIL | HIGH | XAUUSD D1 FAIL: 441 OHLC violations, 716 gaps. D1 historical data from 1793. H1/H4/M15 all PASS. |
| `reports/data_quality_20260626.json` | 2026-06-26 | WARN | 54 issues, all_ok=false | MEDIUM | 5-day-old scan. Issues likely still present. |

## 2. Model Training Results

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/model_training_XAUUSD.json` | 2026-07-01 | INFO | CV accuracy 63.59%, 46 features | HIGH | 5-fold CV, XGBoost, 49999 rows. F1=0.6748. |
| `reports/model_training_BTCUSD.json` | 2026-07-01 | INFO | CV accuracy 63.29%, 46 features | HIGH | 5-fold CV, XGBoost, 59999 rows. F1=0.6443. |
| `reports/model_training_ETHUSD.json` | 2026-07-01 | INFO | CV accuracy 63.15%, 46 features | HIGH | 5-fold CV, XGBoost, 59999 rows. F1=0.6507. |
| `reports/model_training_EURUSD.json` | 2026-07-01 | INFO | CV accuracy 62.99%, 46 features | HIGH | 5-fold CV, XGBoost, 49999 rows. F1=0.6278. |

## 3. Model Evaluation (Test Set)

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/model_evaluation_XAUUSD.json` | 2026-07-01 | INFO | Test accuracy 63.37%, Sharpe 39.03 | HIGH | Strategy Sharpe inflated (no-cost assumption). Cumulative return 378%. |
| `reports/model_evaluation_BTCUSD.json` | 2026-07-01 | INFO | Test accuracy 62.82%, Sharpe 39.56 | HIGH | Same concern. Cumulative return 498%. |
| `reports/model_evaluation_ETHUSD.json` | 2026-07-01 | INFO | Test accuracy 60.96%, Sharpe 34.89 | HIGH | Lowest accuracy of 4 symbols. |
| `reports/model_evaluation_EURUSD.json` | 2026-07-01 | INFO | Test accuracy 63.53%, Sharpe 40.28 | HIGH | Best accuracy. Tightest spread. |

## 4. Backtest with Costs

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/backtest_cost_XAUUSD.json` | 2026-07-01 | FAIL | Net P&L -$2933, return -29.37% | HIGH | 953 trades, win rate 41.76%, max DD 29.79%. Edge does NOT survive costs. |
| `reports/backtest_cost_BTCUSD.json` | 2026-07-01 | FAIL | Net P&L -$1670, return -16.76% | HIGH | 1176 trades, win rate 42.94%, max DD 17.24%. |
| `reports/backtest_cost_ETHUSD.json` | 2026-07-01 | WARN | Net P&L -$47, return -0.48% | HIGH | 1175 trades, win rate 45.62%, max DD 0.51%. Closest to breakeven. |
| `reports/backtest_cost_EURUSD.json` | 2026-07-01 | FAIL | Net P&L -$510, return -5.19% | HIGH | 978 trades, win rate 41.21%, max DD 5.59%. |

## 5. Dry Runs

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/dry_run_20260630_204815.json` | 2026-06-30 | INFO | 10 cycles, 1 SELL approved (10%) | MEDIUM | 5-min run, confidence=0.739, all guards 9/9 pass on trade. |
| `reports/dry_run_20260630_204243.json` | 2026-06-30 | INFO | Short dry run | MEDIUM | Same session as above. |
| `reports/dry_run_20260629_090306.json` | 2026-06-29 | INFO | 60 cycles, 11 approved (18.3%) | MEDIUM | 60-min run. 4 BUY, 7 SELL. Cooldown blocked 42 trades. Engine conservative. |
| `reports/dry_run_20260629_065836.json` | 2026-06-29 | INFO | Short dry run | MEDIUM | Same session as 090306. |
| `reports/dry_run_20260629_054050.json` | 2026-06-29 | INFO | Short dry run | MEDIUM | Asian session test. |
| `reports/dry_run_20260629_053807.json` | 2026-06-29 | INFO | 8 cycles, 0 approved (0%) | MEDIUM | All HOLD due to low confidence. Cooldown working. |
| `reports/dry_run_analysis_20260629.md` | 2026-06-29 | INFO | 60 min analysis, 18.3% approval | MEDIUM | Cooldown preventing overtrading. Signal quality needs improvement. |
| `reports/dry_run_live.log` | 2026-06-29 | INFO | Live dry run log | LOW | Log file, not machine-readable. |

## 6. Full Audits (Per-Symbol)

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/full_audit_XAUUSD.json` | 2026-07-01 | FAIL | Health 73/100, 5 features >50% null | HIGH | Lookahead PASS. Data integrity FAIL (9.4% null). Risk PASS. Code quality PASS. |
| `reports/full_audit_BTCUSD.json` | 2026-07-01 | FAIL | Health 73/100, same pattern | HIGH | Identical issue pattern to XAUUSD. |
| `reports/full_audit_ETHUSD.json` | 2026-07-01 | FAIL | Health 73/100, same pattern | HIGH | Identical issue pattern. |
| `reports/full_audit_EURUSD.json` | 2026-07-01 | FAIL | Health 73/100, same pattern | HIGH | Identical issue pattern. |
| `reports/full_audit_summary.md` | 2026-07-01 | FAIL | All 4 symbols FAIL at 73/100 | HIGH | 5 features with >50% missing: bars_since_sweep, ob_distance_atr, ob_age_bars, ob_strength, ob_mitigation_depth. |

## 7. Paper Trade Readiness

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/paper_trade_readiness.json` | 2026-07-01 | PASS | 8/9 passed, 0 required failed | HIGH | MT5 connected (Pepperstone-Demo, $49807.78). Telegram not configured (non-required). |
| `reports/b2_paper_evaluation.json` | 2026-07-01 | INFO | No closed trades yet | HIGH | Paper trade just started. No evaluation data yet. |
| `reports/paper_trade_plan.md` | 2026-07-01 | INFO | Paper trade plan | MEDIUM | Plan document, not evidence. |

## 8. Deep Audit v3

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/deep_audit_v3/AUDIT_INDEX.md` | 2026-06-29 | FAIL | 8 P0 blockers, STOP classification | MEDIUM | Critical: SL/TP midpoint bug, swap not applied, kill switch unsafe, API keys hardcoded. |
| `reports/deep_audit_v3/BACKTEST_VALIDATION_INTEGRITY.md` | 2026-06-29 | FAIL | Swap not applied in backtest | MEDIUM | P0 blocker #2. |
| `reports/deep_audit_v3/SECURITY_AUDIT.md` | 2026-06-29 | FAIL | 3 API keys hardcoded, MT5 account in git | MEDIUM | P0 blockers #6, #7, #8. |
| `reports/deep_audit_v3/RISK_EXECUTION_FORENSICS.md` | 2026-06-29 | FAIL | Kill switch crash-unsafe, pre-trade gate not wired | MEDIUM | P0 blockers #3, #4, #5. |
| `reports/deep_audit_v3/INTRABAR_EXECUTION_FIDELITY.md` | 2026-06-29 | FAIL | SL/TP uses midpoint not high/low | MEDIUM | P0 blocker #1. |
| `reports/deep_audit_v3/HONEST_SCORECARD.md` | 2026-06-29 | FAIL | 18/25 questions NO/UNVERIFIED | MEDIUM | |
| `reports/deep_audit_v3/MODEL_LIFECYCLE_AUDIT.md` | 2026-06-29 | PARTIAL | No versioning, no drift detection | MEDIUM | |
| `reports/deep_audit_v3/STATISTICAL_RIGOR_AUDIT.md` | 2026-06-29 | FAIL | No label-shuffling, no PBO/CSCV | MEDIUM | |
| `reports/deep_audit_v3/DATA_PIPELINE_FORENSICS.md` | 2026-06-29 | PARTIAL | Fill model uses midpoint | MEDIUM | |
| `reports/deep_audit_v3/DATA_INTEGRITY_CROSS_VALIDATION.md` | 2026-06-29 | PARTIAL | No independent feed cross-validation | MEDIUM | |
| `reports/deep_audit_v3/CODE_QUALITY_DEBT.md` | 2026-06-29 | PARTIAL | Orphaned code, duplicated logic | MEDIUM | |
| `reports/deep_audit_v3/BROKER_REGULATORY_AUDIT.md` | 2026-06-29 | UNVERIFIED | Pepperstone regulatory status not confirmed | MEDIUM | |
| `reports/deep_audit_v3/CAPITAL_SIZING_CAPACITY_AUDIT.md` | 2026-06-29 | PARTIAL | Kelly correct, capacity ceiling not computed | MEDIUM | |
| `reports/deep_audit_v3/DEPLOYMENT_READINESS.md` | 2026-06-29 | NOT READY | 8 P0 blockers | MEDIUM | |
| `reports/deep_audit_v3/ADVERSARIAL_STRESS_TEST.md` | 2026-06-29 | FAIL | No label-shuffling test | MEDIUM | |
| `reports/deep_audit_v3/ALPHA_COMBINATION_AUDIT.md` | 2026-06-29 | N/A | Single-strategy system | MEDIUM | |
| `reports/deep_audit_v3/LIVE_BACKTEST_PARITY.md` | 2026-06-29 | PARTIAL | Feature computation shared, fill model diverges | MEDIUM | |
| `reports/deep_audit_v3/MATH_CORRECTNESS_AUDIT.md` | 2026-06-29 | FAIL | 9 bugs found, 6 inflate metrics | MEDIUM | |
| `reports/deep_audit_v3/OBSERVABILITY_AUDIT.md` | 2026-06-29 | PARTIAL | structlog + prometheus present, no dead-man switch | MEDIUM | |
| `reports/deep_audit_v3/OPERATIONAL_CONTINUITY_AUDIT.md` | 2026-06-29 | FAIL | No runbook, crash recovery not wired | MEDIUM | |
| `reports/deep_audit_v3/OPPORTUNITY_COST_DECISION.md` | 2026-06-29 | STOP | No edge after costs | MEDIUM | |
| `reports/deep_audit_v3/PORTFOLIO_CONCURRENCY_AUDIT.md` | 2026-06-29 | N/A | Standalone strategy | MEDIUM | |
| `reports/deep_audit_v3/POST_DEPLOYMENT_MONITORING.md` | 2026-06-29 | N/A | Not yet deployed | MEDIUM | |
| `reports/deep_audit_v3/PRIORITIZED_NEXT_STEPS.md` | 2026-06-29 | INFO | 30 prioritized items | MEDIUM | |
| `reports/deep_audit_v3/REPO_CENSUS.md` | 2026-06-29 | PASS | 60+ dirs, 200+ .py files | MEDIUM | |
| `reports/deep_audit_v3/RESEARCH_METHODOLOGY_AUDIT.md` | 2026-06-29 | FAIL | Only 3 experiments logged | MEDIUM | |
| `reports/deep_audit_v3/DETERMINISM_REPRODUCIBILITY_FORENSICS.md` | 2026-06-29 | UNVERIFIED | No reproducibility test | MEDIUM | |
| `reports/deep_audit_v3/FEATURE_SIGNAL_AUDIT.md` | 2026-06-29 | PARTIAL | Only 3 experiments, no multiple testing correction | MEDIUM | |
| `reports/deep_audit_v3/TAIL_RISK_STRESS_REPLAY.md` | 2026-06-29 | UNVERIFIED | No stress-event replay | MEDIUM | |

## 9. Legacy Audit Reports

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/AUDIT_INDEX.md` | 2026-06-29 | FAIL | 8 P0 blockers, STOP classification | MEDIUM | Same as deep_audit_v3/AUDIT_INDEX.md summary. |
| `reports/FULL_REPOSITORY_AUDIT.md` | 2026-06-29 | FAIL | Full repo audit | MEDIUM | |
| `reports/CORRECTIVE_AUDIT_ADDENDUM.md` | 2026-06-29 | INFO | Corrections to prior audit | MEDIUM | |
| `reports/COMPLIANCE_MATRIX.md` | 2026-06-29 | INFO | Compliance matrix | MEDIUM | |
| `reports/G0_CANONICAL_RUNTIME_MAP.md` | 2026-06-29 | INFO | Runtime map | LOW | Phase G0 artifact. |
| `reports/G0_CLEAN_PROCESS_EVIDENCE.md` | 2026-06-29 | INFO | Clean process evidence | LOW | Phase G0 artifact. |
| `reports/G0_DATA_MANIFEST_AUDIT.md` | 2026-06-29 | INFO | Data manifest audit | LOW | Phase G0 artifact. |
| `reports/G0_ENGINE_INTEGRATION_AUDIT.md` | 2026-06-29 | INFO | Engine integration audit | LOW | Phase G0 artifact. |
| `reports/G0_FREEZE_INTEGRITY.md` | 2026-06-29 | INFO | Freeze integrity check | LOW | Phase G0 artifact. |
| `reports/G0_LEGACY_PATH_AUDIT.md` | 2026-06-29 | INFO | Legacy path audit | LOW | Phase G0 artifact. |
| `reports/G0_REPO_RECONCILIATION.md` | 2026-06-29 | INFO | Repo reconciliation | LOW | Phase G0 artifact. |
| `reports/G0_SIZING_PATH_AUDIT.md` | 2026-06-29 | INFO | Sizing path audit | LOW | Phase G0 artifact. |
| `reports/KILL_CRITERIA.md` | 2026-06-29 | INFO | Kill criteria definition | MEDIUM | |
| `reports/PHASE_2A_HARDCODE_AUDIT.md` | 2026-06-29 | INFO | Hardcode audit | MEDIUM | |
| `reports/PHASE_3_1A_1_COLLECTION_AUDIT.md` | 2026-06-29 | INFO | Collection audit | LOW | |
| `reports/PHASE_3_1A_1_LEGACY_TEST_MIGRATION_AUDIT.md` | 2026-06-29 | INFO | Test migration audit | LOW | |
| `reports/PHASE_3_1A_2_EVIDENCE.md` | 2026-06-29 | INFO | Evidence doc | LOW | |
| `reports/PHASE_3_1A_2_TEST_DISPOSITION.md` | 2026-06-29 | INFO | Test disposition | LOW | |
| `reports/PHASE_3B_SCENARIOS.md` | 2026-06-29 | INFO | Scenario analysis | LOW | |
| `reports/PHASE_G4_1_DEFINITION.md` | 2026-06-29 | INFO | Phase G4 definition | LOW | |
| `reports/PARQUET_MIGRATION_PLAN.md` | 2026-06-29 | INFO | Parquet migration plan | LOW | |

## 10. Phase Reports

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/REPORT_PHASE_1R_H.md` | pre-2026-06-29 | INFO | Phase 1R report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_2.md` | pre-2026-06-29 | INFO | Phase 2 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_3.md` | pre-2026-06-29 | INFO | Phase 3 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_3_1_ENGINE_INTEGRATION.md` | pre-2026-06-29 | INFO | Engine integration report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_3_2_MT5_READINESS.md` | pre-2026-06-29 | INFO | MT5 readiness report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_3_3_NEWS_EVENTS.md` | pre-2026-06-29 | INFO | News events report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_3B.md` | pre-2026-06-29 | INFO | Phase 3B report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_4.md` | pre-2026-06-29 | INFO | Phase 4 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_5.md` | pre-2026-06-29 | INFO | Phase 5 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_6.md` | pre-2026-06-29 | INFO | Phase 6 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_7.md` | pre-2026-06-29 | INFO | Phase 7 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_8.md` | pre-2026-06-29 | INFO | Phase 8 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_9.md` | pre-2026-06-29 | INFO | Phase 9 report | LOW | Historical phase report. |
| `reports/REPORT_PHASE_10.md` | pre-2026-06-29 | INFO | Phase 10 report | LOW | Historical phase report. |
| `reports/REPORT_G0.md` | pre-2026-06-29 | INFO | Phase G0 report | LOW | |
| `reports/REPORT_G0_RUNTIME_TRUTH.md` | pre-2026-06-29 | INFO | Runtime truth report | LOW | |
| `reports/REPORT_G3_SOURCE_INTEGRITY_AUDIT.md` | pre-2026-06-29 | INFO | Source integrity audit | LOW | |
| `reports/REPORT_G3_SOURCE_PROVENANCE_RECOVERY.md` | pre-2026-06-29 | INFO | Source provenance recovery | LOW | |
| `reports/REPORT_G4_FINAL_EXECUTION_GUIDE.md` | pre-2026-06-29 | INFO | Final execution guide | LOW | |
| `reports/REPORT_G4_PRE_EXECUTION_AUDIT.md` | pre-2026-06-29 | INFO | Pre-execution audit | LOW | |
| `reports/REPORT_QUALITY_CI_Q7_FINAL.md` | pre-2026-06-29 | INFO | Quality CI final | LOW | |

## 11. Research & Analysis

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/cost_analysis.md` | 2026-06-29 | INFO | Cost analysis | MEDIUM | |
| `reports/broker_comparison_pepperstone_vs_icmarkets_thai.md` | 2026-06-29 | INFO | Broker comparison | MEDIUM | Pepperstone recommended for Thai user. |
| `reports/broker_cfd_terms.md` | 2026-06-29 | INFO | CFD terms | LOW | |
| `reports/cross_asset_features_xauusd.md` | 2026-06-29 | INFO | Cross-asset features | MEDIUM | 10Y real yield, DXY, VIX research. |
| `reports/data_pipeline_deep_dive.md` | 2026-06-29 | INFO | Data pipeline deep dive | MEDIUM | |
| `reports/data_quality_research_2026.md` | 2026-06-29 | INFO | Data quality research | LOW | |
| `reports/edge_detection_research.md` | 2026-06-29 | INFO | Edge detection research | LOW | |
| `reports/ml_training_best_practices_2026.md` | 2026-06-29 | INFO | ML training best practices | LOW | |
| `reports/risk_management_research.md` | 2026-06-29 | INFO | Risk management research | LOW | |
| `reports/RESEARCH_BUNDLE.md` | 2026-06-29 | INFO | Research bundle | LOW | |
| `reports/MULTI_BROKER_GUIDE.md` | 2026-06-29 | INFO | Multi-broker guide | LOW | |
| `reports/RUNBOOK.md` | 2026-06-29 | INFO | Runbook | MEDIUM | |
| `reports/paper_trades/daily_2026-07-01.md` | 2026-07-01 | INFO | Daily paper trade log | HIGH | Most recent paper trade activity. |
| `reports/mega_plan_evidence/MASTER_GAP_REPORT.md` | 2026-07-01 | INFO | Master gap report | HIGH | |
| `reports/mega_plan_evidence/security_scan.md` | 2026-07-01 | INFO | Security scan | HIGH | |

## 12. Meta/ Directory

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `Meta/execution_plan.md` | 2026-06-26 | INFO | Execution plan | MEDIUM | 28-day B2 paper trade plan. |
| `Meta/pre_register_b2.md` | 2026-06-26 | INFO | B2 pre-registration | MEDIUM | |
| `Meta/pre_register_config2.md` | 2026-06-26 | INFO | Config pre-registration | MEDIUM | |
| `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md` | 2026-07-01 | INFO | Unified mega remediation plan | HIGH | Most current plan document. |
| `Meta/graxia_mega_plan_v3.md` | 2026-06-29 | INFO | Mega plan v3 | MEDIUM | |
| `Meta/stop_loss_audit.md` | 2026-06-26 | INFO | Stop loss audit | MEDIUM | |
| `Meta/broker_verification_report.md` | 2026-06-26 | INFO | Broker verification | MEDIUM | |
| `Meta/connectivity_log.md` | 2026-06-26 | INFO | Connectivity log | MEDIUM | |
| `Meta/bridge_deploy_state.md` | 2026-06-26 | INFO | Bridge deploy state | MEDIUM | |
| `Meta/deployment_runbook.md` | 2026-06-26 | INFO | Deployment runbook | LOW | |
| `Meta/aws_deployment_guide.md` | 2026-06-26 | INFO | AWS deployment guide | LOW | |
| `Meta/gcloud_deployment_guide.md` | 2026-06-26 | INFO | GCloud deployment guide | LOW | |
| `Meta/strategy_redesign_plan.md` | 2026-06-26 | INFO | Strategy redesign plan | MEDIUM | |
| `Meta/multi_asset_redesign_progress.md` | 2026-06-26 | INFO | Multi-asset redesign progress | MEDIUM | |
| `Meta/multi_horizon_portfolio_redesign_plan.md` | 2026-06-26 | INFO | Portfolio redesign plan | LOW | |
| `Meta/exit_risk_research_b3.md` | 2026-06-26 | INFO | Exit risk research B3 | LOW | |
| `Meta/swap_rates.md` | 2026-06-26 | INFO | Swap rates | MEDIUM | |
| `Meta/research_edge_cost_report.md` | 2026-06-26 | INFO | Edge cost report | MEDIUM | |
| `Meta/deep_research_report.md` | 2026-06-26 | INFO | Deep research report | LOW | |
| `Meta/honest_web_research_report.md` | 2026-06-26 | INFO | Honest web research | LOW | |
| `Meta/bridge_real_web_research_report.md` | 2026-06-26 | INFO | Bridge web research | LOW | |
| `Meta/master_deep_research_synthesis.md` | 2026-06-26 | INFO | Master synthesis | LOW | |
| `Meta/verified_sources_report.md` | 2026-06-26 | INFO | Verified sources | LOW | |
| `Meta/data_manifest.json` | 2026-06-26 | INFO | 15 symbols, 45 TF combos | MEDIUM | Older manifest, may be stale. |
| `Meta/health_check.json` | 2026-06-26 | PASS | 7 passed, 0 failed | MEDIUM | 5-day-old health check. |
| `Meta/bridge_manifest.json` | 2026-06-26 | INFO | 42 synced files | MEDIUM | |
| `Meta/upgrade_pipeline_manifest.json` | 2026-06-26 | INFO | Last run 2026-06-26, 45 downloads | MEDIUM | Pipeline not re-run since. |
| `Meta/latest_dashboard.json` | 2026-06-26 | INFO | Dashboard snapshot | LOW | |
| `Meta/research/*.md` (17 files) | 2026-06-26 | INFO | Research documents | LOW | All pre-2026-06-29 research. |
| `Meta/states/*.md` (50+ files) | 2026-06-26 | INFO | Agent state snapshots | LOW | Historical state files. |

## 13. Alternative Data

| Path | Date | Status | Verdict | Trust | Notes |
|------|------|--------|---------|-------|-------|
| `reports/alternative_data_research.json` | 2026-06-26 | INFO | COT, MT5, yfinance, FRED all OK | MEDIUM | 5-day-old. MT5 terminal confirmed. 6 FRED parquet files in data/macro/. |
| `reports/yfinance_ticker_results.json` | 2026-06-26 | INFO | 30/31 tickers OK, XAUUSD=X empty | MEDIUM | XAUUSD spot from yfinance unavailable (expected). |

---

## Missing Evidence (Referenced but Not in Repo)

| # | Expected Item | Status | Notes |
|---|---------------|--------|-------|
| 1 | Live trade execution logs (real broker) | MISSING | Paper trade just started, no live execution logs yet. |
| 2 | Broker execution quality report (slippage, fill rates) | MISSING | Not yet generated. Need live/paper trade data. |
| 3 | Live P&L tracking (daily/weekly) | MISSING | Paper trade B2 started but no P&L tracker file found. |
| 4 | Strategy performance attribution (per-strategy breakdown) | MISSING | Only single ML strategy, no attribution needed. |
| 5 | Walk-forward out-of-sample results (v5, 1h) | MISSING | walk_forward_v5_1h/ dir exists in artifacts but no summary JSON. |
| 6 | Label shuffling test results | MISSING | Referenced as P0 in deep audit. Never run. |
| 7 | SPRT live monitoring baseline | MISSING | Referenced in deep audit next steps. Not implemented. |
| 8 | Capacity ceiling / slippage scaling test | MISSING | Referenced in deep audit P2. Not run. |
| 9 | Tail-event stress replay (SNB/COVID/Brexit) | MISSING | Referenced in deep audit. Not performed. |
| 10 | Operational runbook (start/stop/kill-switch) | MISSING | RUNBOOK.md exists but may be incomplete. |
| 11 | Telegram bot configuration | MISSING | paper_trade_readiness.json shows Telegram not configured. |

---

## Key Findings

1. **All 4 backtests are net losers** after costs: XAUUSD -29.37%, BTCUSD -16.76%, EURUSD -5.19%, ETHUSD -0.48%.
2. **All 4 full audits FAIL at 73/100** due to 5 features with >50% missing values.
3. **8 P0 blockers** identified in deep audit v3 (2026-06-29) — none appear fixed as of 2026-07-01.
4. **Model accuracy is marginal** (60-64% across all symbols) — edge is not robust.
5. **Paper trade readiness PASS** (8/9 items) — system is technically ready to paper trade.
6. **Dry runs show conservative behavior** — cooldown prevents overtrading, confidence threshold works.
7. **No live/paper trade P&L data yet** — B2 paper trade evaluation shows 0 closed trades.
8. **Most Meta/ and research files are 5+ days old** — stale but still relevant for context.
9. **Critical security issues** from deep audit (hardcoded API keys, MT5 account in git) — status unknown if fixed.
