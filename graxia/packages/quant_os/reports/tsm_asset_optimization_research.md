# TSM Asset Optimization Research

**Date:** 2026-07-05
**Author:** Research Agent (RUFLOW)
**Status:** DRAFT — requires backtest validation before implementation

---

## Executive Summary

The current 4-asset TSM portfolio (NAS100, XAUUSD, OIL, USDJPY) achieves Sharpe 0.535 (equal-weight) or 0.729 (optimal-weight) after realistic costs. Research across academic literature (Moskowitz, Ooi, Pedersen 2012; Baz et al. 2015 EMAC; "Trends Everywhere" 2019) and current CTA industry data suggests significant alpha can be unlocked by:

1. **Reintroducing BTCUSD** (highest individual Sharpe: ~1.0+ historically, but extreme drawdowns)
2. **Adding SPX500/US500** (low correlation to NAS100 despite same asset class — different sector composition)
3. **Adding NATGAS** (low correlation to all current assets, strong trending behavior)
4. **Consider USDCHF as a hedge** (strong negative correlation to XAUUSD)

**Optimal portfolio size: 6-8 assets** (academic consensus: diversification benefits plateau around 8-12 uncorrelated assets).

---

## 1. Current 4-Asset Performance Analysis

### Per-Asset Individual Sharpe (Ensemble TSM, Typical+Swap)

| Asset | Sharpe | Ann Return | Max DD | DSR Sig? | Cost Drag (bps/yr) | Verdict |
|-------|--------|------------|--------|----------|---------------------|---------|
| NAS100 | 0.598 | 16.34% | -37.84% | YES | ~30 | ALPHA |
| XAUUSD | 0.374 | 8.16% | -47.52% | YES | ~180 | ALPHA |
| OIL | 0.285 | 27.98% | -89.62% | YES | ~200 | ALPHA (high DD) |
| USDJPY | 0.204 | 2.58% | -37.03% | YES | ~40 | ALPHA (weak) |

### Correlation Matrix (4-Asset)

|        | NAS100 | XAUUSD | OIL   | USDJPY |
|--------|--------|--------|-------|--------|
| NAS100 | 1.000  | 0.080  | 0.095 | 0.137  |
| XAUUSD | 0.080  | 1.000  | 0.018 | -0.414 |
| OIL    | 0.095  | 0.018  | 1.000 | 0.051  |
| USDJPY | 0.137  | -0.414 | 0.051 | 1.000  |

**Key insights:**
- Average pairwise correlation: **-0.006** (excellent diversification)
- Effective independent bets: **4.07** out of 4 (near-perfect)
- XAUUSD-USDJPY correlation of **-0.41** provides natural hedge
- All other pairs nearly uncorrelated

### Portfolio Comparison

| Portfolio | Sharpe | Ann Ret | Max DD | Assets | DSR Sig? | PBO |
|-----------|--------|---------|--------|--------|----------|-----|
| Full Ensemble (8) | 1.062 | ~12% | -23% | 8 | YES | YES |
| 4-Asset Optimal Weight | 0.729 | 11.71% | -19.12% | 4 | YES | YES |
| 4-Asset Equal Weight | 0.535 | 13.93% | -23.48% | 4 | YES | YES |
| Ex-Crypto (9 assets) | 0.373 | 5.56% | -23.29% | 9 | YES | YES |
| Academic TSM baseline | ~0.4 | ~8% | -20% | 58 | - | - |

**Critical finding:** The full 8-asset ensemble (including crypto) achieves Sharpe 1.062, nearly double the 4-asset portfolio. However, this includes BTC/ETH which have extreme drawdowns and high swap costs.

---

## 2. Asset Class Momentum Research

### Academic Evidence (Moskowitz, Ooi, Pedersen 2012)

