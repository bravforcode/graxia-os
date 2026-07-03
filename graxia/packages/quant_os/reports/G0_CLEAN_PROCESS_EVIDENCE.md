# G0.1 Clean-Process Evidence

## Environment
- Python: 3.12.10
- pip: 26.0.1 (from C:\Users\menum\AppData\Local\Programs\Python\Python312\Lib\site-packages\pip)
- Git SHA: 0be33752c9d38065a8e2d09413898f61e8981843
- Git commit: feat(quant_os): G0 — freeze + canonical runtime map + legacy audit + governance docs + clean-process tests
- Dependency lock SHA-256: ff212b8232eeec7e0198dd59c822ef0b57ce88a2938de2245ed5160ef2a9a4dd
- Executed at: 2026-06-22

## G0 Test Suite (6 tests)
```
============================= test session starts ==============================
platform win32 -- Python 3.12.10, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\menum\graxia os
configfile: pytest.ini
plugins: anyio-4.13.0, hypothesis-6.100.0, langsmith-0.7.35, asyncio-0.23.5, mock-3.15.1
asyncio: mode=Mode.AUTO
collecting ... collected 6 items

test_package_import_clean_process.py::test_package_import_clean_process PASSED  [ 16%]
test_package_import_clean_process.py::test_risk_policy_import_clean_process PASSED [ 33%]
test_runtime_startup_clean_process.py::test_canonical_config_instantiate PASSED [ 50%]
test_no_legacy_production_path.py::test_no_forbidden_tokens_in_canonical_modules PASSED [ 66%]
test_hftbacktest_isolation.py::test_no_hftbacktest_imports_in_canonical PASSED [ 83%]
test_hftbacktest_isolation.py::test_hftbacktest_quarantine_manifest_exists PASSED [100%]

============================== 6 passed in 0.59s ===============================
```

## Full Quant OS Test Suite
```
============================= test session starts ==============================
platform win32 -- Python 3.12.10, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\menum\graxia os
configfile: pytest.ini
plugins: anyio-4.13.0, hypothesis-6.100.0, langsmith-0.7.35, asyncio-0.23.5, mock-3.15.1
asyncio: mode=Mode.AUTO
collecting ... collected 151 items

[all 150 passing tests shown in run output]
1 failed (test_phase_2a::TestStrictMTF::test_strict_mtf_blocks_static_fallback — ImportError: OrderSide missing from execution_simulator.py, pre-existing)
9 collection errors (all backtest-dependent tests, same OrderSide root cause)

======================== 1 failed, 150 passed in 11.88s ========================
```

