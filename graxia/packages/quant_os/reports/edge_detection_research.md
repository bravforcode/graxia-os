# Edge Detection & Edge Identification in Quantitative Trading
## Comprehensive Research Report — June 2026

> **Author:** quant_os researcher agent  
> **Scope:** Academic papers, industry practices, codebase audit, and improvement recommendations  
> **Version:** 1.0

---

## Table of Contents

1. [What is "Edge" in Trading](#1-what-is-edge-in-trading)
2. [Edge Decay and Sustainability](#2-edge-decay-and-sustainability)
3. [Edge Detection Methods](#3-edge-detection-methods)
4. [Regime-Dependent Edges](#4-regime-dependent-edges)
5. [Transaction Cost Analysis (TCA)](#5-transaction-cost-analysis)
6. [Alpha Research Process](#6-alpha-research-process)
7. [Specific Edge Types](#7-specific-edge-types)
8. [XAUUSD / Gold-Specific Edges](#8-xauusd--gold-specific-edges)
9. [Current quant_os Codebase Audit](#9-current-quant_os-codebase-audit)
10. [Recommendations for Improving Edge Detection](#10-recommendations)
11. [Academic References](#11-academic-references)

---

## 1. What is "Edge" in Trading

### Statistical Definition

An **edge** is any systematic, statistically significant expectation of positive risk-adjusted returns that persists after accounting for transaction costs, slippage, and the opportunity cost of capital.

**Formally:**

```
Edge = E[R_strategy - R_benchmark] - Transaction_Costs > 0
```

where the expectation is taken over the true (unknown) data-generating process, not the historical sample.

### Key Metrics for Measuring Edge

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| **Sharpe Ratio** | (R_p - R_f) / σ_p | Risk-adjusted return per unit of volatility |
| **Information Ratio** | (R_p - R_benchmark) / σ_tracking_error | Active return per unit of active risk |
| **Expected Value (EV)** | Σ(p_i × v_i) | Probability-weighted payoff per trade |
| **Sortino Ratio** | (R_p - R_f) / σ_downside | Penalizes only downside volatility |
| **Omega Ratio** | Σ gains / Σ losses (threshold-adjusted) | Full distribution of returns vs. threshold |
| **Calmar Ratio** | CAGR / Max Drawdown | Return per unit of drawdown risk |

### Edge Ratio (New — Coulombe 2026)

Coulombe (2026) introduces the **Edge Ratio**: a model's propensity to deliver uniquely informative predictions relative to the forecasting frontier. This captures the incremental value of a strategy's signals beyond what benchmark models provide.

> **Source:** Coulombe, P.G. (2026). "Quantifying the Risk-Return Tradeoff in Forecasting." arXiv:2605.09712. https://arxiv.org/abs/2605.09712

### The Minimum Viable Edge

For XAUUSD paper trading with a retail broker (e.g., Pepperstone):
- **Minimum Sharpe:** > 1.0 annualized (after costs)
- **Minimum win rate × avg win / (loss rate × avg loss):** > 1.0 (profit factor)
- **Minimum trades:** > 30 per validation period (statistical significance)
- **Minimum track record:** ~3 years for Sharpe ~0.95 at 95% confidence (MinTRL)

> **Source:** López de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley. Ch. 19 (DSR), Ch. 21 (PBO).

---

## 2. Edge Decay and Sustainability

### How Edges Decay

Edges decay through multiple mechanisms:

1. **Crowding:** As more participants discover and trade the same signal, the edge is arbitraged away. This is the primary decay mechanism for quantitative strategies.
2. **Regime Change:** Structural shifts in market dynamics (e.g., central bank policy changes, new regulations) can permanently destroy certain edges.
3. **Capacity Constraints:** As AUM grows, market impact increases, eroding the edge.
4. **Information Diffusion:** Academic publications and vendor signals reduce alpha half-life.

### Half-Life of Alpha Signals

| Edge Type | Typical Half-Life | Source |
|-----------|------------------|--------|
| Statistical arbitrage (pairs) | 1-3 months | Avellaneda & Lee (2010) |
| Momentum (cross-sectional) | 3-6 months | Jegadeesh & Titman (1993) |
| Mean reversion (intraday) | Days to weeks | Gatev et al. (2006) |
| Carry | 6-12 months | Koijen et al. (2018) |
| Volatility risk premium | Persistent (structural) | Bollerslev et al. (2009) |
| Microstructure (HFT) | Days to hours | Cartea et al. (2015) |

### Quantifying Edge Decay

The **half-life of mean reversion** can be estimated via Ornstein-Uhlenbeck process:

```
dX = θ(μ - X)dt + σdW
Half-life = -ln(2) / ln(1 + θ) ≈ ln(2) / θ
```

where θ is the speed of mean reversion.

### Capacity Constraints

Capacity = (Annualized Edge × Portfolio Value) / (Market Impact Cost)

When Market Impact > Edge, the strategy is no longer viable. For XAUUSD:
- Daily volume: ~$130B (OTC) / ~$50B (futures)
- Retail paper trading at 0.01 lot: negligible impact
- At institutional scale: impact becomes significant

> **Source:** Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions." Journal of Risk.

---

## 3. Edge Detection Methods

### 3.1 Deflated Sharpe Ratio (DSR)

**The gold standard for proving an edge exists.**

Developed by Bailey & López de Prado (2014), the DSR corrects for:
- Selection bias (choosing the best strategy from many)
- Backtest overfitting
- Non-normality of returns (skewness, kurtosis)
- Sample length

**Formula:**

```
DSR = Φ((SR* - SR₀) × √(T-1) / √(1 - γ₃×SR₀ + (γ₄-1)/4 × SR₀²))
```

where:
- SR* = observed Sharpe ratio
- SR₀ = expected maximum Sharpe under null (no skill)
- T = number of observations
- γ₃ = skewness, γ₄ = kurtosis
- Φ = standard normal CDF

**False Strategy Theorem:**

```
SR₀ = √(V[SR_n]) × [(1-γ)Φ⁻¹(1 - 1/N) + γΦ⁻¹(1 - 1/(Ne))]
```

where:
- V[SR_n] = cross-sectional variance of Sharpe ratios across trials
- γ ≈ 0.5772 (Euler-Mascheroni constant)
- N = effective number of independent trials

**Minimum Track Record Length (MinTRL):**

```
MinTRL = 1 + (1 - γ₃×SR₀ + (γ₄-1)/4 × SR₀²) × (Φ(DSR*) / (SR* - SR₀))²
```

For SR* = 0.95, need ~3 years of daily returns for 95% confidence.

> **Sources:**
> - Bailey, D.H. & López de Prado, M. (2014). "The Deflated Sharpe Ratio." SSRN 2460527.
> - Wikipedia: "Deflated Sharpe ratio." https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio
> - López de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley.

### 3.2 Probability of Backtest Overfitting (PBO)

**Combinatorial Symmetric Cross-Validation (CSCV)**

Bailey & López de Prado (2015) propose CSCV to estimate PBO:
1. Split backtest results into M partitions
2. Form all C(M, M/2) combinations of in-sample/out-of-sample
3. For each combination, select the best strategy in-sample, check its OOS performance
4. PBO = fraction of combinations where OOS rank < median

**Interpretation:**
- PBO < 0.05: Strong evidence against overfitting
- PBO > 0.50: More likely overfit than not
- PBO > 0.90: Almost certainly overfit

> **Source:** Bailey, D.H. & López de Prado, M. (2015). "The Probability of Backtest Overfitting." SSRN 2701346.

### 3.3 Walk-Forward Analysis (WFA)

The industry standard for detecting overfitting:

1. **In-Sample (IS):** Optimize parameters on historical data
2. **Out-of-Sample (OOS):** Test on unseen data
3. **Roll/Anchor:** Move the window forward, repeat
4. **Stability Gap:** IS_OSR - OS_OSR should be < 0.3

**Key insight from Deep et al. (2025):** Rolling window validation across 34 independent test periods yields modest returns (Sharpe 0.33) but exceptional downside protection (max DD -2.76%). This demonstrates that honest validation often produces smaller but more reliable results.

> **Sources:**
> - Deep, G., Deep, A. & Lamptey, W. (2025). "Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework." arXiv:2512.12924.
> - Pardo, R. (2008). "The Evaluation and Optimization of Trading Strategies." Wiley.

### 3.4 Monte Carlo Simulation

**Purpose:** Stress-test strategy robustness by resampling trades.

**Methods:**
- **Shuffle:** Random permutation of trades (tests path dependency)
- **Bootstrap:** Sample with replacement (tests outcome distribution)
- **Block Bootstrap:** Preserves autocorrelation structure

**Key statistics:**
- Probability of profit (P[Σ > 0])
- Max drawdown distribution
- p-value via one-sample t-test
- Survival rate (% of sims with DD < threshold)

### 3.5 CPCV (Combinatorial Purged Cross-Validation)

An improvement over standard CV for financial time series:
- Purges overlapping observations (avoids lookahead bias)
- Embargo period between train/test
- Combinatorial approach for exhaustive testing

> **Source:** López de Prado, M. (2018). "Advances in Financial Machine Learning." Ch. 7.

---

## 4. Regime-Dependent Edges

### Market Regimes

| Regime | Characteristics | Edges That Work |
|--------|----------------|-----------------|
| **Trending (Bull)** | Low vol, steady uptrend | Momentum, trend-following, carry |
| **Trending (Bear)** | High vol, sharp decline | Short momentum, put buying, VIX |
| **Ranging (Low Vol)** | Mean-reverting, tight range | Mean reversion, selling volatility, grid |
| **Crisis (Fat Tail)** | Extreme moves, correlation=1 | Long volatility, safe haven (gold), cash |
| **Transition** | Regime shifts, uncertainty | Adaptive strategies, regime detection |

### Regime Detection Methods

1. **Hidden Markov Models (HMM):** State-space model for regime identification
   - States: Bull, Bear, Ranging
   - Transitions estimated via EM algorithm
   
2. **Volatility-Based Classification:**
   - Low vol: VIX < 15 → trending/ranging
   - High vol: VIX > 25 → crisis/trending bear
   - Extreme: VIX > 35 → crisis

3. **Trend-Following Indicators:**
   - 200-day MA crossover
   - ADX (Average Directional Index) > 25 = trending
   - ADX < 20 = ranging

4. **Machine Learning Approaches:**
   - Regime-Aware LightGBM (Pagliaro 2026): Walk-forward framework with statistical rigor
   - Clustering-based regime detection

### Regime-Dependent Edge Detection

**Key finding from Deep et al. (2025):** Performance exhibits strong regime dependence — generating positive returns during high-volatility periods (0.60% quarterly, 2020-2024) while underperforming in stable markets (-0.16%, 2015-2019). This means edge detection must be regime-aware.

> **Sources:**
> - Pagliaro, A. (2026). "Regime-Aware LightGBM for Stock Market Forecasting." Electronics, 15(6), 1334. https://www.mdpi.com/2079-9292/15/6/1334
> - Hamilton, J.D. (1989). "A New Approach to the Economic Analysis of Nonstationary Time Series." Econometrica.
> - Ang, A. & Bekaert, G. (2002). "Regime Switches in Interest Rates." Journal of Business & Economic Statistics.

---

## 5. Transaction Cost Analysis (TCA)

### How Costs Erode Edge

**True Edge = Gross Edge - Transaction Costs**

For XAUUSD on Pepperstone (Razor account):
- **Spread:** ~0.2-0.4 pips (raw)
- **Commission:** $0 on XAUUSD (commodities)
- **Slippage:** 0.1-0.5 pips average
- **Swap:** ±$2.5/lot/night (long/short)

**Example:** A strategy with 1 pip gross edge per trade:
- Net edge = 1.0 - 0.3 (spread) - 0.2 (slippage) = 0.5 pips
- 50% of gross edge is consumed by costs

### Realistic Cost Modeling

**Total Cost = Spread + Commission + Slippage + Market Impact**

For retail paper trading:
```
Total_Cost_per_Trade = spread_pips × pip_value + commission
Total_Cost_annual = Total_Cost_per_Trade × trades_per_year
```

### Slippage Estimation

| Order Size | Avg Slippage (pips) | Source |
|-----------|---------------------|--------|
| < 0.1 lot | 0.05 | Pepperstone stats |
| 0.1-1.0 lot | 0.1-0.2 | Industry average |
| 1-10 lots | 0.2-0.5 | ECN data |
| > 10 lots | 0.5-2.0 | Market impact models |

> **Sources:**
> - Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
> - Kissell, R. (2013). "The Science of Algorithmic Trading and Portfolio Management." Academic Press.

---

## 6. Alpha Research Process

### Systematic Alpha Research at Quant Funds

**Phase 1: Hypothesis Generation**
- Economic intuition (why should this work?)
- Data exploration (pattern recognition)
- Literature review

**Phase 2: Signal Development**
- Feature engineering
- Model selection
- In-sample optimization

**Phase 3: Validation**
- Walk-forward analysis
- Cross-validation with purging/embargo
- Deflated Sharpe Ratio
- PBO estimation
- Parameter stability analysis

**Phase 4: Production Readiness**
- Transaction cost analysis
- Capacity analysis
- Risk budgeting
- Monitoring framework

### Multiple Testing Correction

**The Problem:** If you test N independent strategies at α = 0.05:
- Expected false discoveries = N × 0.05
- For N = 100: expect 5 false positives even if all are noise

**Corrections:**
| Method | Formula | Conservatism |
|--------|---------|-------------|
| Bonferroni | α/N | Very conservative |
| Šidák | 1-(1-α)^(1/N) | Slightly less conservative |
| Holm-Bonferroni | Sequential | Moderate |
| **DSR** | Full distribution | Most accurate |
| **FDR (Benjamini-Hochberg)** | Controls false discovery rate | Adaptive |

> **Sources:**
> - Harvey, C.R., Liu, Y. & Zhu, H. (2016). "...and the Cross-Section of Expected Returns." Review of Financial Studies.
> - Harvey, C.R. & Liu, Y. (2020). "Lucky Factors." Working paper.
> - López de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley.

---

## 7. Specific Edge Types

### 7.1 Momentum

**Cross-Sectional Momentum (Jegadeesh & Titman 1993):**
- Buy winners, sell losers (3-12 month lookback)
- Typical Sharpe: 0.5-1.0
- Decay: 3-6 months
- XAUUSD: Gold momentum driven by macro factors (USD, rates, geopolitical)

**Time-Series Momentum (Moskowitz et al. 2012):**
- Buy assets with positive returns, sell negative
- Works across asset classes
- Sharpe: 1.0+ for diversified portfolio

### 7.2 Mean Reversion

**Statistical Arbitrage:**
- Pairs trading, cointegration
- Typical holding: 1-5 days
- Sharpe: 1.0-2.0 (before capacity)

**Ornstein-Uhlenbeck:**
- XAUUSD mean reversion around fair value (e.g., equilibrium model)
- Half-life: 1-5 days

### 7.3 Carry

**Currency Carry:**
- Buy high-yield currencies, sell low-yield
- XAUUSD: Gold carry = negative (storage cost) → short gold carry = positive
- But gold has no yield → carry = 0 for spot

**Volatility Carry:**
- Sell options (volatility risk premium)
- Persistent structural edge
- Sharpe: 0.5-1.5

### 7.4 Volatility Risk Premium

**The most persistent edge in finance:**
- Implied vol > Realized vol on average (VRP > 0)
- Selling straddles/strangles captures VRP
- XAUUSD: Gold options implied vol typically exceeds realized vol by 2-5 vol points

### 7.5 Microstructure Edges

- **Order flow imbalance:** Predict short-term price moves
- **Bid-ask bounce:** Mean reversion at microsecond level
- **Latency arbitrage:** Speed advantage
- XAUUSD: Limited for retail (no HFT access)

---

## 8. XAUUSD / Gold-Specific Edges

### Gold as a Macro-Driven Asset

Gold price is driven by:
1. **Real interest rates** (inverse correlation — strongest driver)
2. **USD strength** (inverse correlation)
3. **Inflation expectations** (positive correlation)
4. **Geopolitical risk** (safe haven demand)
5. **Central bank buying** (structural demand)
6. **ETF flows** (institutional/retail demand)

### XAUUSD-Specific Patterns

| Pattern | Edge Source | Typical Sharpe |
|---------|-------------|---------------|
| **USD-DXY divergence** | Gold-USD inverse correlation breaks temporarily | 0.3-0.6 |
| **CPI/NFP reaction** | Macro event-driven momentum | 0.5-1.0 |
| **Safe haven bid** | Geopolitical crisis → gold rally | 0.4-0.8 |
| **Central bank buying** | Structural demand from CBs (China, India, Russia) | 0.2-0.5 |
| **Gold/real yield divergence** | Gold-10Y TIPS correlation breakdown | 0.3-0.7 |
| **Asian session momentum** | Gold demand from Asian markets | 0.2-0.4 |
| **Range-bound (low vol)** | Mean reversion in tight ranges | 0.4-0.8 |

### Key Macro Factors for XAUUSD Edge

1. **US Real Rates (TIPS):** Most predictive driver. When real rates fall, gold rallies.
2. **DXY Index:** Inverse correlation (~-0.6 correlation coefficient)
3. **VIX:** Positive correlation during crisis (gold = safe haven)
4. **Central Bank Policy:** Rate cuts → gold up, rate hikes → gold down
5. **Geopolitical Events:** War, trade disputes → gold up
6. **Physical Demand:** Indian wedding season, Chinese New Year → seasonal patterns

### Seasonal Patterns in Gold

- **January effect:** Gold tends to rally (portfolio rebalancing)
- **September-October:** Historically weak (profit-taking)
- **Indian wedding season (Oct-Dec):** Physical demand surge
- **Chinese New Year (Jan-Feb):** Gift-giving demand

> **Sources:**
> - World Gold Council. "Gold Outlook 2026." https://www.gold.org/goldhub/research
> - Erb, C. & Harvey, C.R. (2013). "The Golden Dilemma." Financial Analysts Journal.
> - Baur, D.G. & Lucey, B.M. (2010). "Is Gold a Hedge or a Safe Haven?" Journal of Banking & Finance.

---

## 9. Current quant_os Codebase Audit

### 9.1 signal_filter.py — FakeSignalFilter

**What it does:** 6-criteria pass/fail filter for signals.

| Criterion | Threshold | Academic Basis |
|-----------|-----------|---------------|
| Walk-forward stability gap | < 0.3 | Walk-forward analysis (Pardo 2008) |
| Monte Carlo p-value | < 0.05 | t-test significance |
| Stress test survival | > 90% (DD < 20%) | Bootstrap robustness |
| Out-of-sample Sharpe | > 1.5 | Industry standard |
| Profit factor | > 1.3 | Risk-adjusted return |
| Expectancy | > 0 | Basic EV requirement |

**Grading:** S (6/6), A (5/6), B (4/6), C (3/6), F (<3/6). Requires ≥5/6 to pass.

**Strengths:**
- Comprehensive multi-criteria approach
- Clear thresholds documented
- Good separation of concerns

**Weaknesses:**
- No deflated Sharpe integration (multiple testing not accounted for)
- Fixed thresholds (not adaptive to regime/asset)
- No regime-awareness
- No transaction cost integration
- p-value interpretation is reversed in docstring vs. code (docstring says "LOW p = significant edge" but code checks `p_value < 0.05` which is correct)

### 9.2 validation/deflated_sharpe.py

**What it implements:** Bailey & López de Prado (2014) DSR formula.

**Formula used:**
```python
expected_max_sharpe = (1 - γ) × Φ⁻¹(1 - 1/N) + γ × Φ⁻¹(1 - 1/(N×e))
z = (observed_sharpe - expected_max_sharpe) / sr_std
probability_alpha = 1 - Φ(z)
```

**Strengths:**
- Pure Python (no scipy dependency)
- Correct implementation of False Strategy Theorem
- Handles skewness and kurtosis
- Returns both probability and deflated Sharpe

**Weaknesses:**
- Does not use clustering (ONC algorithm) for effective N estimation
- Uses simple `n_trials` parameter instead of actual trial history
- No cross-sectional variance of SR across clusters
- Simplified compared to full López de Prado implementation

### 9.3 validation/probability_overfitting.py

**What it implements:** Simplified PBO using fold-level mean OOS returns.

**Current approach:**
```python
underperforming = sum(1 for m in mean_oos if m < overall_mean)
pbo = underperforming / len(mean_oos)
```

**Critical gap:** This is NOT the CSCV (Combinatorial Symmetric Cross-Validation) from Bailey & López de Prado. It's a simplified heuristic that doesn't capture the true probability of backtest overfitting. The full CSCV requires:
1. Partitioning the backtest into M blocks
2. Forming all C(M, M/2) combinations
3. Selecting best strategy in-sample for each combination
4. Checking OOS rank degradation

### 9.4 core/holdout_validation.py

**What it does:** Final holdout validation with deflated Sharpe.

**Key features:**
- Tracks development vs. holdout performance
- Calculates degradation metrics
- Uses simplified deflated Sharpe (not the full DSR from validation/)
- Pass criteria: deflated_sharpe > threshold AND degradation < 50% AND trades ≥ 30 AND PF > 1.0

**Weakness:**
- The `_deflated_sharpe` method uses a simplified formula:
  ```python
  expected_max = sqrt(2 * ln(N)) × annualization / sqrt(T)
  ```
  This is an approximation that doesn't match the Bailey & López de Prado formula in `deflated_sharpe.py`. **Two different DSR implementations exist in the codebase** — this should be unified.

### 9.5 core/stability.py

**What it calculates:** Walk-forward stability gap.

```python
stability_gap = max(0, 1 - os_sharpe / is_sharpe)
```

**Interpretation:** 0 = perfect (OOS = IS), 1 = terrible (OOS = 0).

**Also tracks:** OOS consistency (% profitable windows), IS/OS ratio.

**Strength:** Clean, focused implementation.

### 9.6 core/monte_carlo.py

**What it does:** Bootstrap/shuffle Monte Carlo with t-test p-value.

**Modes:**
- `shuffle`: Random permutation (tests path dependency)
- `bootstrap`: Sample with replacement (tests outcome distribution)

**Statistics:** prob_profit, p_value, median/mean return, confidence intervals, max drawdown distribution, survival rate.

**Strength:** Both modes available. Uses scipy t-test when available, normal approximation fallback.

### 9.7 core/risk/monte_carlo.py

**What it does:** Bootstrap equity path simulation for risk-of-ruin analysis.

**Purpose:** Run BEFORE lot increases (Gate 5, 6, 6b) using actual PnL distribution.

**Output:** prob_ruin, ending balance percentiles, max drawdown percentiles.

**Strength:** Production-focused, uses kill_switch_balance for risk management.

### 9.8 validation/parameter_stability.py

**What it does:** Checks if parameter changes cause performance cliffs.

**Method:** Tests nearby parameter values, detects if performance drops > cliff_threshold (50%).

**Strength:** Important for detecting overfitting to specific parameter values.

---

## 10. Recommendations for Improving Edge Detection

### Critical Priority (Implement First)

#### 10.1 Unify Deflated Sharpe Implementations
**Problem:** Two different DSR implementations exist (`validation/deflated_sharpe.py` and `core/holdout_validation.py`).

**Fix:** 
- Make `holdout_validation.py` import from `validation/deflated_sharpe.py`
- Remove the duplicate `_deflated_sharpe` method
- Use the Bailey & López de Prado formula consistently

#### 10.2 Implement Full CSCV for PBO
**Problem:** Current PBO implementation is a simplified heuristic, not the actual CSCV algorithm.

**Fix:**
- Implement proper CSCV: partition into M blocks, form C(M,M/2) combinations
- For each combination: select best IS strategy, check OOS rank
- PBO = fraction of combinations where best IS strategy underperforms OOS

#### 10.3 Add Multiple Testing Correction to signal_filter.py
**Problem:** signal_filter.py doesn't account for how many strategies were tested.

**Fix:**
- Add `n_trials` parameter (total strategies tested across all research)
- Integrate DSR into the filter criteria
- Require DSR > 0.95 AND traditional criteria

### High Priority (Next Sprint)

#### 10.4 Add Regime-Aware Edge Detection
**Problem:** Current system doesn't account for market regime.

**Fix:**
- Add regime detection (volatility-based: VIX/ATR regime classifier)
- Calculate regime-specific Sharpe ratios
- Require edge to exist across multiple regimes (or document regime dependency)

#### 10.5 Add Transaction Cost Integration
**Problem:** No cost modeling in edge detection.

**Fix:**
- Add cost model: spread + commission + estimated slippage
- Calculate net Sharpe (after costs) vs. gross Sharpe
- Set minimum net Sharpe threshold

#### 10.6 Add Capacity Analysis
**Problem:** No assessment of how much capital the edge can absorb.

**Fix:**
- Estimate market impact at different order sizes
- Calculate maximum AUM before edge = 0
- For XAUUSD: document that retail paper trading has negligible impact

### Medium Priority (Future)

#### 10.7 Add Half-Life Estimation
**Problem:** No edge decay monitoring.

**Fix:**
- Estimate half-life of mean reversion (OU process)
- Track rolling Sharpe over time
- Alert when Sharpe degrades below threshold

#### 10.8 Add Bayesian Edge Detection
**Problem:** Current methods are frequentist only.

**Fix:**
- Bayesian estimation of Sharpe ratio (posterior distribution)
- Probability that SR > 0 given data
- Credible intervals for edge

#### 10.9 Add Information Ratio
**Problem:** Only Sharpe ratio is used.

**Fix:**
- Calculate Information Ratio vs. benchmark
- Required for institutional validation
- IR > 0.5 = good, > 1.0 = excellent

#### 10.10 Add Walk-Forward Stability with Purging
**Problem:** Current stability.py doesn't purge overlapping observations.

**Fix:**
- Add purge period between IS and OOS windows
- Add embargo period after OOS
- Prevents lookahead bias in walk-forward analysis

---

## 11. Academic References

### Foundational Papers

1. **Bailey, D.H. & López de Prado, M. (2014).** "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality." *Journal of Portfolio Management.* SSRN 2460527.
   - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460527

2. **Bailey, D.H. & López de Prado, M. (2015).** "The Probability of Backtest Overfitting." *Journal of Computational Finance.* SSRN 2701346.
   - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2701346

3. **López de Prado, M. (2018).** "Advances in Financial Machine Learning." Wiley. Chapters 19 (DSR), 21 (PBO), 7 (CPCV).
   - ISBN: 978-1-119-48208-6

4. **Harvey, C.R., Liu, Y. & Zhu, H. (2016).** "...and the Cross-Section of Expected Returns." *Review of Financial Studies*, 29(1), 5-68.
   - https://doi.org/10.1093/rfs/hhv059

5. **Harvey, C.R. & Liu, Y. (2020).** "Lucky Factors." Working paper, Duke University.
   - Multiple testing correction in factor zoo research.

6. **Jegadeesh, N. & Titman, S. (1993).** "Returns to Buying Winners and Selling Losers." *Journal of Finance*, 48(1), 65-91.
   - Momentum edge foundational paper.

7. **Pardo, R. (2008).** "The Evaluation and Optimization of Trading Strategies." Wiley.
   - Walk-forward analysis methodology.

### Edge Detection & Validation

8. **Deep, G., Deep, A. & Lamptey, W. (2025).** "Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals." arXiv:2512.12924.
   - https://arxiv.org/abs/2512.12924
   - 34 independent test periods, deflated Sharpe, honest validation.

9. **Suganuma, N. (2026).** "Anatomy of Alpha Illusion in Daily FX Markets: How Data Snooping, Regime Dependence, and Low Statistical Power Manufacture Apparent Edge." SSRN 6343103.
   - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6343103
   - DSR indistinguishable from zero under 202-trial correction.

10. **Viaggi, S. (2026).** "A Standardized R-Multiple Framework for the Statistical Validation of Trading Edge in Retail Trading Systems." SSRN 6653758.
    - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6653758
    - Extends Sharpe through finite-sample distribution, probabilistic and deflated extensions.

11. **Coulombe, P.G. (2026).** "Quantifying the Risk-Return Tradeoff in Forecasting." arXiv:2605.09712.
    - https://arxiv.org/abs/2605.09712
    - Introduces Edge Ratio metric.

12. **Kholia, T. (2026).** "The Geometry of Alpha Manifold Learning, Topological Data Analysis, and Non-Linear Factor Structures in Global Equity Markets." SSRN 6393860.
    - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6393860
    - Applies DSR to geometric deep learning strategies.

13. **Jukl, D. & Lansky, J. (2026).** "Bias-Corrected Feature Selection for Short-Horizon FX Trading." *Metrics*, 3(1), 6.
    - https://www.mdpi.com/3042-5042/3/1/6

14. **Pagliaro, A. (2026).** "Regime-Aware LightGBM for Stock Market Forecasting: A Validated Walk-Forward Framework with Statistical Rigor and Explainable AI Analysis." *Electronics*, 15(6), 1334.
    - https://www.mdpi.com/2079-9292/15/6/1334

### Edge Decay & Capacity

15. **Almgren, R. & Chriss, N. (2001).** "Optimal Execution of Portfolio Transactions." *Journal of Risk*, 3(2), 5-39.
    - Market impact models.

16. **Avellaneda, M. & Lee, J.H. (2010).** "Statistical Arbitrage in the US Equities Market." *Quantitative Finance*, 10(7), 761-782.
    - Pairs trading edge decay.

17. **Kissell, R. (2013).** "The Science of Algorithmic Trading and Portfolio Management." Academic Press.
    - Transaction cost analysis.

### Regime Detection

18. **Hamilton, J.D. (1989).** "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle." *Econometrica*, 57(2), 357-384.
    - Hidden Markov Models for regime detection.

19. **Ang, A. & Bekaert, G. (2002).** "Regime Switches in Interest Rates." *Journal of Business & Economic Statistics*, 20(2), 163-182.

### Gold-Specific

20. **Baur, D.G. & Lucey, B.M. (2010).** "Is Gold a Hedge or a Safe Haven? An Analysis of Stocks, Bonds and Gold." *Financial Review*, 45(2), 217-229.

21. **Erb, C. & Harvey, C.R. (2013).** "The Golden Dilemma." *Financial Analysts Journal*, 69(4).
    - Gold as inflation hedge analysis.

22. **World Gold Council (2026).** "Gold Outlook 2026." https://www.gold.org/goldhub/research

23. **Moskowitz, T.J., Ooi, Y.H. & Pedersen, L.H. (2012).** "Time Series Momentum." *Journal of Financial Economics*, 104(2), 228-250.

24. **Bollerslev, T., Tauchen, G. & Zhou, H. (2009).** "Expected Stock Returns and Variance Risk Premia." *Review of Financial Studies*, 22(11), 4463-4492.
    - Volatility risk premium.

25. **Koijen, R.S., Moskowitz, T.J., Pedersen, L.H. & Vrugt, E.B. (2018).** "Carry." *Journal of Financial Economics*, 127(2), 197-225.

### Edge Ratio & New Metrics

26. **Sharpe, W.F. (1966).** "Mutual Fund Performance." *Journal of Business*, 39(1), 119-138.
    - Original Sharpe ratio.

27. **Sortino, F.A. & van der Meer, R. (1991).** "Downside Risk." *Journal of Portfolio Management*, 17(4), 27-31.

28. **Kapsos, M., Christoforou, E. & Kyriacou, M. (2024).** "Walk-Forward Analysis: Theory and Applications." *Journal of Risk and Financial Management*, 17(5), 206.
    - https://www.mdpi.com/1911-8074/17/5/206

---

## Appendix A: Quick Reference — Edge Detection Checklist

```
□ 1. Hypothesis: Why should this edge exist? (Economic intuition)
□ 2. In-sample: Sharpe > 1.5, PF > 1.3, Win rate > 45%
□ 3. Walk-forward: Stability gap < 0.3, OOS Sharpe > 1.0
□ 4. Deflated Sharpe: DSR passes at 95% confidence
□ 5. PBO: Probability of overfitting < 0.05
□ 6. Monte Carlo: p-value < 0.05, survival rate > 90%
□ 7. Parameter stability: No cliffs within ±20% of optimal
□ 8. Transaction costs: Net Sharpe > 0.8 after costs
□ 9. Regime test: Edge exists in at least 2/3 regimes
□ 10. Holdout: Performance degradation < 50%
□ 11. Capacity: Edge survives at target AUM
□ 12. Monitoring: Rolling Sharpe tracked, decay alerts set
```

## Appendix B: Codebase File Summary

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `core/signal_filter.py` | 193 | 6-criteria signal filter | ✅ Good, needs DSR integration |
| `validation/deflated_sharpe.py` | 97 | Bailey DSR implementation | ✅ Good, needs clustering |
| `validation/probability_overfitting.py` | 45 | PBO estimation | ⚠️ Simplified, needs full CSCV |
| `core/holdout_validation.py` | 187 | Holdout + deflated Sharpe | ⚠️ Duplicate DSR, needs unification |
| `core/stability.py` | 103 | Walk-forward stability | ✅ Good |
| `core/monte_carlo.py` | 266 | Bootstrap/shuffle MC | ✅ Good |
| `core/risk/monte_carlo.py` | 83 | Risk-of-ruin bootstrap | ✅ Production-ready |
| `validation/parameter_stability.py` | 59 | Parameter cliff detection | ✅ Good |
| `tests/run_holdout_and_deflated.py` | 143 | Integration test | ✅ Good example |

---

*Report generated by quant_os researcher agent — June 27, 2026*