Across 58 futures contracts (1965-2009):
- **Equity indices**: Average TSM Sharpe ~0.5-0.8 (24 markets)
- **Currencies**: Average TSM Sharpe ~0.3-0.5 (12 markets)
- **Commodities**: Average TSM Sharpe ~0.4-0.7 (27 markets)
- **Bonds**: Average TSM Sharpe ~0.3-0.6 (10 markets)
- **Diversified portfolio**: Sharpe >1.0 (2.5x equity market)

### "Trends Everywhere" (Moskowitz et al. 2019) Extended Findings

- Traditional assets: TSM Sharpe = 1.17
- Alternative assets: TSM Sharpe = 1.34
- Equity factors: TSM Sharpe = 0.95
- Combined: TSM Sharpe = 1.60

### Current CTA Industry Context (2025)

- SG Trend Index: **-9.3% YTD** (worst period since 2022)
- Short-term CTAs outperforming long-term trend followers
- V-shaped reversals challenging longer lookback periods
- **Implication:** Our 20-120 day lookback ensemble is medium-term — may be vulnerable to same reversals

---

## 3. Candidate Assets — Comprehensive Evaluation

### Tier 1: Strong Candidates (High Momentum Alpha + Low Cost)

| Asset | Est. TSM Sharpe | Spread (bps RT) | Swap (bps/day) | Liquidity | Correlation to Current | Verdict |
|-------|-----------------|-----------------|----------------|-----------|------------------------|---------|
| **NAS100** | 0.598 | 1.0 | -0.30/+0.10 | Very High | 1.00 (self) | KEEP |
| **XAUUSD** | 0.374 | 0.72 | -0.50/+0.20 | Very High | 0.08 to NAS100 | KEEP |
| **BTCUSD** | ~0.8-1.2* | 4.86 | -3.00/-1.50 | High | ~0.15 to NAS100 | ADD (careful sizing) |
| **SPX500** | ~0.4-0.6 | ~1.2 | ~-0.25/+0.08 | Very High | ~0.85 to NAS100 | ADD (diversification) |
| **USDCHF** | ~0.3-0.5 | ~7.0 | ~+0.10/-0.15 | High | -0.5 to XAUUSD | ADD (hedge) |

*BTC Sharpe highly regime-dependent; 2016-2021 was exceptional

### Tier 2: Moderate Candidates

| Asset | Est. TSM Sharpe | Spread (bps RT) | Swap (bps/day) | Liquidity | Correlation | Verdict |
|-------|-----------------|-----------------|----------------|-----------|-------------|---------|
| **OIL** | 0.285 | 9.76 | -0.50/+0.15 | High | Low to all | KEEP (high DD caveat) |
| **NATGAS** | ~0.3-0.5 | ~15-25 | ~-1.00 | Medium | Low to all | CONSIDER |
| **USDJPY** | 0.204 | 7.12 | +0.08/-0.20 | Very High | -0.41 to XAUUSD | KEEP (weak but hedge) |
| **UK100** | ~0.3-0.4 | ~1.5 | ~-0.20 | High | ~0.7 to NAS100 | LOW PRIORITY |
| **GER40** | ~0.3-0.5 | ~1.2 | ~-0.15 | High | ~0.75 to NAS100 | LOW PRIORITY |

### Tier 3: Weak or Negative Candidates

| Asset | Est. TSM Sharpe | Spread (bps RT) | Verdict | Reason |
|-------|-----------------|-----------------|---------|--------|
| **EURUSD** | -0.155 | 7.0 | REJECT | Negative Sharpe in backtest |
| **GBPUSD** | 0.019 | 7.3 | REJECT | Near-zero alpha, costs dominate |
| **SILVER** | -0.030 | 13.16 | REJECT | Negative Sharpe, high costs |
| **USDCHF** | -0.501 | ~7.0 | REJECT (individual) | Negative Sharpe BUT useful as hedge |
| **ETHUSD** | ~0.3-0.5* | 23.34 | REJECT | Spread too high (23 bps!) |
| **US30** | 0.025 | ~2.4 | REJECT | Near-zero alpha, redundant with NAS100 |

