# Hypothesis Pre-Registration #8
## Cross-Asset Volatility Rank (CVR) — Relative Vol Value Signal

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1008 (1007 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

Volatility itself is a tradeable asset class. When an asset's realized volatility is at an extreme relative to its own history, there is a structural supply/demand imbalance in options market-making:

1. When vol is cheap (20th percentile), market makers under-hedge, creating positive convexity for long vol positions.
2. When vol is expensive (80th percentile), over-hedging by dealers creates negative convexity for long vol positions.
3. The vol mean-reversion trade (selling expensive vol, buying cheap vol) earns the vol risk premium over a 5-day horizon.

This is a *relative value* strategy: go long when vol is cheap (expect realized vol to increase) and short when vol is expensive (expect mean-reversion down).

**Why this is a different mechanism from BVC (trial #1007), MRM (trial #1005), GSS (trial #1006):**

- BVC tests vol-continuation on BTCUSD
- MRM tests regime classification on real yields
- GSS tests cross-asset ratio mean-reversion between XAU and XAG
- **CVR tests vol mean-reversion on a single asset's own history**

This is a pure vol-percentile signal — structurally different from all prior trials.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Vol mean-reversion** | Cheap vol -> long, expensive vol -> short | Market-maker hedging imbalance |
| B — Vol continuation | Cheap vol -> short, expensive vol -> long | Structural vol regime shift |

**Registered choice: Arm A.** Arm B would need its own pre-registration if Arm A fails.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| Asset OHLC | `data/{ASSET}_D1.csv` | Daily | 5+ years |

Must span 2+ volatility regimes (low-vol and high-vol periods).

## 4. Feature Construction (exact, no discretion)

```
# Log returns
log_ret_t = ln(close_t / close_{t-1})

# Realized vol (data through t-1 only)
rv_t = std(log_ret, 20d, ddof=1) * sqrt(252) shifted by 1

# Percentile rank within rolling window
vol_pct_t = rank(rv, 60d) / 60 * 100
```

All rolling statistics use data through `t-1` only (no look-ahead).

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `vol_window` | **20** | Realized vol lookback |
| `rank_window` | **60** | Percentile rank lookback |
| `entry_low` | **20** | Buy vol below this percentile |
| `entry_high` | **80** | Sell vol above this percentile |
| `hold_days` | **5** | Time exit |
| `atr_period` | **14** | ATR window |
| `stop_atr` | **2.0** | Stop-loss in ATR multiples |

**Entry rules:**

| Condition | Signal | Rationale |
|---|---|---|
| `vol_percentile < 20` | **LONG** | Cheap vol, buy (expect increase) |
| `vol_percentile > 80` | **SHORT** | Expensive vol, sell (expect decrease) |

Stop-loss / take-profit: set by validation pipeline risk layer (2.0× ATR SL, 2:1 R:R TP).

## 6. Validation Gates

Identical to existing pipeline:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1008** |
| PBO (CSCV) | N/A | single frozen config |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 5 |
| Min. independent trades | ≥ 100 | see §7 |

## 7. Sample Size Check

Vol percentiles below 20 or above 80 occur roughly 20% of trading days (combined). With 5 years of daily data (~1260 trading days), expected entries ≈ 252. **Comfortably exceeds the 100-trade minimum.**

If the WFA produces <100 independent OOS trades, the trial fails on sample-size grounds.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down
- [x] Pre-registered parameters frozen: `vol_window=20, rank_window=60, entry_low=20, entry_high=80, hold_days=5, atr_period=14, stop_atr=2.0`
- [x] All rolling statistics use `t-1` only
- [x] Deflated Sharpe uses cumulative trial count = 1008
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/cross_asset_vol_rank.py` | Self-contained CVR signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1008_cross_asset_vol_rank.md` | This document |

The strategy module exposes:

```python
from strategies.cross_asset_vol_rank import CVRConfig, compute_cvr_signals
config = CVRConfig()                             # frozen defaults
result = compute_cvr_signals(close, highs, lows, config=config)
# result.signal          : -1 / 0 / +1 single-bar entries
# result.vol_percentile  : percentile rank of current vol (0-100)
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** Vol mean-reversion is one of the oldest quantitative signals. The challenge is that vol regimes can persist for months, making the 20/80 percentile thresholds too aggressive. If the test fails, the honest interpretation is that vol percentile mean-reversion does not have a robust edge at daily frequency with the frozen parameters, not that "we needed different percentiles."
