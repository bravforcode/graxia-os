# Hypothesis Pre-Registration #6
## Gold/Silver Spread (GSS) — Ratio Mean-Reversion

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1006 (1005 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

The gold/silver ratio (XAUUSD / XAGUSD) is a structural relative-value metric driven by differing industrial vs monetary demand for the two metals. When the ratio deviates excessively from its rolling mean, the spread is over- or under-priced relative to equilibrium. Mean-reversion occurs because:

1. Central bank and ETF rebalancing flows act as a restoring force.
2. Silver's industrial demand component creates mean-reverting mispricing relative to gold's monetary premium.
3. The 60-day window captures the medium-term equilibrium; extremes beyond 2 standard deviations represent dislocations that revert as flow pressure subsides.

This is a *contrarian* strategy: when the ratio is elevated (gold expensive relative to silver), we short the ratio; when depressed, we go long.

**Why this is a different mechanism from MRM (trial #1005), RYDC (trial #1001), CAM (trial #1003), SP (trial #1004):**

- MRM tests regime classification on real yields
- RYDC tested contemporaneous residual divergence from a DXY + real-yield regression
- CAM tests lagged DXY → XAUUSD underreaction
- SP tests intraday regime-conditional behavior on a single instrument
- **GSS tests cross-asset ratio mean-reversion between XAUUSD and XAGUSD**

This is a *ratio z-score contrarian* trade — structurally different from all prior trials.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Ratio z-score contrarian** | Mean-reversion when ratio deviates >2 std | Flow-driven restoring force |
| B — Ratio momentum | Trend-follow the ratio | Structural drift in relative demand |

**Registered choice: Arm A.** Arm B would need its own pre-registration if Arm A fails.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD OHLC | `data/XAUUSD_D1.csv` | Daily | 5+ years |
| XAGUSD OHLC | `data/XAGUSD_D1.csv` | Daily | 5+ years |

## 4. Feature Construction (exact, no discretion)

```
# Gold/Silver ratio
ratio_t = XAUUSD_close_t / XAGUSD_close_t

# Rolling statistics (data through t-1 only)
ratio_mean_t = mean(ratio, 60d) shifted by 1
ratio_std_t  = std(ratio, 60d, ddof=1) shifted by 1

# Z-score
ratio_z_t = (ratio_t - ratio_mean_t) / ratio_std_t
```

All rolling statistics use data through `t-1` only (no look-ahead).

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `ratio_window` | **60** | Rolling mean/std window for the ratio |
| `entry_z` | **2.0** | Z-score threshold for entry |
| `hold_days` | **10** | Time exit if stop not hit |
| `atr_period` | **14** | ATR window |
| `stop_atr` | **1.5** | Stop-loss in ATR multiples |

**Entry rules:**

| Condition | Signal | Rationale |
|---|---|---|
| `ratio_z > +2.0` | **SHORT** ratio | Gold expensive relative to silver, expect reversion |
| `ratio_z < -2.0` | **LONG** ratio | Gold cheap relative to silver, expect reversion |

Stop-loss / take-profit: set by validation pipeline risk layer (1.5× ATR SL, 2:1 R:R TP).

## 6. Validation Gates

Identical to existing pipeline:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1006** |
| PBO (CSCV) | N/A | single frozen config |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 5 |
| Min. independent trades | ≥ 100 | see §7 |

## 7. Sample Size Check

With `|z| > 2.0`, approximately 5% of trading days trigger an entry. With daily data over 5 years (~1260 trading days), expected entries ≈ 63 per side, total ≈ 126. **Comfortably exceeds the 100-trade minimum.**

If the WFA produces <100 independent OOS trades, the trial fails on sample-size grounds.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down
- [x] Pre-registered parameters frozen: `ratio_window=60, entry_z=2.0, hold_days=10, atr_period=14, stop_atr=1.5`
- [x] All rolling statistics use `t-1` only
- [x] Deflated Sharpe uses cumulative trial count = 1006
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/gold_silver_spread.py` | Self-contained GSS signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1006_gold_silver_spread.md` | This document |

The strategy module exposes:

```python
from strategies.gold_silver_spread import GSSConfig, compute_gss_signals
config = GSSConfig()                             # frozen defaults
result = compute_gss_signals(xau_close, xau_high, xau_low, xag_close, config=config)
# result.signal    : -1 / 0 / +1 single-bar entries
# result.ratio     : XAUUSD / XAGUSD
# result.ratio_z   : z-score of ratio vs 60-day rolling mean
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** Cross-asset ratio strategies are vulnerable to cointegration regime breaks. The 60-day window is intentionally medium-term to capture equilibrium while being short enough to adapt. If the test fails, the honest interpretation is that the XAU/XAG ratio mean-reversion edge does not have a robust daily-frequency edge with public data, not that "we needed a different window."
