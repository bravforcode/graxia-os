# G0A Datetime Audit — REMEDIATION REQUIRED

## Classification: AUDITED / REMEDIATION REQUIRED

## Summary
- Total naive datetime calls: 53
- **Execution-adjacent: 17 — MUST migrate before G3**
- Legacy: 28 — document separately, non-blocking
- Test: 1 — acceptable
- Infrastructure/other: 7 — migrate with execution path
- Timezone-aware (correct): 72+ in newer modules (shadow/, market_data/, tick/, validation/)

## Execution-Adjacent Paths (BLOCKING G3)

These are reachable from canonical tick handling, approval TTL, event gating, broker reconciliation, or evidence sealing:

| File | Lines | Context |
|------|-------|---------|
| execution/order.py | 44, 45, 149, 153, 155 | Order created_at, updated_at, sent_at, filled_at |
| execution/manager.py | 352, 367 | Event occurred_at, order updated_at |
| execution/broker_adapter.py | 190 | Fill filled_at |
| broker/mt5_gateway.py | 80 | Connection timestamp |
| data/quality_gate.py | 24, 131 | Data timestamp, staleness check |
| monitoring/alerts.py | 2 | Alert timestamp |
| monitoring/telegram.py | 1 | Notification timestamp |
| canary/emergency_kill_switch.py | 43 | Kill switch activated_at |
| canary/drills/drill_executor.py | 30, 39 | Drill start/duration |
| canary/drills/drill_definitions.py | 28 | Drill timestamp |
| mt5_connector/shadow_runner.py | 200 | Session ID generation |
| risk/engine.py | 260, 267 | Cooldown check timestamps |

**Migration pattern:**
```python
# Before (naive):
datetime.utcnow()

# After (aware):
datetime.now(datetime.timezone.utc)
```

## Legacy Paths (NON-BLOCKING)

| File | Lines | Context |
|------|-------|---------|
| demo_campaign/campaign.py | 107, 123, 126, 140, 153, 263, 270, 271 | Campaign runner |
| demo_campaign/drills.py | 112, 130, 151, 154, 284 | Drill tests |
| gold_bot/core/engine.py | 43, 60, 163, 295, 346, 402, 545 | Bot engine |
| gold_bot/monitoring/telegram_bot.py | 2 | Telegram |
| gold_bot/ai/validator.py | 106 | AI prompt |
| gold_bot/run_demo.py | 1 | Demo runner |
| gold_bot/strategies/opening_range.py | 1 | Strategy |
| backtest/engine.py | 281, 319, 594 | Backtest |
| run_paper_trading.py | 5 | Paper trading |
| run_backtest.py | 1 | Backtest runner |
| run_ml_train.py | 1 | ML training |
| expansion/tracker.py | 4 | Expansion |
| quarantine_manager.py | 1 | Quarantine |

## Test Paths (NON-BLOCKING)

| File | Lines | Context |
|------|-------|---------|
| gold_bot/tests/test_engine.py | 155 | Test fixture |

## Verdict

**AUDITED / REMEDIATION REQUIRED** — 17 execution-adjacent naive datetime calls must be migrated to `datetime.now(datetime.timezone.utc)` before G3.

Non-execution legacy cleanup is documented separately and does not block G0A/G0B/G1/G2.
