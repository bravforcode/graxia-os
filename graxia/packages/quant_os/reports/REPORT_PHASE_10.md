# Phase 10 — Controlled Expansion

## Objective
Evidence-gated scaling from micro-live to full production configuration.

## Expansion Phases

| Phase | Description | Symbols | Max Positions |
|-------|-------------|---------|---------------|
| 1 | One symbol micro-live | XAUUSD | 1 |
| 2 | Two symbols | XAUUSD, EURUSD | 2 |
| 3 | Three symbols | +GBPUSD | 3 |
| 4 | Multiple strategies | +mean_reversion | 4 |
| 5 | Portfolio allocation | +USDJPY, +momentum | 5 |

## Evidence Gates Per Phase
Each phase requires passing all gates before advancing:
- Phase 1: Micro-live review, campaign, drills, kill switch, reconciliation
- Phase 2: EURUSD data, strategy validation, cross-symbol risk
- Phase 3: Third symbol, portfolio risk
- Phase 4: Second strategy, correlation check
- Phase 5: All strategies, portfolio optimization, final review

## Exit Gate
- [x] All 5 phases defined
- [x] Evidence gates per phase defined
- [x] Risk limits per phase defined
- [x] Expansion tracker working
- [x] Report generation working

## Test Results
```
18 passed, 2 warnings in 0.31s

TestExpansionPlanner::test_create_planner PASSED
TestExpansionPlanner::test_get_current_step PASSED
TestExpansionPlanner::test_get_step_by_phase PASSED
TestExpansionPlanner::test_can_advance_initial PASSED
TestExpansionPlanner::test_cannot_advance_with_unpassed_gates PASSED
TestExpansionPlanner::test_can_advance_after_gates_pass PASSED
TestExpansionPlanner::test_step_to_dict PASSED
TestExpansionPlanner::test_planner_to_dict PASSED
TestExpansionPlanner::test_phase_1_risk_limits PASSED
TestExpansionPlanner::test_phase_5_has_most_symbols PASSED
TestExpansionTracker::test_get_status PASSED
TestExpansionTracker::test_complete_gate PASSED
TestExpansionTracker::test_complete_gate_nonexistent PASSED
TestExpansionTracker::test_start_phase PASSED
TestExpansionTracker::test_complete_phase PASSED
TestExpansionTracker::test_cannot_complete_without_gates PASSED
TestExpansionTracker::test_export_report PASSED
TestExpansionTracker::test_report_summary PASSED
```

## Verdict
**PASS**
