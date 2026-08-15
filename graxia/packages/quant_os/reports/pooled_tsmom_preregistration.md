# Pooled Multi-Asset TSMOM — Pre-Registration

> **Document created BEFORE any pooled test runs.**
> **Universe, parameters, and methodology are FROZEN.**
> **Do not modify after seeing results.**

---

## 1. Research Question

**Does time-series momentum (TSMOM) with lookback=252 produce statistically significant returns when tested pooled across multiple asset classes with cluster-robust inference?**

**Null hypothesis H₀:** Mean pooled return = 0 (no edge after costs)
**Alternative H₁:** Mean pooled return ≠ 0

**Why pooled:** Moskowitz, Ooi & Pedersen (2012) validated TSMOM across 58 instruments. Single-asset test on XAUUSD produced 503 trades over 20 years with NW t-stat=0.111 — underpowered. Pooling across assets increases independent bets and statistical power.

---

## 2. Asset Universe (PRE-REGISTERED, FROZEN)

| # | Symbol | Asset Class | D1 Bars | Start Date | Rationale |
|---|--------|------------|---------|------------|-----------|
| 1 | XAUUSD | Commodity (precious) | 20,300 | 2005-01-01 | Primary asset, gold momentum |
| 2 | XAGUSD | Commodity (precious) | 16,671 | 2005-01-01 | Silver — correlated with gold but different industrial demand |
| 3 | EURUSD | FX (major) | 14,220 | 2005-01-01 | Most liquid FX pair, USD driver |
| 4 | GBPUSD | FX (major) | 14,490 | 2005-01-01 | GBP — different monetary policy cycle |
| 5 | USDJPY | FX (major) | 14,462 | 2005-01-01 | JPY — safe haven, rates-sensitive |
| 6 | NAS100 | Equity index | 23,176 | 2005-01-01 | Tech/growth risk appetite proxy |
| 7 | US30 | Equity index | 33,732 | 2005-01-01 | Industrial/blue-chip, different sector mix |
| 8 | BTCUSD | Crypto | 5,827 | 2012-01-01 | Highest vol, uncorrelated macro driver |

**Total: 8 assets across 4 asset classes.**

### Excluded Assets (with reasons)

| Asset | Reason |
|-------|--------|
| DXY | Only 2,143 bars (2018–2026) — too short for 252-bar warmup + meaningful test |
| ETHUSD | Only 3,980 bars (2015–2026) — too short, high correlation with BTC |
| AUDUSD | High correlation with XAUUSD (AUD is commodity currency) — adds little independence |
| USDCHF | High correlation with EURUSD (CHF tracks EUR) — adds little independence |

### Universe Rules

1. **NO asset may be added or removed after this document is signed.**
2. If an asset has data quality issues, it is EXCLUDED from that test run (not replaced).
3. Results must be reported BOTH with and without BTCUSD (since BTC has shorter history).
4. If excluding an asset drops total trades below 1,000, flag as INSUFFICIENT_SAMPLE.

---

## 3. Parameters (PRE-REGISTERED, FROZEN across ALL assets)

```
lookback = 252          # 12-month TSMOM (Moskowitz et al. 2012)
atr_period = 14         # ATR for SL/TP
atr_sl_mult = 2.0       # Stop loss = 2x ATR
atr_tp_mult = 3.0       # Take profit = 3x ATR (1.5:1 RR)
risk_per_trade_bps = 100  # 1% risk per trade
max_positions = 1       # Per asset (total max = 8 across universe)
```

### Parameter Rules

1. **Same lookback for ALL assets.** No per-asset optimization. If EURUSD works better with lookback=126, that's a different hypothesis — not this one.
2. **Same SL/TP multipliers for ALL assets.** ATR normalizes across asset vol.
3. **No parameter changes after first test run.** If results are poor, the correct action is REJECT, not re-tune.

---

## 4. Inference Method: Cluster-Robust Standard Errors

### Why Not Standard Newey-West

Standard NW corrects for time-series autocorrelation within ONE asset. When pooling across assets, returns on the same date are cross-sectionally correlated (e.g., risk-off day → all assets momentum in same direction). NW ignores this.

