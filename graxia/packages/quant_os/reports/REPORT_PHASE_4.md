# Phase 4 — EURUSD Clean Research Foundation

## Objective
Start new market research track without copying XAUUSD settings.

## Files Created
- `markets/eurusd/__init__.py`
- `markets/eurusd/README.md`
- `markets/eurusd/contract_snapshot.py` — EURUSD contract specs
- `markets/eurusd/session_calendar.py` — EUR/USD session times
- `markets/eurusd/event_calendar.py` — Economic event mapping
- `markets/eurusd/hypothesis.py` — Hypothesis template + registry
- `markets/eurusd/anti_contamination.py` — XAUUSD contamination guard
- `markets/eurusd/exit_gate.py` — Phase 4 exit gate

## Separation Rule
- `markets/xauusd/` — XAUUSD strategies
- `markets/eurusd/` — EURUSD strategies
- No shared strategy parameters

## Exit Gate Checklist
- [ ] EURUSD data and contract profile are clean
- [ ] Hypothesis is explicit
- [ ] Baseline is executable under canonical engine
- [ ] No imported XAU optimization exists

## Test Results
[Fill from test run]

## Verdict
[PASS / CONDITIONAL_PASS / FAIL]

## Next Phase
Phase 5 — Research Governance, Walk-Forward, DSR, PBO, and Robustness