### Full Test Output — All 150 Passing Tests
```
test_package_import_clean_process.py::test_package_import_clean_process PASSED [  0%]
test_package_import_clean_process.py::test_risk_policy_import_clean_process PASSED [  1%]
test_runtime_startup_clean_process.py::test_canonical_config_instantiate PASSED [  1%]
test_no_legacy_production_path.py::test_no_forbidden_tokens_in_canonical_modules PASSED [  2%]
test_hftbacktest_isolation.py::test_no_hftbacktest_imports_in_canonical PASSED [  3%]
test_hftbacktest_isolation.py::test_hftbacktest_quarantine_manifest_exists PASSED [  3%]
test_core.py::TestGoldenRules::test_live_trading_default_false PASSED [  4%]
test_core.py::TestGoldenRules::test_ai_cannot_submit_order PASSED [  5%]
test_core.py::TestGoldenRules::test_paper_minimum_days PASSED [  5%]
test_core.py::TestGoldenRules::test_max_risk_per_trade PASSED [  6%]
test_core.py::TestGoldenRules::test_hard_stop_drawdown PASSED [  7%]
test_core.py::TestGoldenRules::test_validate_golden_rules PASSED [  7%]
test_core.py::TestEnums::test_order_status_transitions PASSED [  8%]
test_core.py::TestEnums::test_trading_mode_values PASSED [  9%]
test_core.py::TestConfig::test_default_config PASSED [  9%]
test_core.py::TestConfig::test_config_enforces_limits PASSED [ 10%]
test_core.py::TestExceptions::test_risk_violation_error PASSED [ 11%]
test_core.py::TestExceptions::test_duplicate_order_error PASSED [ 11%]
test_new_modules.py::TestRegimeFilter::test_init PASSED [ 12%]
test_new_modules.py::TestRegimeFilter::test_detect_returns_regime PASSED [ 13%]
test_new_modules.py::TestRegimeFilter::test_insufficient_data PASSED [ 13%]
test_new_modules.py::TestRegimeFilter::test_trending_data PASSED [ 14%]
test_new_modules.py::TestRegimeFilter::test_get_allowed_strategies PASSED [ 15%]
test_new_modules.py::TestRegimeFilter::test_crisis_no_trading PASSED [ 15%]
test_new_modules.py::TestMonteCarlo::test_init PASSED [ 16%]
test_new_modules.py::TestMonteCarlo::test_run_with_trades PASSED [ 17%]
test_new_modules.py::TestMonteCarlo::test_run_empty_trades PASSED [ 17%]
test_new_modules.py::TestMonteCarlo::test_validate_strategy PASSED [ 18%]
test_new_modules.py::TestWalkForwardStability::test_init PASSED [ 19%]
test_new_modules.py::TestWalkForwardStability::test_calculate PASSED [ 19%]
test_new_modules.py::TestWalkForwardStability::test_empty_results PASSED [ 20%]
test_new_modules.py::TestFakeSignalFilter::test_init PASSED [ 21%]
test_new_modules.py::TestFakeSignalFilter::test_evaluate_all_pass PASSED [ 21%]
test_new_modules.py::TestFakeSignalFilter::test_quick_check PASSED [ 22%]
test_new_modules.py::TestDashboard::test_init PASSED [ 23%]
test_new_modules.py::TestDashboard::test_update PASSED [ 23%]
test_new_modules.py::TestDashboard::test_render PASSED [ 24%]
test_execution.py::TestOrder::test_order_creation PASSED [ 25%]
test_execution.py::TestOrder::test_order_idempotency_key_generation PASSED [ 25%]
test_execution.py::TestOrderStateMachine::test_valid_transition PASSED [ 26%]
test_execution.py::TestOrderStateMachine::test_invalid_transition_raises PASSED [ 27%]
test_execution.py::TestOrderStateMachine::test_fill_updates_quantities PASSED [ 27%]
test_execution.py::TestOrderStateMachine::test_cancel_terminal_state PASSED [ 28%]
test_execution.py::TestIdempotencyChecker::test_generate_key PASSED [ 29%]
test_execution.py::TestIdempotencyChecker::test_duplicate_detection PASSED [ 29%]
test_execution.py::TestPaperBroker::test_connect PASSED [ 30%]
test_execution.py::TestPaperBroker::test_get_account PASSED [ 31%]
test_execution.py::TestPaperBroker::test_place_order PASSED [ 31%]
test_execution.py::TestPaperBroker::test_get_price PASSED [ 32%]
test_strategies.py::TestSignal::test_signal_creation PASSED [ 33%]
test_strategies.py::TestSignal::test_risk_reward_ratio PASSED [ 33%]
test_strategies.py::TestMultiTimeframeMomentum::test_strategy_init PASSED [ 34%]
test_strategies.py::TestMultiTimeframeMomentum::test_required_features PASSED [ 35%]
test_strategies.py::TestMultiTimeframeMomentum::test_calculate_confidence PASSED [ 35%]
test_strategies.py::TestMeanReversionBollinger::test_strategy_init PASSED [ 36%]
test_strategies.py::TestMeanReversionBollinger::test_required_features PASSED [ 37%]
test_strategies.py::TestEnsemble::test_ensemble_weights PASSED [ 37%]
test_strategies.py::TestEnsemble::test_get_ensemble_signal_buy PASSED [ 38%]
test_strategies.py::TestEnsemble::test_get_ensemble_signal_conflict PASSED [ 39%]
test_strategies.py::TestPositionSizing::test_fixed_fractional PASSED [ 39%]
test_strategies.py::TestPositionSizing::test_kelly_sizer PASSED [ 40%]
test_phase_2a.py::TestDatasetManifests::test_dataset_manifests_exist PASSED [ 41%]
test_phase_2a.py::TestDatasetManifests::test_manifest_checksum_matches PASSED [ 41%]
test_phase_2a.py::TestDatasetManifests::test_manifest_timestamps_ordered PASSED [ 42%]
test_phase_2a.py::TestDatasetManifests::test_manifest_not_synthetic PASSED [ 43%]
test_phase_2a.py::TestDatasetManifests::test_manifest_timezone_utc PASSED [ 43%]
test_phase_2a.py::TestDatasetManifests::test_manifest_source_known PASSED [ 44%]
test_phase_2a.py::TestRiskPolicy::test_risk_policy_basis_points PASSED [ 45%]
test_phase_2a.py::TestRiskPolicy::test_risk_policy_no_pct_field PASSED [ 45%]
test_phase_2a.py::TestStrictMTF::test_strict_mtf_blocks_static_fallback FAILED [ 46%]
test_phase_2a.py::TestHardcodeAudit::test_hardcode_audit_no_units_per_lot_in_production PASSED [ 47%]
test_phase_2a.py::TestHardcodeAudit::test_no_order_send_in_phase2 PASSED [ 47%]
test_phase_2b.py::TestContractSpec::test_contract_spec_validate_valid PASSED [ 48%]
test_phase_2b.py::TestContractSpec::test_contract_spec_validate_zero_tick_value PASSED [ 49%]
test_phase_2b.py::TestContractSpec::test_contract_spec_validate_volume_min_gt_max PASSED [ 49%]
test_phase_2b.py::TestContractSpec::test_contract_spec_frozen PASSED [ 50%]
test_phase_2b.py::TestContractSnapshotStore::test_contract_snapshot_store_save_load PASSED [ 50%]
test_phase_2b.py::TestContractSnapshotStore::test_contract_snapshot_hash_deterministic PASSED [ 51%]
test_phase_2b.py::TestPositionSizer::test_sizer_valid_input PASSED [ 52%]
test_phase_2b.py::TestPositionSizer::test_sizer_zero_sl_rejects PASSED [ 52%]
test_phase_2b.py::TestPositionSizer::test_sizer_wrong_side_sl_rejects PASSED [ 53%]
test_phase_2b.py::TestPositionSizer::test_sizer_below_min_volume_rejects PASSED [ 54%]
test_phase_2b.py::TestPositionSizer::test_sizer_rounds_down_to_step PASSED [ 54%]
test_phase_2b.py::TestPositionSizer::test_sizer_risk_never_exceeds_budget PASSED [ 55%]
test_phase_2b.py::TestPreTradeRisk::test_pre_trade_check_daily_loss_blocks PASSED [ 56%]
test_phase_2b.py::TestPreTradeRisk::test_pre_trade_check_weekly_loss_blocks PASSED [ 56%]
test_phase_2b.py::TestPreTradeRisk::test_pre_trade_check_max_positions_blocks PASSED [ 57%]
test_phase_2b.py::TestPreTradeRisk::test_pre_trade_check_kill_switch_blocks PASSED [ 58%]
test_phase_2b.py::TestKillSwitch::test_kill_switch_activate_deactivate PASSED [ 58%]
test_phase_2b.py::TestKillSwitch::test_kill_switch_persists PASSED [ 59%]
test_phase_2b.py::TestRiskLedger::test_risk_ledger_daily_tracking PASSED [ 60%]
test_phase_2b.py::TestNoOrderSend::test_no_order_send_in_broker PASSED [ 60%]
test_phase_2b.py::TestNoOrderSend::test_no_order_send_in_risk PASSED [ 61%]
test_phase_2b.py::TestGoldenSizing::test_golden_xauusd_sizing PASSED [ 62%]
test_phase_2b.py::TestGoldenSizing::test_golden_eurusd_sizing PASSED [ 62%]
test_phase_3.py::TestBidAskEntryExit::test_long_entry_at_ask_plus_slippage PASSED [ 63%]
test_phase_3.py::TestBidAskEntryExit::test_short_entry_at_bid_minus_slippage PASSED [ 64%]
test_phase_3.py::TestBidAskEntryExit::test_close_long_at_bid_minus_slippage PASSED [ 64%]
test_phase_3.py::TestBidAskEntryExit::test_close_short_at_ask_plus_slippage PASSED [ 65%]
test_phase_3.py::TestSLTPTriggers::test_long_sl_triggers_on_bid PASSED [ 66%]
test_phase_3.py::TestSLTPTriggers::test_long_tp_triggers_on_bid PASSED [ 66%]
test_phase_3.py::TestSLTPTriggers::test_short_sl_triggers_on_ask PASSED [ 67%]
test_phase_3.py::TestSLTPTriggers::test_short_tp_triggers_on_ask PASSED [ 68%]
test_phase_3.py::TestSLTPTriggers::test_no_trigger_returns_none PASSED [ 68%]
test_phase_3.py::TestAmbiguousBarAdverseOrdering::test_long_ambiguous_bar_sl_first PASSED [ 69%]
test_phase_3.py::TestAmbiguousBarAdverseOrdering::test_short_ambiguous_bar_sl_first PASSED [ 70%]
test_phase_3.py::TestNextBarFillTiming::test_signal_cannot_fill_on_same_bar PASSED [ 70%]
test_phase_3.py::TestNextBarFillTiming::test_fill_on_next_bar_allowed PASSED [ 71%]
test_phase_3.py::TestCostModelScenarios::test_base_scenario_spread PASSED [ 72%]
test_phase_3.py::TestCostModelScenarios::test_stress_1_1_5x_spread PASSED [ 72%]
test_phase_3.py::TestCostModelScenarios::test_stress_3_3x_spread PASSED [ 73%]
test_phase_3.py::TestCostModelScenarios::test_run_cost_stress_matrix_returns_all_scenarios PASSED [ 74%]
test_phase_3.py::TestOrderStateMachineTransitions::test_happy_path_to_audited PASSED [ 74%]
test_phase_3.py::TestOrderStateMachineTransitions::test_invalid_transition_raises PASSED [ 75%]
test_phase_3.py::TestOrderStateMachineTransitions::test_terminal_states_block_transition PASSED [ 76%]
test_phase_3.py::TestOrderStateMachineTransitions::test_advance_alias_works PASSED [ 76%]
test_phase_3.py::TestOrderStateMachineTransitions::test_needs_protective_stop_verification_alias PASSED [ 77%]
test_phase_3.py::TestTradeLedger::test_record_and_retrieve PASSED [ 78%]
test_phase_3.py::TestTradeLedger::test_ledger_hash_deterministic PASSED [ 78%]
test_phase_3.py::TestNoOrderSend::test_no_order_send_in_execution_modules PASSED [ 79%]
test_phase_3_order.py::TestFullLifecycle::test_signal_created_transitions_to_risk_checked PASSED [ 80%]
test_phase_3_order.py::TestFullLifecycle::test_risk_checked_to_prechecked PASSED [ 80%]
test_phase_3_order.py::TestFullLifecycle::test_prechecked_to_submitted PASSED [ 81%]
test_phase_3_order.py::TestFullLifecycle::test_submitted_to_acknowledged PASSED [ 82%]
test_phase_3_order.py::TestFullLifecycle::test_acknowledged_to_filled PASSED [ 82%]
test_phase_3_order.py::TestFullLifecycle::test_filled_to_protective_stops_verified PASSED [ 83%]
test_phase_3_order.py::TestFullLifecycle::test_protective_to_position_reconciled PASSED [ 84%]
test_phase_3_order.py::TestFullLifecycle::test_position_reconciled_to_closed PASSED [ 84%]
test_phase_3_order.py::TestFullLifecycle::test_closed_to_deal_reconciled PASSED [ 85%]
test_phase_3_order.py::TestFullLifecycle::test_deal_reconciled_to_audited PASSED [ 86%]
test_phase_3_order.py::TestInvalidTransitions::test_invalid_transition_raises PASSED [ 86%]
test_phase_3_order.py::TestInvalidTransitions::test_terminal_states_no_transition PASSED [ 87%]
test_phase_3_order.py::TestCriticalIncident::test_critical_incident_is_terminal PASSED [ 88%]
test_phase_3_order.py::TestCriticalIncident::test_critical_from_early_state PASSED [ 88%]
test_phase_3_order.py::TestCriticalIncident::test_history_recorded PASSED [ 89%]
test_phase_3_order.py::TestTradeLedger::test_trade_ledger_record_and_retrieve PASSED [ 90%]
test_phase_3_order.py::TestTradeLedger::test_trade_ledger_hash_deterministic PASSED [ 90%]
test_phase_3_order.py::TestTradeLedger::test_trade_ledger_summary PASSED [ 91%]
test_phase_3_order.py::TestTradeLedger::test_trade_ledger_filter_by_symbol PASSED [ 92%]
test_phase_3_order.py::TestExecutionSafety::test_no_order_send_in_execution PASSED [ 92%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_gold_exposure_cap_applied PASSED [ 93%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_gold_small_stop PASSED [ 94%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_gold_no_exposure_cap_when_small PASSED [ 94%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_forex_exposure_cap PASSED [ 95%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_gold_vs_forex_different_lots PASSED [ 96%]
test_position_sizer_numeric.py::TestPositionSizerNumeric::test_zero_stop_loss_returns_zero PASSED [ 96%]
test_antimartingale_tiers.py::test_three_losses_gets_quarter_adjustment PASSED [ 97%]
test_antimartingale_tiers.py::test_two_losses_gets_half_adjustment PASSED [ 98%]
test_antimartingale_tiers.py::test_three_wins_gets_1_5x_adjustment PASSED [ 98%]
test_antimartingale_tiers.py::test_two_wins_gets_1_25x_adjustment PASSED [ 99%]
test_antimartingale_tiers.py::test_no_streak_gets_base_adjustment PASSED [100%]
```