### Method: Driscoll-Kraay (or Date-Clustered NW)

**Idea:** Treat each DATE as a cluster. Compute the cross-sectional mean return for each date, then apply NW to the time series of cross-sectional means.

```
For each date t:
    r̄_t = (1/N_t) * Σ_i r_{i,t}    # cross-sectional mean (N_t = assets with trades that day)

Then apply NW to {r̄_t}:
    SE = NW_SE(r̄_1, r̄_2, ..., r̄_T)
    t-stat = mean(r̄) / SE
```

**Why this works:**
- Cross-sectional correlation is absorbed by the daily averaging
- Time-series autocorrelation is handled by NW bandwidth
- Effective degrees of freedom = number of distinct trading dates (~5,000), not total trades (~3,000)

### Fallback: If cross-sectional mean has too many zero days

If >50% of dates have no trades (assets not in position), use **pooled NW with date dummies** instead:
```
Stack all asset returns into one long series
Sort by date (not by asset)
Apply NW to the stacked series
```

This is less precise than Driscoll-Kraay but still better than per-asset NW.

---

## 5. Data Quality Gates (per asset)

Before any asset enters the pool, it MUST pass:

| Check | Threshold | Action if FAIL |
|-------|-----------|----------------|
| Missing bars | < 2% missing in last 5 years | EXCLUDE asset |
| Date continuity | No gaps > 5 business days | Flag, investigate |
| Zero-price bars | 0 bars with close=0 | EXCLUDE if any |
| Spread anomaly | No bars with spread > 10x median | Flag, clip |
| Minimum history | ≥ 3,000 D1 bars from 2005-01-01 | EXCLUDE if less |
| Return sanity | No single-bar return > 20% (daily) | Flag, investigate |

---

## 6. Expected Trade Count

| Asset | Est. trades/year (252-bar lookback, D1) | Est. total (2005-2026 = 21 years) |
|-------|----------------------------------------|-----------------------------------|
| XAUUSD | ~25 | ~525 |
| XAGUSD | ~25 | ~525 |
| EURUSD | ~25 | ~525 |
| GBPUSD | ~25 | ~525 |
| USDJPY | ~25 | ~525 |
| NAS100 | ~25 | ~525 |
| US30 | ~25 | ~525 |
| BTCUSD | ~25 | ~350 (shorter history) |

**Total estimated: ~3,725 trades across 8 assets over 21 years.**
**Effective independent observations: ~5,000 trading dates (cross-sectional means).**

This is ~7x the single-asset sample (503 trades). If edge exists, this should detect it.

---

## 7. Reporting Requirements

### Must Report

1. **Per-asset results:** Sharpe, NW t-stat, trades, win rate, PF, max DD for each of 8 assets
2. **Pooled results:** Cross-sectional mean return, Driscoll-Kraay t-stat, pooled Sharpe
3. **Correlation matrix:** Pairwise correlation of per-asset returns (to verify independence)
4. **With/without BTC:** Results excluding BTCUSD (shorter history concern)
5. **Cost sensitivity:** Results with 0%, 30%, 50% edge haircut

### Decision Criteria

| Outcome | Criteria |
|---------|----------|
| **GO** | Pooled Driscoll-Kraay t-stat > 2.0 AND per-asset Sharpe > 0 in ≥ 5/8 assets |
| **MARGINAL** | Pooled t-stat 1.5–2.0 OR per-asset Sharpe > 0 in only 3–4/8 assets |
| **REJECT** | Pooled t-stat < 1.5 OR per-asset Sharpe > 0 in < 3/8 assets |

---

## 8. Timeline

1. **Data quality check:** Run quality gates on all 8 assets
2. **Engine adaptation:** Extend BacktestEngine to run multi-asset sequentially
3. **Run pooled test:** Execute TSMOM on all 8 assets, collect returns
4. **Compute cluster-robust SE:** Driscoll-Kraay on cross-sectional means
5. **Report and decide:** Apply decision criteria above

---

*Pre-registered: 2026-07-16*
*Author: quant_os research pipeline*
*FROZEN: Do not modify universe, parameters, or methodology after this point*
