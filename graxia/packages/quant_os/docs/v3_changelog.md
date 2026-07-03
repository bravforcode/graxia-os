# GRAXIA-OS v3.0 Changelog

> **Release Date**: 2026-06-26 | **Supersedes**: v2.0
> **Source Document**: `Meta/graxia_mega_plan_v3.md`
> **Capital**: $5,000 | **Symbol**: XAUUSD M15 | **Broker**: Pepperstone ECN Razor

---

## Bug Fixes (9 total)

| Bug | Severity | Description | File(s) | Fix |
|-----|----------|-------------|---------|-----|
| #1 | CRITICAL | PnL multiplier hardcoded at 2350 | `walk_forward.py:76` | Use actual bar close price array (`test_close_prices`) |
| #2 | HIGH | Cost model: double-counted commission + stale constant | `walk_forward.py` | Pull live spread from MT5; XAUUSD Razor commission embedded in spread |
| #3 | CRITICAL | Data leakage: train_acc=100% from un-purged CV | `core/cross_validation.py` | CombinatorialPurgedCV with both `purged_size` + `embargo_size` |
| #4 | HIGH | Paper trade not running | `run_paper_trading.py` | Automation wired after Day 1 fixes |
| #5 | HIGH | Walk-Forward tests only ONE backtest path | `backtest/walk_forward.py` | CPCV with 15+ independent paths → PBO calculation |
| #6 | HIGH | No regime conditioning | `core/regime_detector.py` (new) | Primary: Sparse JM (`jumpmodels`); Secondary: HMM (`hmmlearn`) |
| #7 | MEDIUM | No SMC microstructure features | `scripts/features_advanced.py` | `smartmoneyconcepts` (corrected package name) |
| #8 | NEW | No swap/overnight financing cost modeled | `core/risk/swap_cost.py` (new) | Live swap rates from MT5 + TomNext triple-charge handling |
| #9 | NEW | NautilusTrader MT5 adapter doesn't exist | `shadow/canonical_bar_builder.py` | NT used offline only; live execution via `MetaTrader5` |

---

## New Code Modules Created

