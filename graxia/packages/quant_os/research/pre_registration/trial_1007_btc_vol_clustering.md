# Hypothesis Pre-Registration #7
## BTC Volatility Clustering (BVC) — Vol-Continuation Signal

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1007 (1006 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

Cryptocurrency volatility clusters differently than FX. In FX, vol spikes are typically mean-reverting (a shock subsides). In crypto, particularly BTCUSD, vol spikes tend to *persist* for 2-5 days because:

1. Leverage liquidation cascades create self-reinforcing vol.
2. Miner/whale rebalancing flows are multi-day, not single-bar.
3. 24/7 trading means the vol cycle doesn't pause for market close, allowing momentum to compound.

When 20-day realized vol spikes above 1.5x its own rolling mean, the hypothesis is that the next day tends to continue in the same direction as the vol expansion. This is a *vol-continuation* trade: long in the direction of the vol expansion (upward move + vol spike = long; downward move + vol spike = short).

**Why this is a different mechanism from MRM (trial #1005) and GSS (trial #1006):**

- MRM tests regime classification on real yields
- GSS tests cross-asset ratio mean-reversion between XAU and XAG
- **BVC tests vol-continuation on a single crypto asset (BTCUSD)**

This is a pure vol-regime signal on BTCUSD itself — structurally different from all prior trials.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Vol-continuation** | Direction persists during vol spike | Liquidation cascades + miner flow |
| B — Vol-reversion | Direction reverses during vol spike | Overreaction + mean-reversion |

**Registered choice: Arm A.** Arm B would need its own pre-registration if Arm A fails.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| BTCUSD OHLC | `data/BTCUSD_D1.csv` | Daily | 5+ years |

## 4. Feature Construction (exact, no discretion)

```
# Log returns
log_ret_t = ln(close_t / close_{t-1})

# Realized vol (data through t-1 only)
rv_t = std(log_ret, 20d, ddof=1) * sqrt(252) shifted by 1

# Rolling mean of realized vol
rv_mean_t = mean(rv, 60d) shifted by 1

# Vol ratio
vol_ratio_t = rv_t / rv_mean_t

# Direction: sign of close-to-close return over vol_window
direction_t = sign(close_t / close_{t-20} - 1) shifted by 1
```

All rolling statistics use data through `t-1` only (no look-ahead).

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `vol_window` | **20** | Realized vol lookback |
| `vol_threshold` | **1.5** | Vol spike threshold (realized > 1.5 × mean) |
| `hold_days` | **3** | Time exit if stop not hit |
| `atr_period` | **14** | ATR window |
| `stop_atr` | **2.0** | Stop-loss in ATR multiples |

**Entry rules:**

| Condition | Signal | Rationale |
|---|---|---|
| `vol_ratio > 1.5` AND `direction > 0` | **LONG** | Vol up + rising price = continuation |
| `vol_ratio > 1.5` AND `direction < 0` | **SHORT** | Vol up + falling price = continuation |

Stop-loss / take-profit: set by validation pipeline risk layer (2.0× ATR SL, 2:1 R:R TP).

## 6. Validation Gates

Identical to existing pipeline:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1007** |
| PBO (CSCV) | N/A | single frozen config |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 5 |
| Min. independent trades | ≥ 100 | see §7 |

## 7. Sample Size Check

Vol spikes (vol_ratio > 1.5) occur roughly 10-15% of trading days. With 5 years of daily BTCUSD data (~1260 trading days), expected entries ≈ 126-189 per direction. **Exceeds the 100-trade minimum.**

If the WFA produces <100 independent OOS trades, the trial fails on sample-size grounds.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down
- [x] Pre-registered parameters frozen: `vol_window=20, vol_threshold=1.5, hold_days=3, atr_period=14, stop_atr=2.0`
- [x] All rolling statistics use `t-1` only
- [x] Deflated Sharpe uses cumulative trial count = 1007
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/btc_vol_clustering.py` | Self-contained BVC signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1007_btc_vol_clustering.md` | This document |

The strategy module exposes:

```python
from strategies.btc_vol_clustering import BVCConfig, compute_bvc_signals
config = BVCConfig()                             # frozen defaults
result = compute_bvc_signals(close, highs, lows, config=config)
# result.signal    : -1 / 0 / +1 single-bar entries
# result.vol_ratio : realized_vol / rolling_mean_vol
# result.vol_rank  : percentile rank of vol_ratio
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** Vol clustering in crypto is well-documented but the *directional* component (long vs short during vol spikes) is less certain. The hypothesis is that liquidation cascades create a directional bias during vol expansion. If the test fails, the honest interpretation is that vol-continuation does not have a robust directional edge on BTCUSD daily data, not that "we needed a different threshold."
