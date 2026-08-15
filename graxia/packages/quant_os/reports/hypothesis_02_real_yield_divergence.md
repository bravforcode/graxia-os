# Hypothesis Pre-Registration Addendum #2
## Real-Yield Divergence Continuation (RYDC) — XAUUSD

**Status:** DRAFT — not yet locked. Do not touch OOS data until checklist in §8 is complete and signed off.
**Cumulative trial count entering this test:** 1000+ (from Search #1, all rejected) + 1 (this hypothesis) = trial #1001+.
**Supersedes nothing.** This runs alongside the existing paper-trade window (ends ~July 23), not instead of it.

---

## 1. Economic Rationale

Gold carries no yield. Its opportunity cost is the real (inflation-adjusted) risk-free rate. Two structural relationships are well established in macro finance:

- **Real yields ↓ → gold tailwind** (falling opportunity cost of holding a non-yielding asset)
- **DXY ↓ → gold tailwind** (gold is USD-denominated globally)

This relationship is *not* itself an edge — it's public knowledge, priced in contemporaneously by rates and macro desks within the same session.

**The actual candidate edge:** information diffusion lag. Rates markets are dominated by fast, institutional flow. Gold spot/CFD retail flow is slower and more technically/momentum-driven. When gold's realized move diverges meaningfully from what the contemporaneous DXY/real-yield move implies, the hypothesis is that this divergence persists for a few days (continuation) before being arbitraged away — rather than correcting within the same session.

This is a named, falsifiable mechanism — not a scan across indicators.

## 2. Two Competing Arms — Pick ONE Before Testing

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Continuation (underreaction)** | Divergence sign predicts next-N-day return in the **same** direction | Slow retail diffusion of rates information |
| B — Mean-reversion (overreaction) | Divergence predicts the **opposite** direction | Retail overshoot, snaps back to fair value |

**Registered choice: Arm A.** Testing both and keeping whichever wins is exactly the PBO = 0.50 failure mode already documented in Search #1. Arm B is explicitly *not* tested under this pre-registration. If Arm A fails, Arm B would need its own separate pre-registration — not a post-hoc pivot on the same data.

## 3. Data Requirements

| Series | Source (free) | Frequency | Min. history |
|---|---|---|---|
| XAUUSD close | Pepperstone MT5 History Center (primary), cross-check vs Dukascopy | Daily | 5+ years |
| DXY (or UDX/USD) | Dukascopy / HistData.com | Daily | 5+ years |
| 10Y TIPS real yield (DFII10) | FRED API | Daily | 5+ years |
| FOMC/CPI calendar | Existing event_flag infra | Event dates | Same window |

5+ years is required specifically to span both a hiking regime (2022–23) and a cutting regime (2024–26) — otherwise the real-yield relationship is regime-specific and won't generalize, which is a distinct failure mode from what killed Search #1.

## 4. Feature Construction (exact, no discretion)

Rolling OLS, 60 trading-day window, refit daily, **coefficients estimated on data through t−1 only** (no look-ahead):

```
Gold_ret_t = α + β1·DXY_ret_t + β2·ΔDFII10_t + ε_t

Predicted_t   = α̂ + β̂1·DXY_ret_t + β̂2·ΔDFII10_t
Residual_t    = Gold_ret_t − Predicted_t
Residual_z_t  = (Residual_t − mean(Residual, 20d)) / std(Residual, 20d)
```

## 5. Signal & Trade Rule (fixed — cannot be tuned after seeing results)

- **Entry long:** `Residual_z_t > +1.5` AND no FOMC/CPI release within next 48h AND flat
- **Entry short:** `Residual_z_t < −1.5`, same conditions
- **Exit:** 4 trading days fixed hold, OR `|Residual_z| < 0.5` (reversion complete) — whichever comes first
- **Stop-loss:** 1.5 × ATR(14) from entry
- **Sizing:** fixed-fractional, consistent with existing risk framework

The 48h FOMC/CPI exclusion exists so this signal isn't accidentally re-testing event-driven vol rather than the diffusion-lag mechanism it's named for.

## 6. Validation Gates — Identical to Existing Pipeline, No Relaxation

| Gate | Threshold | Note |
|---|---|---|
| Statistical significance | p < 0.05 | two-sided t-test, OOS trade returns only |
| WFA OOS positive | ≥ 70% of folds | same method as Search #1 |
| WFE | ≥ 0.5 | OOS Sharpe / IS Sharpe |
| Deflated Sharpe Ratio | > 0 | **must use cumulative trial count (1000+ from Search #1, plus this one)** — do not reset the counter |
| PBO (CSCV) | < 0.5, target < 0.2 | same combinatorial method |
| Bootstrap Sharpe 95% CI | excludes 0 | block bootstrap, block size ≥ 4 days (holding period) |
| Min. independent trades | ≥ 100 | see §7 — may not be reachable at these parameters |

Go-live criteria unchanged from the June 25 document: **avg_net/trade ≥ $0.40, win rate ≥ 0.55, t-stat ≥ 2.0, forward/OOS data only.**

## 7. Sample Size Check — Do This Before Running Anything

At `|z| > 1.5`, a standard normal residual would flag roughly 13% of days *if independent*. With a 4-day hold and autocorrelated residuals, effective independent signals will be far lower. Rough estimate over 5 years (~1250 trading days): **~40–90 non-overlapping entries** after enforcing hold-period spacing.

That's short of the ≥100 trade target. Two honest options, decide *before* seeing any results:
- **Lower z-threshold to 1.0** for a secondary, separately pre-registered arm (more signals, weaker divergence — expect lower per-trade edge)
- **Add XAGUSD (silver)** as a second, independently pre-registered instrument sharing the same mechanism — not pooled with gold post-hoc, tested and reported separately, combined only if both clear their own gates

If neither gets you to ~100 trades, the honest conclusion is the sample size doesn't support a statistically meaningful daily-frequency test on this instrument alone, and the hypothesis should wait for more history to accumulate rather than being forced through with a weaker gate.

## 8. Pre-Registration Lock Checklist

- [ ] Arm A chosen and written down (not selected after seeing results)
- [ ] IS/OOS split date fixed in advance
- [ ] Parameters frozen: window=60d, z-threshold=1.5, hold=4d, stop=1.5×ATR
- [ ] Deflated Sharpe calculation uses cumulative trial count across the whole research program, not reset to zero
- [ ] Go/no-go criteria match the June 25 document exactly
- [ ] Sample-size decision (§7) made in advance, not adjusted after seeing trade count
- [ ] Document hashed and timestamped at lock, same convention as June 25

---

**Note on expectations:** this hypothesis has a real, named mechanism behind it, which is more than the indicator scan in Search #1 had. That does not make it likely to pass — most well-motivated hypotheses still fail these gates, and PBO/DSR exist precisely to catch the ones that only look good by chance. If it fails, that's the pipeline working, not a reason to loosen it.

---

## Implementation Files

| File | Purpose |
|---|---|
| `strategies/rydc.py` | RYDC strategy module (rolling OLS, signal generator) |
| `strategies/event_filter.py` | FOMC/CPI date management (48h exclusion) |
| `scripts/prepare_rydc_data.py` | Data download and alignment pipeline |
| `scripts/run_rydc_validation.py` | Validation runner with all gates |
| `scripts/download_dxy.py` | DXY data downloader (Yahoo/Stooq) |

## How to Run

```bash
# Step 1: Prepare data
python scripts/prepare_rydc_data.py --start 2018-01-01 --fred-api-key YOUR_KEY

# Step 2: Run validation
python scripts/run_rydc_validation.py --folds 5 --bootstrap 1000 --verbose

# Step 3: Check results
# Output: reports/validation/rydc_validation_YYYYMMDD_HHMMSS.json
```

---

## 9. Validation Results — REJECTED

**Date:** 2026-07-12
**Verdict:** REJECTED — Null result, no edge found
**Trial count after this test:** 1002 (1001 from Search #1 + 1 this hypothesis)

### Gate Results (Corrected — BUG FIX 2026-07-12)

| Gate | Value | Threshold | Status | Note |
|---|---|---|---|---|
| p-value | 0.9680 | < 0.05 | **FAIL** | Clear null result — data essentially random |
| WFA OOS positive | 60.00% | ≥ 70% | **FAIL** | Below threshold |
| WFE | 1.9811 | ≥ 0.5 & < 1.5 | **INSUFFICIENT_DATA** | WFE > 1.5 is suspicious; small-sample noise from folds with 14-22 trades |
| Deflated Sharpe | 0.16% | > 95% | **FAIL** | P(genuine skill) = 0.16% after deflating 1001 trials — effectively zero |
| PBO | N/A | N/A | **INSUFFICIENT_DATA** | Single frozen config — no in-sample selection for CSCV to measure |
| Bootstrap CI lower | -2.3125 | > 0 | **FAIL** | CI includes zero |
| Min trades | 52 | ≥ 100 | **FAIL** | Sample too small |

**Overall: FAIL (0/5 PASS, 2 INSUFFICIENT_DATA)**

> **Note:** Original report (2026-07-12 earlier) showed 3/7 PASS due to 3 calculation bugs:
> 1. DSR formula missing `sr_se` scaling → DSR showed 1.37e-116 instead of 0.0016
> 2. DSR threshold `> 0` passed any non-zero value → should be `> 0.95`
> 3. PBO computed as `1 - WFE` → not real CSCV PBO; should be N/A for single config
>
> After fixing: DSR=0.16% (FAIL), WFE=INSUFFICIENT_DATA, PBO=INSUFFICIENT_DATA.
> True pass count = 0/5, not 3/7. This is an even clearer null result.

### Key Metrics (OOS)

| Metric | Value |
|---|---|
| Total trades | 52 |
| Win rate | 51.92% |
| Profit factor | 1.01 |
| Sharpe ratio | 0.044 |
| Max drawdown | 22.91% |
| t-statistic | 0.040 |
| p-value | 0.9680 |
| DSR | 0.16% (P(genuine skill) after 1001 trials) |

### Analysis

This is a **null result**, not an underpowered test:

1. **p = 0.9680** — Data is essentially random. If there were a real edge, point estimates would show direction even with small samples.

2. **Win rate = 51.92%** — Almost exactly 50%, consistent with no edge.

3. **Profit factor = 1.01** — No meaningful edge after costs.

4. **DSR = 0.16%** — After accounting for 1001 cumulative trials, there is only a 0.16% probability this represents genuine skill. This is the correct DSR value (previously reported as 1.37e-116 due to formula bug).

5. **WFE = 1.9811 (insufficient)** — OOS Sharpe appears higher than IS Sharpe, which is suspicious and likely due to unstable Sharpe estimates from small fold sizes (14-22 trades each).

6. **PBO = N/A** — Cannot compute for a single frozen configuration. CSCV PBO applies to Search #1's 1000+-combo scan, not to a pre-registered single hypothesis.

### Why This Failed

The hypothesis assumed an "information diffusion lag" between rates markets and gold spot. The data shows no such lag exists — gold's response to DXY/real-yield moves is contemporaneous, not delayed by days. This is consistent with efficient market pricing where macro desks hedge gold exposure in real-time.

### Implications for Next Steps

- **Do NOT pivot to Arm B** without separate pre-registration
- **Do NOT assume more data will help** — p=0.968 is a null result, not underpowered
- **Trial count = 1002** — must carry forward for all future hypothesis tests
- **Next hypothesis** must have a different, named mechanism and go through the same gates