### v3-Specific Modules
- `core/risk/swap_cost.py` — Live swap rate fetching + overnight cost estimator (Bug #8)
- `core/regime_detector.py` — Jump Model (primary) + HMM (secondary) regime detection (Bug #6)
- `core/data/point_in_time_store.py` — Point-in-time external data staging (prevents lookahead)
- `core/risk/monte_carlo.py` — Bootstrap equity paths + risk-of-ruin simulation (§2.4)
- `scripts/reconcile_data_sources.py` — Dukascopy vs Pepperstone MT5 cross-source comparison (§5C)

### v3 Utility Scripts
- `scripts/verify_v3_imports.py` — Comprehensive library import verification
- `scripts/features_advanced.py` — SMC microstructure feature extraction (Bug #7)

---

## Library Corrections (F1–F10 Findings)

See `Meta/graxia_mega_plan_v3.md` §0.3 for full details.

| Finding | v2.0 Said | v3.0 Finding | Status |
|---------|-----------|-------------|--------|
| F1 | `pip install smart-money-concepts` | Real name: `smartmoneyconcepts` (no hyphens) | ✅ Fixed |
| F2 | `pip install mlfinlab` (free) | Closed-source since ~2021. Use `mlfinpy` or direct implementation | ✅ Documented |
| F3 | NautilusTrader as live MT5 validator | No MT5 adapter exists. Offline backtest only | ✅ Redesigned |
| F4 | `skfolio` with only `purged_size` | Needs both `purged_size` + `embargo_size` | ✅ Fixed |
| F5 | Cost: spread only, no overnight | Swap/overnight cost unmodeled anywhere | ✅ Fixed (Bug #8) |
| F6 | vectorbt free + maintained | Community-maintained edition, fine for research | ⚠️ Noted |
| F7 | HMM only regime detector | Sparse JM added as primary; HMM demoted to secondary | ✅ Upgraded |
| F8 | COT via manual ZIP download | `cot_reports` library + CFTC Socrata REST API | ✅ Automated |
| F9 | Deflated Sharpe/PBO conceptual | `pypbo` intended but uninstallable; manual fallback | ⚠️ Documented |
| F10 | Thai regulatory not addressed | Brief note added (§17.5); not legal advice | ⚠️ Noted |

---

## Architecture Changes

### Dual-Engine Redesign (§6)
- **v2.0**: NautilusTrader bridged to live MT5 for "production validation" (impossible — no adapter)
- **v3.0**: NautilusTrader runs **offline on historical Dukascopy Parquet bars** as a second independent backtest engine. Different fill/slippage model = useful disagreement signal.
- **Live execution**: MetaTrader5 Python package → Pepperstone directly. No change.

### Regime Detector Upgrade (§8 / §11C)
- **v2.0**: HMM (GaussianHMM) as sole regime detector
- **v3.0**:
  - PRIMARY: Statistical Jump Model (`jumpmodels`) — penalizes state switching directly, better with fat-tailed gold returns
  - SECONDARY: HMM (`hmmlearn`) — cross-check; if JM and HMM disagree >X%, that's a regime-uncertainty signal
  - Sparse JM also does automatic feature selection

### Cost Model Overhaul (§1 / §9)
- **v2.0**: Hardcoded `COST_PER_TRADE = 0.345` (wrong for metals)
- **v3.0**:
  - Live spread pulled from MT5 terminal every session (not hardcoded)
  - XAUUSD Razor: commission embedded in spread (no separate per-side fee)
  - Session-segmented spread costs (Asian vs London vs NY vs overlap)
  - Swap/overnight financing modeled (prevents silent cost underestimation)
  - `swap_cost` column added to every backtest trade row

### Risk Framework Additions
- **Monte Carlo risk-of-ruin** simulation (new §2.4) — runs before every lot increase
- **Dual-VPS failover** (new §4D) — standby VPS takes over if primary dead >30min
- **Telegram alerting enhanced** — prob_ruin at current lot in daily heartbeat

---

## Test Coverage Summary

### Test Files (all phases)
```
tests/test_phase_be_p0.py       tests/test_phase_2a.py
tests/test_phase_be_p1.py       tests/test_phase_2b.py
tests/test_phase_1r_h_integration.py
tests/test_phase_3.py           tests/test_phase_3_order.py
tests/test_phase_3_1_engine_integration.py
tests/test_phase_3_2_market_data.py
tests/test_phase_3_3_news_events.py
tests/test_phase_3b_exit_gate.py
tests/test_phase_3b_native.py   tests/test_phase_3b_regime.py
tests/test_phase_4_eurusd_restored.py
tests/test_phase_4_integration_restored.py
tests/test_phase_5_bootstrap.py
tests/test_phase_5_cost_stress.py
tests/test_phase_5_governance.py
tests/test_phase_5_integration.py
tests/test_phase_5_statistical.py
tests/test_phase_5_validation.py
tests/test_phase_5_verdict.py
tests/test_phase_6_integration_restored.py
tests/test_phase_6_shadow.py
tests/test_phase_6_shadow_runner.py
tests/test_phase_7_canary_policy_restored.py
tests/test_phase_7_integration_restored.py
tests/test_phase_7_reconciliation.py
tests/test_phase_8_drills.py
tests/test_phase_8_integration_restored.py
tests/test_phase_9_integration.py
tests/test_phase_9_review.py
tests/test_phase_10_expansion.py
tests/test_phase_10_integration.py
tests/test_phase_10_micro_live.py
tests/test_phase_11_expansion.py
tests/test_phase_11_integration.py
tests/test_e2e_critical_incident.py
tests/test_e2e_full_pipeline.py
tests/test_e2e_next_bar_entry.py
tests/test_e2e_trade_ledger_provenance.py
tests/test_quarantine_integrity.py
tests/test_release_reproducibility.py
tests/test_lookahead_regression.py
tests/test_risk_engine.py
tests/test_position_sizer_numeric.py
```

### Module-Local Tests
```
cost/test_cost_model_labeled.py     cost/test_cost_stress.py
cost/test_forbidden_shortcuts.py    cost/test_pipeline_latency.py
cost/test_quote_calibration.py      cost/test_be_p4_integration.py
events/test_event_gate.py           events/test_event_metrics.py
events/test_event_risk_gate.py      events/test_event_schema.py
events/test_market_health.py        events/test_event_isolation.py
events/test_be_p3_integration.py
validation/test_archive_reasons.py  validation/test_auto_blockers.py
validation/test_dataset_protocol.py validation/test_decision_gates.py
validation/test_evidence_pack.py    validation/test_promotion_review.py
validation/test_revalidation_runner.py
validation/test_review_report.py    validation/test_threshold_evaluator.py
validation/test_be_p6_integration.py validation/test_be_p11_integration.py
shadow/test_* (12 files)
canary/test_* (12 files)
oracle/test_* (8 files)
micro_live/test_* (7 files)
expansion/test_* (5 files)
runtime/test_* (3 files)
ticks/test_* (6 files)
regime/test_* (6 files)
gold_bot/tests/ (3 files)
repo_intelligence/tests/ (2 files)
```

---

## Library Installation Summary (2026-06-26)

| Category | Count | Status |
|----------|-------|--------|
| Installed & working | 26 | ✅ |
| Requires workaround | 1 | ⚠️ (smartmoneyconcepts: PYTHONIOENCODING) |
| Substitute needed | 1 | ⚠️ (fracdiff → fracdiff2) |
| Broken (incompatible) | 1 | ❌ (deepchecks vs sklearn 1.9) |
| Not installable | 1 | ❌ (pypbo — manual implementation only) |
| **Total libraries** | **29** | |

See `docs/library_integration_map.md` for per-library details and workarounds.

---

## Files Created This Session

1. `scripts/verify_v3_imports.py` — Library import verification script
2. `requirements.txt` — Pinned dependency list (5 sections)
3. `docs/library_integration_map.md` — Library-to-module mapping + known issues
4. `docs/v3_changelog.md` — This file
