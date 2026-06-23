# REPORT_LEGACY_METRIC_INVALIDATION_ENFORCEMENT.md

## G1.0 — Historical Metric Invalidation Enforcement

**Commit:** `5d161759d7326f5c0ffde3f32220c573f2b8df88`
**Date:** 2026-06-23

---

## Programmatic Invalidation Registry

Created `risk/metric_invalidation.py` — a code-accessible, testable registry of all legacy campaign metric classifications.

### MetricValidity Enum

| State | Meaning | Example |
|-------|---------|---------|
| `VALID` | Directly observed, retained evidence | process_restarts, connectivity_events |
| `PARTIALLY_VALID` | Useful for context, not decisions | signal_count, uptime, spread_obs |
| `INVALID_FOR_DECISION` | Cannot be used for trading decisions | gross_pnl, expectancy, risk_per_trade |
| `SIMULATED_ONLY` | Hypothetical, no broker execution | win_rate, risk_reward_ratio |
| `UNDETERMINED` | Not yet classified | Unknown metrics |
| `OUT_OF_SCOPE` | Intentionally excluded | Multi-broker metrics |

### Registry (17 entries)

| Metric | Classification |
|--------|---------------|
| gross_pnl | **INVALID_FOR_DECISION** |
| net_pnl_after_costs | **INVALID_FOR_DECISION** |
| expectancy | **INVALID_FOR_DECISION** |
| profit_factor | **INVALID_FOR_DECISION** |
| win_rate | **SIMULATED_ONLY** |
| risk_per_trade | **INVALID_FOR_DECISION** |
| max_drawdown | **INVALID_FOR_DECISION** |
| sharpe_ratio | **INVALID_FOR_DECISION** |
| position_sizing | **INVALID_FOR_DECISION** |
| stop_loss_distance | **INVALID_FOR_DECISION** |
| take_profit_distance | **INVALID_FOR_DECISION** |
| risk_reward_ratio | **SIMULATED_ONLY** |
| signal_count | **PARTIALLY_VALID** |
| uptime_seconds | **PARTIALLY_VALID** |
| spread_observations | **PARTIALLY_VALID** |
| connectivity_events | **PARTIALLY_VALID** |
| process_restarts | **VALID** |

### API

```python
from risk.metric_invalidation import get_metric_validity, is_metric_usable

# Check classification
validity = get_metric_validity("gross_pnl")  # → MetricValidity.INVALID_FOR_DECISION

# Check if usable for decisions
if not is_metric_usable("gross_pnl"):
    reject("Legacy P&L cannot be used for sizing decisions")
```

## Why Invalidation Is Necessary

### Root Cause
All legacy shadow campaign metrics used `units_per_lot=100000` (forex standard). For XAUUSD, the correct contract size is `trade_contract_size=100` (confirmed by Pepperstone runtime snapshot and MT5 `order_calc_profit()`).

### Sizing Error Magnitude
- Old: 1 lot XAUUSD risk = 10,000 × 100,000 × 0.01 = **$10,000,000** per point
- Correct: 1 lot XAUUSD risk = 1.0 × 100 × 0.01 = **$1.00** per point
- Error: **1,000,000× overstatement** (six orders of magnitude)

### Metrics Affected
Every metric that depends on position sizing, contract value, or P&L is invalid:

- Gross P&L ($976.77) → **INVALID** (should be ~$0.98 with correct sizing)
- Risk per trade → **INVALID** (1000× overstated)
- Expectancy → **INVALID** (cannot compute from wrong P&L)
- Profit factor → **INVALID** (ratio of inflated numbers)
- Sharpe ratio → **INVALID** (requires P&L series)
- Max drawdown → **INVALID** (based on wrong position values)
- Win rate → **SIMULATED_ONLY** (hypothetical TP/SL, no broker fill)

### Metrics Partially Usable
- Signal count (780) → **PARTIALLY_VALID** — operational telemetry
- TP/SL distribution (480 TP, 298 SL) → **PARTIALLY_VALID** — demonstrates geometry logic works
- Spread observations → **PARTIALLY_VALID** — raw market data
- Uptime (6.5h continuous) → **PARTIALLY_VALID** — connectivity test
- Zero restarts → **VALID** — directly observed

## Tests (10/10 Passing)

| Test | Purpose |
|------|---------|
| test_gross_pnl_invalid | P&L → INVALID_FOR_DECISION |
| test_expectancy_invalid | Expectancy → INVALID_FOR_DECISION |
| test_win_rate_simulated_only | Win rate → SIMULATED_ONLY |
| test_signal_count_partially_valid | Signal count → PARTIALLY_VALID |
| test_process_restarts_valid | Restarts → VALID |
| test_pnl_not_usable | is_metric_usable("gross_pnl") == False |
| test_uptime_usable | is_metric_usable("uptime_seconds") == True |
| test_unknown_metric_returns_undetermined | Default → UNDETERMINED |
| test_sharpe_ratio_invalid_for_decision | Sharpe → INVALID_FOR_DECISION |
| test_all_registry_metrics_have_classification | All 17 entries valid |

## Enforcement Policy

```python
def enforce_legacy_metric_policy():
    """Called before any legacy metric is used for decision-making."""
    metrics_to_check = ["gross_pnl", "net_pnl", "expectancy", "win_rate", 
                       "risk_per_trade", "position_sizing"]
    for metric in metrics_to_check:
        if is_metric_usable(metric):
            return False, f"{metric} classified as usable but should be invalid"
    return True, "Legacy invalidation policy enforced"
```

## Verdict: PASS — All historical metrics programmatically invalidated
