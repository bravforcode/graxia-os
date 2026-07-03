# Phase 9 — Guarded Micro-Live Review

## Objective
Review whether the system deserves the right to submit a tightly constrained live order.

## Review Evidence

### Evidence Pack
- **Built**: 2026-06-22T13:10:22
- **Backtest results**: MTM strategy (2 trades, 50% win rate, PF 1.87, Sharpe 0.29), MRB/MLB no trades
- **Release gate**: 562/562 tests passed across dual runs, reproducible e2e seal `e9201136...`
- **Drill results**: 11/11 passed (kill switch, MT5 disconnect, stale tick, wide spread, contract change, broker rejection, order timeout, position mismatch, SL/TP verification, restart recovery, telemetry)
- **Canary config**: DEMO mode, XAUUSD only, single position, no auto-resume
- **Micro-live policy**: 1 symbol, 1 position, 1 order/day, 5 bps risk, kill switch enabled, no compounding

### Risk Policy Verification
| Check | Status | Detail |
|-------|--------|--------|
| Micro-live policy valid | PASS | All constraints satisfied |
| Canary config valid | PASS | DEMO mode enforced |
| Risk budgets | **FAIL** | RiskPolicy: 10/50/150/300 bps vs micro-live requirement: 5/20/50/100 bps |
| Kill switch present | PASS | EmergencyKillSwitch active |
| No auto-resume | PASS | auto_resume_after_kill_switch = False |
| Single symbol only | PASS | max_symbols = 1 |
| Single position only | PASS | max_open_positions = 1 |
| No compounding | PASS | no_compounding = True |

**Blocker**: `risk/risk_policy.py` defaults (10/50/150/300 bps) exceed micro-live limits (5/20/50/100 bps). Must be tightened before full approval.

### Review Verdict
- **Report ID**: RPT-20260622131022
- **Candidate**: XAU_LIQSWEEP_LOCKED_001
- **Checklist outcome**: `extend_demo`
- **Archive reasons**: `risk_budgets_exceeded`
- **Final verdict**: `CONDITIONAL_APPROVAL`

## If Approved
- One symbol (XAUUSD)
- One strategy (liquidity_sweep_locked_version)
- Smallest volume (0.01 lot)
- No compounding
- Strict daily/weekly caps (20 bps daily, 50 bps weekly, 100 bps max DD)
- Human session enable
- Persistent kill switch
- No auto-resume
- Explicit stop conditions

## If Not Approved
Archive or return to research.

## Test Results
```
tests/test_phase_9_review.py         5 passed
tests/test_phase_9_integration.py    5 passed
─────────────────────────────────────────────
Total: 10 passed, 0 failed
```

## Blocking Issue
The `risk/risk_policy.py` module uses demo-level risk budgets:
- `risk_per_trade_bps`: 10 (requires <= 5)
- `max_daily_loss_bps`: 50 (requires <= 20)
- `max_weekly_loss_bps`: 150 (requires <= 50)
- `max_total_drawdown_bps`: 300 (requires <= 100)

**Action required**: Tighten `RiskPolicy` defaults to match `MicroLivePolicy` constraints before promoting to micro-live.

## Verdict
**CONDITIONAL_APPROVAL** — System passes all structural and drill checks. One blocker remains: risk policy budgets must be tightened to micro-live levels (5/20/50/100 bps) before live capital deployment.