*ETH excluded due to extreme spread costs (23 bps RT vs 4.86 for BTC)

---

## 4. Recommended Portfolio Configurations

### Option A: Conservative Expansion (6 assets)

**Goal:** Maximize Sharpe while controlling drawdown

| Asset | Weight | Rationale |
|-------|--------|-----------|
| NAS100 | 30% | Highest individual Sharpe (0.598), growth exposure |
| XAUUSD | 25% | Strong alpha (0.374), crisis hedge, low cost |
| BTCUSD | 15% | Highest potential Sharpe, but limit due to DD risk |
| USDJPY | 10% | Negative correlation to XAUUSD, safe-haven |
| OIL | 10% | Commodity diversification, low correlation |
| SPX500 | 10% | Index diversification (different sector mix than NAS100) |

**Expected metrics:**
- Sharpe: ~0.7-0.9 (estimated)
- Max DD: ~-25% to -30%
- Effective bets: ~5.5 (good diversification)
- Annual cost drag: ~150-200 bps

### Option B: Aggressive Diversification (8 assets)

**Goal:** Maximize diversification across asset classes

| Asset | Weight | Rationale |
|-------|--------|-----------|
| NAS100 | 20% | Core equity momentum |
| XAUUSD | 20% | Core commodity/hedge |
| BTCUSD | 10% | Crypto momentum (capped) |
| USDJPY | 10% | FX diversification |
| OIL | 10% | Energy momentum |
| SPX500 | 10% | Equity diversification |
| NATGAS | 10% | Energy diversification, low correlation |
| USDCHF | 10% | Gold hedge (negative corr) |

**Expected metrics:**
- Sharpe: ~0.6-0.8 (diminishing returns from 6→8 assets)
- Max DD: ~-22% to -28%
- Effective bets: ~6.5
- Annual cost drag: ~180-250 bps

### Option C: Minimal Cost (4 assets, optimized)

**Goal:** Minimize cost drag while maintaining alpha

| Asset | Weight | Rationale |
|-------|--------|-----------|
| NAS100 | 45% | Best risk-adjusted, lowest cost |
| XAUUSD | 35% | Strong alpha, very low spread (0.72 bps) |
| USDJPY | 15% | Hedge to XAUUSD |
| OIL | 5% | Minimal allocation, high DD risk |

**This is essentially the current optimal-weight portfolio (Sharpe 0.729).**

---

## 5. Cost-Benefit Analysis

### Per-Asset Risk-Adjusted Return After Costs

| Asset | Gross Sharpe | Cost Drag (bps/yr) | Net Sharpe (est.) | Cost/Alpha Ratio |
|-------|-------------|---------------------|-------------------|------------------|
| NAS100 | ~0.65 | 30 | 0.598 | LOW (excellent) |
| XAUUSD | ~0.55 | 180 | 0.374 | MODERATE |
| BTCUSD | ~1.0 | 350 | ~0.7 | MODERATE |
| USDJPY | ~0.25 | 40 | 0.204 | HIGH (marginal) |
| OIL | ~0.45 | 200 | 0.285 | HIGH |
| SPX500 | ~0.50 | 30 | ~0.45 | LOW (good) |
| NATGAS | ~0.45 | 400 | ~0.30 | HIGH |
| ETHUSD | ~0.50 | 800 | ~0.20 | EXTREME (avoid) |

### Spread Cost Hierarchy (Best to Worst)

1. XAUUSD: 0.72 bps RT — **exceptional**
2. NAS100: 1.0 bps RT — **excellent**
3. SPX500: ~1.2 bps RT — **excellent**
4. BTCUSD: 4.86 bps RT — **good**
5. USDJPY: 7.12 bps RT — **acceptable**
6. EURUSD: 7.0 bps RT — **acceptable** (but no alpha)
7. OIL: 9.76 bps RT — **moderate**
8. SILVER: 13.16 bps RT — **poor**
9. NATGAS: ~15-25 bps RT — **poor**
10. ETHUSD: 23.34 bps RT — **unacceptable**