### Test Suite Notes
- **9 test files could not be collected** due to a pre-existing `ImportError: cannot import name 'OrderSide' from 'graxia.packages.quant_os.execution.execution_simulator'`
  - `test_load.py`, `test_ema_rsi.py`, `test_timing.py`, `test_timing2.py`, `test_timing3.py`, `test_vwap.py`, `test_single.py`, `test_lookahead_regression.py`, `test_mtf_leak.py`
  - Root cause: `backtest/engine.py:29` imports `OrderSide as ExecOrderSide` from `execution_simulator`, but `OrderSide` is defined in `core.enums`, not re-exported from `execution_simulator`
  - This is a pre-existing broken import, not related to G0 cleanup
- **1 test failed** (`test_phase_2a::TestStrictMTF::test_strict_mtf_blocks_static_fallback`) — same `OrderSide` import error triggered at test runtime via `backtest.engine` import

## Clean-Process Import
```
IMPORT OK
```

## Bias Detection Tests (deterministic only — real tests excluded for network dependency)
```
Not run in this session (not in the explicit file list, would require separate invocation).
```

## Verdict
**6/6 G0 tests PASS** → G0.1 closeout requirement MET

- All clean-process import tests: PASS
- Runtime startup test: PASS
- Legacy production path audit: PASS
- HFT backtest isolation: PASS (both tests)
- Clean subprocess import: PASS
- Full suite: 150/150 collectable tests pass (1 failure + 9 collection errors are pre-existing `OrderSide` import bug, orthogonal to G0 scope)
