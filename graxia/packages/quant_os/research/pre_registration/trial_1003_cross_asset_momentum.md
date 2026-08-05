# Hypothesis Pre-Registration #3
## Cross-Asset Momentum (CAM) — DXY → XAUUSD Lead-Lag

**Status:** LOCKED — 2026-07-13
**Cumulative trial number:** 1003 (1002 from prior work + 1 this hypothesis)
**Supersedes nothing.** Runs alongside existing pipelines. Sacred holdout remains physically separate.

---

## 1. Economic Rationale

Gold is priced in USD globally; the dollar is the single largest macro driver of XAUUSD spot. The *contemporaneous* sign of the DXY → XAUUSD relationship is well known and already priced in within the same session by institutional interbank flow.

The candidate edge is a different, more specific claim about **diffusion lag**:

> When DXY drops (rises), XAUUSD tends to rise (fall) with a 1–5 day lag because retail and CTA flow on XAUUSD is slower to reprice than interbank flow on DXY. The z-score extreme in DXY therefore predicts the *follow-through direction* in XAUUSD over the next few days.

This is NOT the "DXY moves → XAUUSD moves the same day" claim (already public, zero alpha). It is specifically a *multi-day lead-lag* underreaction mechanism.

**Why this is a different mechanism from RYDC (trial #1001, rejected):** RYDC tested *contemporaneous* residual divergence from a DXY + real-yield regression, and the data showed no edge. CAM tests a *lagged* response to a *pure* DXY shock (no regression, no residual — just the rolling z-score of DXY returns). The two hypotheses are independent and the stopping rule (§3.1) counts this as a fresh trial.

## 2. Pre-Registered Arm Choice

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Cross-asset momentum** | DXY z < -1.0 → LONG XAUUSD for 5d; DXY z > +1.0 → SHORT XAUUSD for 5d | Slow retail diffusion of DXY information into gold |
| B — Cross-asset mean-reversion | Opposite direction | Retail overreaction snap-back |

**Registered choice: Arm A.** Arm B is not tested under this pre-registration. If Arm A fails, Arm B would need a separate pre-registration, not a post-hoc pivot on the same data.

## 3. Data Requirements

| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD close | `data/XAUUSD_D1.csv` | Daily | 5+ years |
| DXY close | `data/DXY_D1.csv` | Daily | 5+ years |

The two series must be aligned on common trading days; no forward-fill (would leak).

## 4. Feature Construction (exact, no discretion)

```
dxy_ret_t    = log(DXY_t / DXY_{t-1})
dxy_mu_w     = mean(dxy_ret, window) shifted by 1
dxy_sd_w     = std(dxy_ret, window, ddof=1) shifted by 1
dxy_z_t      = (dxy_ret_t - dxy_mu_w) / dxy_sd_w

xau_ret_t    = log(XAU_t / XAU_{t-1})
corr_t       = rolling_corr(dxy_ret, xau_ret, window) shifted by 1   # filter
```

All rolling statistics use data through `t-1` only (no look-ahead).

## 5. Signal & Trade Rule (FROZEN — cannot be tuned after seeing results)

**Pre-registered parameters (frozen):**

| Parameter | Value | Meaning |
|---|---|---|
| `window` | **60** | Rolling z-score window, trading days |
| `z_threshold` | **1.0** | Entry when `|dxy_z| > 1.0` |
| `hold_days` | **5** | Fixed hold period |
| `corr_filter` | **-0.1** | Only trade when rolling corr(DXY, XAU) < -0.1 |

**Entry rules:**

- **LONG XAUUSD** when `dxy_z_t < -1.0` AND `corr_t < -0.1` AND flat
- **SHORT XAUUSD** when `dxy_z_t > +1.0` AND `corr_t < -0.1` AND flat
- **Hold** for exactly 5 trading days (caller / backtester enforces)
- **Stop-loss / take-profit:** set by the validation pipeline's risk layer (1.5× ATR SL, 2:1 R:R TP — not part of this pre-registration)

**Why the correlation filter:** when DXY and XAU have *just happened* to be positively correlated, the historical lead-lag is unreliable; we only trade when the lead-lag is *currently* negative, which is exactly the regime under which the candidate edge is most plausible.

## 6. Validation Gates

Identical to existing pipeline (`scripts/run_rydc_validation.py` patterns) — no relaxation:

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test on OOS trade returns only |
| WFA OOS positive | ≥ 70% of folds | standard walk-forward |
| WFE | ≥ 0.5 & < 1.5 | OOS / IS Sharpe ratio |
| Deflated Sharpe Ratio | > 0.95 | uses **cumulative trial count = 1003** for DSR |
| PBO (CSCV) | N/A for single frozen config | mark honestly as N/A |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size = 5 (hold period) |
| Min. independent trades | ≥ 100 | see §7 — may be tight |

## 7. Sample Size Check

With `|dxy_z| > 1.0` and a 60-day window, ~16% of days produce a signal. With a 5-day hold, effective independent entries per year ≈ 50 (5-day-hold) × 0.16 = ~8/year. Over 5 years of pre-2025 research data, ≈ 40 entries. **This is short of the 100-trade target.**

**Decided before seeing results:** lower the z_threshold to expand the entry set is NOT done here (would change the pre-registered parameter, which is forbidden). If the data does not produce ~100 trades, the trial reports a sample-size failure and the hypothesis is rejected on those grounds, not on the edge itself.

## 8. Pre-Registration Lock Checklist

- [x] Arm A chosen and written down (not selected after seeing results)
- [x] Pre-registered parameters frozen: `window=60, z_threshold=1.0, hold_days=5, corr_filter=-0.1`
- [x] All rolling statistics use `t-1` only (no look-ahead)
- [x] Deflated Sharpe calculation uses cumulative trial count = 1003
- [x] Document committed before any backtest run
- [x] Sacred holdout (`data/sacred_holdout/holdout.csv`) NOT opened

## 9. Implementation

| File | Purpose |
|---|---|
| `strategies/cross_asset_momentum.py` | Self-contained CAM signal (no relative imports from `..core` or `..backtest`) |
| `research/pre_registration/trial_1003_cross_asset_momentum.md` | This document |
| `research/hypothesis_registry.json` | Registry entry |

The strategy module exposes:

```python
from strategies.cross_asset_momentum import CAMConfig, compute_cam_signals
config = CAMConfig()                            # frozen defaults
result = compute_cam_signals(xau_close, dxy_close, config=config)
# result.signal        : -1 / 0 / +1 with multi-day holds
# result.dxy_z         : rolling z-score of DXY returns
# result.correlation   : rolling 60d correlation
```

## 10. How to Run

A future Phase 4.5 / 5 script will wire this into the fixed validation pipeline. The pattern matches `scripts/run_rydc_validation.py` exactly.

---

**Note on expectations:** RYDC (trial #1001) returned p=0.968 — a strong null. CAM uses a fundamentally different mechanism (pure lagged z-score, no regression residual), but that does not make it likely to pass. Most well-motivated hypotheses still fail these gates. If CAM fails, that is the pipeline working, not a reason to relax.