---

## 6. Market Regime Analysis

### Which Assets Perform Best by Regime?

Based on academic research and CTA industry data:

| Regime | Best Assets | Worst Assets | Notes |
|--------|-------------|--------------|-------|
| **HIGH_VOL (crisis)** | BTC, XAUUSD, USDJPY | NAS100, OIL | TSM profits from extreme moves |
| **NORMAL** | NAS100, SPX500, OIL | USDJPY, USDCHF | Trend-following works in trends |
| **LOW_VOL (grinding)** | XAUUSD, USDCHF | OIL, BTC | Low vol = weak trends |
| **RISK_OFF** | XAUUSD, USDJPY, USDCHF | NAS100, OIL, BTC | Safe havens bid |
| **RISK_ON** | NAS100, BTC, OIL | XAUUSD, USDJPY | Risk assets bid |

### Trending vs Mean-Reverting Behavior

| Asset | Trend Strength | Mean Reversion | TSM Suitability |
|-------|---------------|----------------|-----------------|
| NAS100 | HIGH | Moderate | EXCELLENT |
| XAUUSD | HIGH | Moderate | GOOD |
| BTCUSD | VERY HIGH | Strong | EXCELLENT (but volatile) |
| OIL | HIGH | Strong | GOOD (but DD risk) |
| USDJPY | MODERATE | Moderate | FAIR |
| SPX500 | HIGH | Moderate | GOOD |
| NATGAS | VERY HIGH | VERY STRONG | FAIR (whipsaw risk) |

---

## 7. Optimal Portfolio Size Analysis

### Academic Evidence

From Moskowitz et al. (2012):
- Individual asset TSM Sharpe: 0.3-0.5
- 58-asset diversified portfolio: Sharpe >1.0
- Diversification benefit is **the primary driver** of high portfolio Sharpe

### Our Data Points

| N Assets | Portfolio | Sharpe | Effective Bets |
|----------|-----------|--------|----------------|
| 4 | 4-Asset Equal | 0.535 | 4.07 |
| 4 | 4-Asset Optimal | 0.729 | 4.07 |
| 8 | Full Ensemble | 1.062 | ~6-7 (est.) |
| 9 | Ex-Crypto | 0.373 | ~5-6 (est.) |

### Diminishing Returns Curve

Based on our data and academic research:
- **4 assets**: Sharpe ~0.5-0.7 (concentrated, high idiosyncratic risk)
- **6 assets**: Sharpe ~0.7-0.9 (sweet spot for retail)
- **8-10 assets**: Sharpe ~0.9-1.1 (approaching maximum diversification)
- **15+ assets**: Sharpe ~1.0-1.2 (marginal improvement, operational complexity)

**Recommendation: 6 assets is optimal for our setup.** It captures most diversification benefit while keeping operational complexity manageable.

---

## 8. Risk Considerations

### Key Risks

1. **Momentum Crashes**: TSM suffers largest losses during V-shaped reversals (2009, 2020, 2025)
   - Mitigation: Shorter lookbacks (20-40 days) recover faster than 120-day
   - Our ensemble uses all four, providing some protection

2. **Swap Cost Compounding**: Multi-week holds accumulate significant swap costs
   - XAUUSD: -0.50 bps/day × 60 days = -30 bps
   - BTCUSD: -3.00 bps/day × 60 days = -180 bps (!!)
   - Mitigation: Size BTC positions smaller, or use perpetual futures with better funding

3. **Correlation Regime Changes**: Assets can become correlated during crises
   - 2022: Everything correlated (inflation shock)
   - Mitigation: Diversify across asset classes, not just within

