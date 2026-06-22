# Phase 7 — MT5 Demo Canary Execution

## Objective
Validate broker behavior, not profitability. Demo account only.

## Preconditions
- Phase G0 through Phase 6 passed
- One broker profile only
- Demo account only
- One symbol only (XAUUSD)
- One strategy only
- One risk policy version only

## Files Created
- `canary/__init__.py`
- `canary/config.py` — Canary configuration with validation
- `canary/broker_validator.py` — Broker behavior validation
- `canary/order_lifecycle.py` — Order state machine (16 states), post-fill verifier

## Order Lifecycle
```
SIGNAL_CREATED → RISK_ACCEPTED → ORDER_INTENT_CREATED → ORDER_CHECKED →
ORDER_SUBMITTED → BROKER_ACKNOWLEDGED → FILLED → PROTECTIVE_STOPS_VERIFIED →
POSITION_RECONCILED → CLOSED → DEAL_RECONCILED → AUDITED
```

**Terminal states:** AUDITED, CRITICAL_INCIDENT, REJECTED, EXPIRED

**Branch paths from ORDER_SUBMITTED:**
- REJECTED (broker rejects order)
- EXPIRED (order expires)

**Branch paths from BROKER_ACKNOWLEDGED:**
- PARTIALLY_FILLED → PROTECTIVE_STOPS_VERIFIED → ...
- REJECTED
- EXPIRED

**CRITICAL_INCIDENT** reachable from every non-terminal state.

## Post-Fill Verification
| Check | Method | Description |
|-------|--------|-------------|
| Fill price | `verify_fill_price(expected, actual, tolerance=0.01)` | Fill matches expected within tolerance |
| SL/TP exists | `verify_sl_tp_exists(broker_sl, broker_tp, expected_sl, expected_tp)` | Protective levels set on broker |
| Position state | `verify_position_state(has_position, expected_dir, actual_dir)` | Position matches intent |

## Broker Validation Checks
| Check | Description |
|-------|-------------|
| `validate_account_mode` | Ensures demo account only |
| `validate_symbol` | Symbol allowed and contract specs verified |
| `validate_stop_loss` | SL distance respects minimum distance |
| `validate_position_limits` | Open positions within limit |
| `validate_daily_orders` | Daily order count within limit |

## Exit Gate
- [ ] No unexplained broker action
- [ ] No duplicate submission
- [ ] No unprotected position
- [ ] Reconciliation accuracy complete
- [ ] Observed costs recorded
- [ ] No unresolved critical incident

## Test Results
[Fill from test run]

## Verdict
[CONDITIONAL_PASS]
