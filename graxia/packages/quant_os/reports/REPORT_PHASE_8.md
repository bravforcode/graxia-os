# Phase 8 — Demo Campaign and Incident Drills

## Objective
Observe behavior through real operating conditions over a predeclared campaign.

## Files Created
- `demo_campaign/__init__.py`
- `demo_campaign/campaign.py` — Multi-day demo campaign runner
- `demo_campaign/drills.py` — 11 mandatory incident drills

## Incident Drills
1. Kill switch activation
2. MT5 disconnection
3. Stale tick detection
4. Wide spread detection
5. Contract metadata change
6. Broker rejection
7. Order timeout
8. Position mismatch
9. Missing SL/TP verification
10. Restart recovery
11. Telemetry resilience

## Campaign Configuration
- Symbol: XAUUSD
- Duration: 5 days
- Session: 390 min/day (6.5h)
- Interval: 30s between signals
- Max spread: 0.20

## Exit Gate
- [ ] Continuous stable campaign completed
- [ ] All signals auditable
- [ ] Kill switch tested and working
- [ ] MT5 disconnection handled gracefully
- [ ] No unresolved incidents
- [ ] Daily reports generated

## Test Results
[Fill from test run]

## Verdict
[PASS / CONDITIONAL_PASS / FAIL]