4. **Lookahead Bias in Weight Optimization**: Grid search on historical data may overfit
   - Current optimal weights: NAS100 45%, XAUUSD 35%, OIL 5%, USDJPY 15%
   - Mitigation: Use equal-weight as baseline, optimize only with walk-forward

5. **Data Snooping**: Testing many assets increases false discovery risk
   - Mitigation: Pre-register asset selection criteria BEFORE backtesting

### Maximum Drawdown Expectations

| Portfolio | Expected Max DD | DD Duration (est.) |
|-----------|-----------------|-------------------|
| 4-Asset | -19% to -24% | 1-2.5 years |
| 6-Asset | -18% to -25% | 1-3 years |
| 8-Asset | -15% to -22% | 1-2.5 years |

---

## 9. Implementation Recommendations

### Phase 1: Validate Current Portfolio (Week 1)

1. **Paper trade the 4-asset optimal-weight portfolio** for 2-4 weeks
2. Track per-asset signal accuracy
3. Monitor actual vs expected costs
4. Validate correlation stability

### Phase 2: Research New Assets (Weeks 2-3)

1. **Download historical data** for candidate assets:
   - SPX500 (S&P 500 CFD or futures)
   - BTCUSD (already have data)
   - USDCHF (already have data)
   - NATGAS (NG_F.csv exists in yfinance data)

2. **Run single-asset TSM backtests** on each candidate:
   - Individual Sharpe ratio
   - Max drawdown
   - Cost drag
   - Correlation to existing portfolio

3. **Pre-register asset selection criteria**:
   - Minimum individual Sharpe: >0.3
   - Maximum correlation to any existing asset: <0.6
   - Maximum spread cost: <15 bps RT
   - Maximum swap cost: <1.0 bps/day absolute

### Phase 3: Portfolio Expansion (Weeks 4-6)

1. **Test 6-asset portfolio** with pre-registered assets
2. Run ensemble backtest with DSR and PBO validation
3. Compare to 4-asset baseline
4. If Sharpe improvement >0.1 AND DSR significant → proceed

### Phase 4: Risk Management Enhancement

1. **Regime detection**: Add VIX-based regime filter
   - HIGH_VOL (VIX >25): Reduce position sizes by 50%
   - LOW_VOL (VIX <12): Reduce position sizes by 25%
   - NORMAL: Full positions

2. **Drawdown control**: Kill switch at -20% portfolio drawdown
   - Already implemented in kill_switch.py

3. **Correlation monitoring**: Weekly correlation matrix update
   - Alert if avg pairwise correlation >0.3

---

## 10. Summary: Ranked Assets by Expected Sharpe

| Rank | Asset | Expected Sharpe | Spread (bps) | Swap (bps/day) | Priority |
|------|-------|-----------------|--------------|----------------|----------|
| 1 | BTCUSD | 0.7-1.0 | 4.86 | -3.00/-1.50 | HIGH (cap at 10-15%) |
| 2 | NAS100 | 0.55-0.65 | 1.0 | -0.30/+0.10 | CORE |
| 3 | SPX500 | 0.40-0.55 | ~1.2 | ~-0.25/+0.08 | ADD |
| 4 | XAUUSD | 0.35-0.50 | 0.72 | -0.50/+0.20 | CORE |
| 5 | NATGAS | 0.30-0.50 | ~15-25 | ~-1.00 | CONSIDER |
| 6 | OIL | 0.25-0.35 | 9.76 | -0.50/+0.15 | KEEP (reduce weight) |
| 7 | USDJPY | 0.20-0.30 | 7.12 | +0.08/-0.20 | KEEP (hedge) |
| 8 | USDCHF | 0.15-0.25* | ~7.0 | ~+0.10/-0.15 | ADD (hedge only) |
| 9 | GER40 | 0.30-0.45 | ~1.2 | ~-0.15 | LOW PRIORITY |
| 10 | UK100 | 0.25-0.40 | ~1.5 | ~-0.20 | LOW PRIORITY |

