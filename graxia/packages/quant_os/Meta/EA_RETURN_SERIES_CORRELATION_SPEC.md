# EA-Return-Series Correlation Spec

**Date:** 2026-07-24
**Status:** DRAFT — needs review before step 6 implementation
**Supersedes:** Price-series correlation (existing `core/correlation.py`)

---

## Motivation

The existing correlation system (`core/correlation.py`) computes pairwise correlation across **price series** (OHLCV data). The EA farm needs a different metric: correlation across **EA return series** (per-EA PnL over time). Two EAs trading the same instrument with the same holding period may look uncorrelated on price but produce nearly identical equity curves — the risk is hidden if we only measure price correlation.

---

## Spec

### Return series definition

For each EA, define its return series as the sequence of per-trade or daily PnL values:

- **Per-trade returns:** `r_i = PnL_i / balance_before_trade_i` for each completed trade `i`.
- **Daily returns:** `r_d = PnL_d / balance_start_of_day_d` for each trading day `d`.

Per-trade is preferred when trade frequency is low (< 10 trades/day). Daily is preferred for high-frequency EAs.

### Trailing window

Use a trailing window of the most recent `N` return observations (default: `N=60` for daily, `N=200` for per-trade). Older observations are dropped. This ensures the correlation reflects recent behavior, not ancient history.

### Correlation metric

Pearson correlation coefficient between the two EA return series, aligned by timestamp (for daily) or by trade sequence index (for per-trade).

### Cap / threshold

- **Same as production:** cap at **0.7** (`HIGH_CORRELATION` from `core/correlation.py:25`).
- `>= 0.7`: HIGH — flag as correlated, block or reduce position.
- `>= 0.9`: VERY HIGH — flag as near-duplicate, block.

This matches the existing threshold in `core/config.py:93` (`max_correlation_threshold = 0.7`).

### When to compute

- **Before adding a new EA to the portfolio:** compute pairwise correlation against all existing EAs.
- **Periodically (daily or weekly):** recompute trailing-window correlation to detect drift.
- **On EA update/version change:** recompute if the EA's strategy logic changed.

---

## Design Decision: Price-Series vs EA-Return-Series

The choice of return series metric matters because:

| Scenario | Price correlation | EA-return correlation |
|----------|-------------------|----------------------|
| Two EAs, same instrument, opposite timeframes | Low (different price windows) | Low (different entry/exit patterns) |
| Two EAs, same instrument, same timeframe, different entry logic | Low-Medium (same price data, different trades) | Low-Medium (different PnL sequences) |
| Two EAs, same instrument, same timeframe, similar entry logic | Medium-High (same price data) | **High** (similar PnL sequences) |
| Two EAs, different instruments, same strategy template | Low (different price data) | **High** (similar PnL patterns) |

The EA-return correlation catches case 4 (same strategy template, different instruments) which price correlation misses entirely.

**Recommendation:** Use EA-return-series correlation as the primary metric for portfolio diversification. Keep price-series correlation as a secondary signal for detecting instrument-level concentration.

---

## Implementation Sketch

```python
# validation/ea_correlation.py (proposed)

def compute_ea_return_correlation(
    ea_a_trades: list[dict],  # [{timestamp, pnl, balance_before}, ...]
    ea_b_trades: list[dict],
    window: int = 200,
    method: str = "per_trade",  # or "daily"
) -> float:
    """Compute Pearson correlation between two EA return series."""
    ...

def check_ea_portfolio_correlation(
    portfolio: dict[str, list[dict]],  # {ea_name: [trades]}
    cap: float = 0.7,
    window: int = 200,
) -> list[tuple[str, str, float]]:
    """Return pairs with correlation >= cap."""
    ...
```

---

## Open Questions

1. **Alignment:** How to align trades from two EAs with different trade frequencies? Options: (a) timestamp-bucket to daily, (b) trade-sequence index alignment, (c) both with configurable preference.
2. **Cold start:** New EA with < `window` trades — use all available trades, or require minimum before computing?
3. **Storage:** Where to persist per-EA return series? Options: (a) JSON files in `validation/fixtures/`, (b) SQLite, (c) in-memory only.
4. **Integration with existing `core/correlation.py`:** Extend existing module or create separate `validation/ea_correlation.py`?

---

## Approval

| Approver | Role | Date | Decision |
|----------|------|------|----------|
| — | Human Reviewer | — | **PENDING** |
