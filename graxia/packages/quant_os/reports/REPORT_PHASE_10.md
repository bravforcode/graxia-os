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
[Fill from test run]

## Verdict
[PASS / CONDITIONAL_PASS / FAIL]