*USDCHF has negative individual Sharpe but strong negative correlation to XAUUSD, making it valuable as a portfolio hedge

---

## 11. Final Recommendation

### Immediate Action (This Week)

1. **Keep the 4-asset portfolio** as baseline (NAS100, XAUUSD, OIL, USDJPY)
2. **Begin paper trading** the optimal-weight allocation: NAS100 45%, XAUUSD 35%, USDJPY 15%, OIL 5%
3. **Download BTCUSD and SPX500 data** for backtesting

### Short-Term (2-4 Weeks)

1. **Add BTCUSD** at 10-15% allocation (highest alpha potential)
2. **Add SPX500** at 10% allocation (index diversification)
3. **Reduce OIL** to 5% (high drawdown risk)
4. **Target 6-asset portfolio** with expected Sharpe ~0.7-0.9

### Medium-Term (1-3 Months)

1. **Evaluate NATGAS** if data quality improves
2. **Consider regime overlay** (VIX-based position sizing)
3. **Monitor CTA industry** for regime shifts in momentum effectiveness

### Portfolio Allocation Summary

| Asset | Current Weight | Recommended Weight | Change |
|-------|---------------|-------------------|--------|
| NAS100 | 25% (equal) / 45% (optimal) | 30% | -15% from optimal |
| XAUUSD | 25% / 35% | 25% | -10% from optimal |
| BTCUSD | 0% | 15% | NEW |
| USDJPY | 25% / 15% | 10% | -5% from optimal |
| OIL | 25% / 5% | 10% | +5% from optimal |
| SPX500 | 0% | 10% | NEW |

**Total: 6 assets, 100% allocation**

---

## Appendix A: Data Availability

| Asset | CSV File | Data Range | Status |
|-------|----------|------------|--------|
| NAS100 | data/NAS100_D1.csv | 2016+ | AVAILABLE |
| XAUUSD | data/XAUUSD_D1.csv | 2016+ | AVAILABLE |
| OIL | data/market_data/yfinance/CL_F.csv | 2016+ | AVAILABLE |
| USDJPY | data/USDJPY_D1.csv | 2016+ | AVAILABLE |
| BTCUSD | data/BTCUSD_D1.csv | 2016+ | AVAILABLE |
| ETHUSD | data/ETHUSD_D1.csv | 2016+ | AVAILABLE (but reject) |
| SPX500 | data/market_data/yfinance/_GSPC.csv | Available | NEEDS CONVERSION |
| USDCHF | data/USDCHF_D1.csv? | Check | NEEDS VERIFICATION |
| NATGAS | data/market_data/yfinance/NG_F.csv | Available | NEEDS CONVERSION |

## Appendix B: Pepperstone Spread Reference

| Asset | Razor Avg Spread | Commission | RT Cost (bps) | Source |
|-------|-----------------|------------|---------------|--------|
| XAUUSD | 0.19 pts | $0 | 0.72 | Pepperstone |
| NAS100 | ~1.0 pt | $0 | ~1.0 | Pepperstone |
| US500 | ~0.4 pts | $0 | ~1.2 | Pepperstone |
| BTCUSD | ~2.5 pts | $0 | 4.86 | Pepperstone |
| USDJPY | ~0.06 pts | $7/rt | 7.12 | Pepperstone |
| EURUSD | ~0.0 pts | $7/rt | 7.0 | Pepperstone |
| OIL | ~2.0 pts | $0 | 9.76 | Pepperstone |
| XAGUSD | ~3.3 pts | $0 | 13.16 | Pepperstone |
| NATGAS | ~0.005 | $0 | ~15-25 | Pepperstone |
| ETHUSD | ~11.7 pts | $0 | 23.34 | Pepperstone |

---

*This research document should be validated with actual backtests before any portfolio changes.*
*All expected Sharpe ratios are estimates based on academic literature and current backtest data.*
