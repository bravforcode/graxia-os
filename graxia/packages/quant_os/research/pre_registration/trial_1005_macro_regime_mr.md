# Hypothesis Pre-Registration #5
## Macro Regime Mean-Reversion (MRM) — Real-Yield Regime-Conditional Trading

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1005 (1004 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

Real (inflation-adjusted) yields are the structural driver of all risk-asset valuations. When DFII10 (10Y TIPS yield) is **stable** (low coefficient of variation over a rolling window), the macro backdrop is quiet and price action mean-reverts within the recent range — classical range-trading works. When DFII10 is **trending** (high CV), macro narratives are shifting, cross-asset hedging flow is active, and the same "mean-reversion" trade gets run over by a regime break.

The candidate edge here is **regime-conditional trade selection**:

```
regime_score_t = std(DFII10, 30d) / |mean(DFII10, 30d)|

IF regime_score < 0.20  →  STABLE   → mean reversion
IF regime_score ≥ 0.20  →  TRENDING → momentum
```

The same deviation threshold (2.0× ATR from the 20-bar rolling mean) flips its direction based on the regime.

**Why this is a different mechanism from RYDC (trial #1001) and CAM (trial #1003), SP (trial #1004):**

- RYDC tested contemporaneous residual divergence from a DXY + real-yield regression
- CAM tests lagged DXY → XAUUSD underreaction
- SP tests intraday regime-conditional behavior on a single instrument
- **MRM tests daily regime classification on the real-yield series itself, then picks trade direction *conditional* on that classification**

This is a *regime classifier + trade direction flip* — a structurally different test. The stopping rule (§3.1) counts this as a new trial.

**Critical scope clarification:** MRM is *not* a "try MR if trending, momentum if ranging" backtest with a tunable regime threshold. The regime threshold (0.20) and the entry threshold (2.0× ATR) are both pre-registered and frozen.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Regime-conditional flip** | Same deviation, opposite direction by regime | Macro regime determines price-action model |
| B — Always mean reversion | Single-mode, never flip | Classical range-trading |
| C — Always momentum | Single-mode, always trend | Trend-following |

**Registered choice: Arm A.** Arms B and C are not pre-registered here; if Arm A fails they would each need their own pre-registration, not a post-hoc pivot.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD OHLC | `data/XAUUSD_D1.csv` | Daily | 5+ years |
| DFII10 (10Y TIPS real yield) | FRED API or `data/rydc/rydc_daily.csv` | Daily | 5+ years |

DFII10 must be the *real* yield (TIPS), not nominal. If the data is unavailable, the trial reports a data-availability failure, not a real-data null.

## 4. Feature Construction (exact, no discretion)

```
# Regime classifier
mu_d  = mean(DFII10, 30d) shifted by 1
sd_d  = std(DFII10, 30d, ddof=1) shifted by 1
regime_score = sd_d / |mu_d|

# Deviation in ATR units
tr_t   = max(high-low, |high-close_{t-1}|, |low-close_{t-1}|)
atr_t  = mean(tr, 14) shifted by 1
mean_t = mean(close, 20) shifted by 1
dev_t  = (close_t - mean_t) / atr_t
```

All rolling statistics use data through `t-1` only (no look-ahead).

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `regime_window` | **30** | DFII10 rolling CV window |
| `regime_threshold` | **0.20** | std/\|mean\| boundary: STABLE below, TRENDING above |
| `mr_threshold_atr` | **2.0** | Entry distance from rolling mean, in ATR units |
| `atr_period` | **14** | ATR window |
| `mean_window` | **20** | Rolling mean of close for entry reference |

**Entry rules:**

| Regime | Deviation | Signal | Rationale |
|---|---|---|---|
| STABLE | `dev < -2.0` | **LONG** | Mean reversion up (price oversold in stable regime) |
| STABLE | `dev > +2.0` | **SHORT** | Mean reversion down (price overbought in stable regime) |
| TRENDING | `dev < -2.0` | **SHORT** | Momentum down (trend continuation) |
| TRENDING | `dev > +2.0` | **LONG** | Momentum up (trend continuation) |

Stop-loss / take-profit: set by validation pipeline risk layer (1.5× ATR SL, 2:1 R:R TP).

## 6. Validation Gates

Identical to existing pipeline:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1005** |
| PBO (CSCV) | N/A | single frozen config |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 5 |
| Min. independent trades | ≥ 100 | see §7 |

## 7. Sample Size Check

With `|dev| > 2.0` (in ATR units), a price needs to move 2× ATR from its 20-bar mean. On daily XAUUSD, ATR(14) ≈ $15–25. A 2× ATR move is ≈ $30–50, which happens roughly 10–15% of trading days. With a hold of 5d and 5 years of pre-2025 data, expected entries ≈ 200–300. **Comfortably exceeds the 100-trade minimum.**

If the WFA produces <100 independent OOS trades, the trial fails on sample-size grounds.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down
- [x] Pre-registered parameters frozen: `regime_window=30, regime_threshold=0.20, mr_threshold_atr=2.0, atr_period=14, mean_window=20`
- [x] All rolling statistics use `t-1` only
- [x] Deflated Sharpe uses cumulative trial count = 1005
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/macro_regime_mr.py` | Self-contained MRM signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1005_macro_regime_mr.md` | This document |
| `research/hypothesis_registry.json` | Registry entry |

The strategy module exposes:

```python
from strategies.macro_regime_mr import MRMConfig, Regime, compute_mrm_signals
config = MRMConfig()                             # frozen defaults
result = compute_mrm_signals(close, highs, lows, dfii10, config=config)
# result.signal        : -1 / 0 / +1 single-bar entries
# result.regime        : Regime.STABLE / TRENDING per bar
# result.regime_score  : std(DFII10, 30d) / |mean(DFII10, 30d)|
# result.deviation_atr : (close - mean_20) / ATR
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** Regime-classifier strategies are notoriously easy to overfit (the regime threshold is a high-degree-of-freedom knob). The 0.20 cutoff was chosen from prior research on DFII10 historical CV distribution; it is **frozen** here. If the test fails, the honest interpretation is that the regime-conditional mechanism does not have a robust daily-frequency edge on XAUUSD with public data, not that "we needed a different threshold." The stopping rule (§3.1) prevents re-running with a different threshold on the same data.
