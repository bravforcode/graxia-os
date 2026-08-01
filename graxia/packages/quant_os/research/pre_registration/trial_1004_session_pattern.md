# Hypothesis Pre-Registration #4
## Session Pattern (SP) — Volatility Clustering by FX Session

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1004 (1003 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

FX markets are not uniform across the 24-hour day. Liquidity, the *type* of participants, and average range differ systematically by trading session:

- **Asian session (00:00–07:00 UTC):** low volatility, range-bound; retail flow dominates; mean reversion is the well-documented dominant behavior
- **London session (07:00–12:00 UTC):** trending breakouts; institutional flow; momentum dominates, especially into the London/NY overlap
- **New York session (12:00–21:00 UTC):** high volatility; momentum at the overlap, reversal into the close
- **Late NY (21:00–24:00 UTC):** thin book; price action is noise — no-trade zone

The candidate edge here is **volatility-regime-conditional behavior**: the same price-action pattern (e.g. price deviates from a 20-bar mean by 0.5× ATR) is profitable in one session regime and unprofitable in another. Pre-registered:

- **Low-vol session (Asian):** mean reversion. Enter when price deviates by `threshold` (0.5× ATR) from the rolling mean, expect reversion.
- **High-vol session (London / NY):** momentum. Enter on directional break of the same threshold, expect continuation for `session_window` bars.

**Why this is a different mechanism from RYDC (trial #1001, rejected) and CAM (trial #1003):** RYDC tested cross-asset lead-lag on contemporaneous residuals. CAM tests lagged DXY → XAUUSD underreaction. SP tests *intraday regime-conditional behavior* on a single instrument — same price pattern, different trade direction by session. The three hypotheses are independent, the stopping rule counts each as one trial.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Regime-conditional** | Asian: mean reversion; London/NY: momentum | Liquidity type drives profitable price-action model |
| B — Pure mean reversion always | Same direction regardless of session | Single-mode assumption (the strong null) |

**Registered choice: Arm A.** The hypothesis is that *switching direction* by session is the edge; if it isn't, Arm A fails on the same gates as the others. Arm B is not pre-registered here; if it later becomes interesting, it gets its own registration.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD OHLC | `data/XAUUSD_H1.csv` (or M15) | Intraday | 3+ years |
| UTC timestamp | derived from file index | Per-bar | Same window |

The validation runner must use intraday data (not D1) because the session classification is hour-of-day, which collapses to one value on daily bars.

## 4. Feature Construction (exact, no discretion)

```
session_t       = classify(timestamp.hour, UTC):
                    00–07 → ASIAN
                    07–12 → LONDON
                    12–21 → NEW_YORK
                    21–24 → LATE_NY (no-trade zone)

tr_t            = max(high-low, |high-close_{t-1}|, |low-close_{t-1}|)
atr_t           = mean(tr, period=14) shifted by 1

mean_t          = mean(close, window=20) shifted by 1
dev_t           = (close_t - mean_t) / atr_t        # in ATR units
```

All rolling statistics use data through `t-1` only.

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `session_window` | **20** | Rolling window for session-relative mean |
| `threshold_atr` | **0.5** | Entry distance from rolling mean, in ATR units |
| `atr_period` | **14** | ATR window |

**Entry rules:**

| Condition | Signal | Rationale |
|---|---|---|
| `session == ASIAN` AND `dev < -0.5` | **LONG** (mean reversion up) | Price oversold in low-vol session |
| `session == ASIAN` AND `dev > +0.5` | **SHORT** (mean reversion down) | Price overbought in low-vol session |
| `session == LONDON` AND `dev < -0.5` | **SHORT** (momentum down) | Vol expansion continues the move |
| `session == LONDON` AND `dev > +0.5` | **LONG** (momentum up) | Vol expansion continues the move |
| `session == NY` AND `dev < -0.5` | **SHORT** (momentum down) | Same as London |
| `session == NY` AND `dev > +0.5` | **LONG** (momentum up) | Same as London |
| `session == LATE_NY` | **no signal** | Thin book, no-trade zone |

Stop-loss / take-profit: set by the validation pipeline's risk layer (1.5× ATR SL, 2:1 R:R TP).

**Note on hold period:** the entry signal is single-bar. Mean reversion in Asian session typically exits at the mean (caller-side logic). Momentum entries hold for `session_window` bars. Both are pre-registered as caller-side conventions, not strategy-side parameters.

## 6. Validation Gates

Identical to existing pipeline:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1004** |
| PBO (CSCV) | N/A | single frozen config |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 4 |
| Min. independent trades | ≥ 100 | see §7 |

## 7. Sample Size Check

Intraday bars on H1: ~24 bars/day. Asian + London + NY active windows ≈ 21 hours/day. With `|dev| > 0.5` threshold on a 20-bar rolling mean (i.e. 20h rolling), the entry rate is roughly 25–35% of bars. Per trading day: ~6 entries. Over 3 years: ≈ 4500 entries. **This comfortably exceeds the 100-trade minimum**, with material statistical power.

If the WFA produces <100 independent OOS trades, the trial fails on sample-size grounds.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down
- [x] Pre-registered parameters frozen: `session_window=20, threshold_atr=0.5, atr_period=14`
- [x] Session classification rules locked (UTC hour ranges)
- [x] All rolling statistics use `t-1` only
- [x] Deflated Sharpe uses cumulative trial count = 1004
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/session_pattern.py` | Self-contained SP signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1004_session_pattern.md` | This document |
| `research/hypothesis_registry.json` | Registry entry |

The strategy module exposes:

```python
from strategies.session_pattern import SPConfig, Session, compute_sp_signals
config = SPConfig()                              # frozen defaults
result = compute_sp_signals(close, highs, lows, idx, config=config)
# result.signal        : -1 / 0 / +1 single-bar entries
# result.session       : Session.ASIAN / LONDON / NEW_YORK / LATE_NY per bar
# result.atr           : ATR(14) per bar
# result.deviation_atr : (close - mean_20) / ATR
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** SP is a *behavioral* hypothesis (participant type changes profitable model), which is qualitatively different from RYDC (cross-asset lead-lag) and CAM (lagged DXY → XAUUSD). Even if all three fail, they fail for different reasons, which is informative. The stopping rule (§3.1) prevents us from running 20 variants of "session-conditional X" — this is the one and only test of the session-conditional mechanism.
