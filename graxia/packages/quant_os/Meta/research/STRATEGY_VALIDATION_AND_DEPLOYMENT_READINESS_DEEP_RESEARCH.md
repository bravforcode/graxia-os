# Strategy Validation & Deployment Readiness: Gap Analysis
## Deep Research Report — 2026-07-04

> **Researcher Agent** | **5 research topics** | **AQR, QuantConnect, industry papers**
> Sources: AQR White Papers (Active Extension, Diversifiers Forever, Diversifying Alternatives and the Rearview Mirror, Broad Strategic Asset Allocation, Key Design Choices When Building a Risk-Mitigating Portfolio, Was That Intentional?), quant_os vault research (EDGE_DETECTION_DEEP_RESEARCH.md, deployment_runbook.md), industry standards.

---

## Table of Contents

1. [Paper Trading Validation Duration Requirements](#1-paper-trading-validation-duration-requirements)
2. [Regime Change Detection in Live Trading](#2-regime-change-detection-in-live-trading)
3. [Strategy Decay Monitoring Metrics](#3-strategy-decay-monitoring-metrics)
4. [Strategy Return Decomposition (Alpha vs Beta vs Carry)](#4-strategy-return-decomposition-alpha-vs-beta-vs-carry)
5. [Strategy Portfolio Construction & Allocation](#5-strategy-portfolio-construction--allocation)
6. [Validation Gap Analysis: Backtest vs Live](#6-validation-gap-analysis-backtest-vs-live)
7. [Actionable Recommendations for quant_os](#7-actionable-recommendations-for-quant_os)

---

## 1. Paper Trading Validation Duration Requirements

### Industry Standards

| Source | Minimum Duration | Recommended | Rationale |
|--------|-----------------|-------------|-----------|
| **AQR Capital** (5-step pipeline) | 6-18 months paper | — | In-sample → OOS temporal → OOS cross-sectional → paper → live |
| **DE Shaw** (layered pipeline) | 6+ months | 12 months | Each layer separated by internal APIs |
| **quant_os deployment_runbook** | 8 weeks minimum | 12 weeks | Paper trade Sharpe within 25% of backtest |
| **quant_os broker_verification_report** | 8-12 weeks | — | Demo capital before live |
| **QuantConnect** | 2-4 weeks minimum | — | Paper trading mode available |
| **Industry consensus (CTA/managed futures)** | 6 months | 12 months | Full market cycle required |

### Key Validation Gates During Paper Trading

From our deployment_runbook.md (lines 48-56):
- Paper trade duration ≥ 8 weeks completed
- Live slippage within backtest assumptions (±20%)
- No kill-switch false triggers during paper trade
- Data feed uptime ≥ 99.5% during paper period
- Signal generation matches backtest expectations
- Rebalance execution time < 5 minutes per cycle
- **Paper trade Sharpe within 25% of backtest Sharpe**

### Critical Gap in quant_os

**Current state:** 28-day (4-week) paper trading requirement in pre_register_b2.md.

**Industry standard:** 6-18 months for institutional-grade validation. Even our own deployment_runbook specifies 8-12 weeks. The 4-week minimum is insufficient for:
- Capturing regime transitions
- Validating signal behavior across different volatility environments
- Confirming slippage assumptions hold under various market conditions
- Testing correlation regime shifts (especially relevant for multi-asset TSM)

### Recommended Minimum Paper Trading Duration

| Strategy Type | Minimum Paper | Rationale |
|---------------|---------------|-----------|
| **Trend-following (TSM)** | 12 weeks | Must capture at least 2-3 trend reversals |
| **Mean-reversion** | 8 weeks | Shorter cycles, but needs multiple regime transitions |
| **Carry** | 16 weeks | Must survive at least 1 "carry crash" scenario |
| **Multi-strategy** | 24 weeks | Must validate correlation assumptions |

---

## 2. Regime Change Detection in Live Trading

### Early Warning Signals

Based on AQR's research and industry practices:

#### 2.1 Volatility Regime Shifts

**Indicator: Realized vs Implied Volatility Spread**
- When realized vol diverges from implied vol by >1.5 standard deviations, regime shift is likely
- VIX term structure inversion (backwardation) is a strong signal
- AQR's "Diversifying Alternatives and the Rearview Mirror" paper notes that diversifiers "feel disappointing in bull markets, yet remain vital for long-term portfolio resilience" — this means regime detection is critical for knowing when diversifiers will activate

**Metric Implementation:**
```python
vol_regime = realized_vol_20d / realized_vol_120d
if vol_regime > 1.5:
    # Volatility expansion regime — tighten risk
elif vol_regime < 0.7:
    # Volatility compression regime — potential break pending
```

#### 2.2 Correlation Regime Breaks

**Indicator: Rolling Cross-Asset Correlation**
- Cross-asset correlation spike > 0.7 = crisis regime (all correlations go to 1)
- Our deployment_runbook already monitors this: "Correlation spike alert: realized cross-asset correlation > 0.7"
- AQR's "Key Design Choices When Building a Risk-Mitigating Portfolio" emphasizes that trend following performs well in "both growth- and inflation-driven bear markets" — regime detection determines which path

**Metric:**
```python
corr_matrix = rolling_corr(returns, window=60)
avg_corr = corr_matrix.mean()
if avg_corr > 0.7:
    # Crisis regime — all assets correlating, reduce exposure
elif avg_corr < 0.2:
    # Idiosyncratic regime — diversification benefits max
```

#### 2.3 Trend Regime Detection

**Indicator: Dual-Lookback Signal Divergence**
- Our TSM strategy uses 20d + 120d lookbacks
- When short-term and long-term signals diverge for >3 weeks, regime transition is in progress
- AQR's "Key Design Choices" recommends combining "short-/long-term price and economic trend signals" for this exact reason

**Metric:**
```python
signal_divergence = sign(short_signal) != sign(long_signal)
divergence_duration = consecutive_days(signal_divergence)
if divergence_duration > 15:  # 3 weeks
    # Regime transition — reduce position size
```

#### 2.4 Macro Regime Indicators

From AQR's "Broad Strategic Asset Allocation" and "Diversifiers Forever" papers:
- **Inflation regime:** CPI trend direction + breakeven spread changes
- **Growth regime:** ISM manufacturing + yield curve slope
- **Liquidity regime:** TED spread + FRA-OIS spread + credit spreads
- **Risk appetite:** VIX level + high yield spread + equity put/call ratio

### Early Warning Framework

| Signal | Threshold | Action |
|--------|-----------|--------|
| Vol regime (realized/long-term) | > 1.5 or < 0.7 | Reduce position size by 30% |
| Correlation spike | > 0.7 | Reduce exposure by 50% |
| Signal divergence duration | > 15 days | Halve position size |
| Trend strength (ADX) | < 20 | Reduce to 25% of normal |
| Max drawdown (rolling 60d) | > 15% | Trigger review, consider halt |

---

## 3. Strategy Decay Monitoring Metrics

### 3.1 Alpha Decay Theory

From the vault's EDGE_DETECTION_DEEP_RESEARCH.md (Sources 3.1-3.7):

**Key insight (Source 3.1 — Meng & Chen, 2026):** "Algorithmic trading accounts for 60–80% of US equity volume; the act of trading erodes the inefficiencies that generated alpha."

**Key insight (Source 3.3 — Chen & Kawashima, 2026):** "Alpha decay is a fundamental phenomenon in quantitative finance — as more participants discover and trade a signal, the edge diminishes."

**Key insight (Source 3.4 — Yuan et al., 2026):** "Different factors exhibit different decay profiles" — some signals decay faster than others.

### 3.2 Decay Detection Metrics

#### Primary Metrics (Must Monitor)

| Metric | Calculation | Decay Threshold | Action |
|--------|-------------|-----------------|--------|
| **Rolling Sharpe** | Sharpe(60d) | < 0.5 | Alert; < 0.3 = halt | 
| **Rolling Information Ratio** | IR(60d) vs benchmark | < 0.3 | Investigate signal quality |
| **Win Rate Decay** | Win rate(30d) vs lifetime | Drop > 10pp | Signal may be decaying |
| **Signal Decay Half-Life** | Autocorrelation decay of alpha signal | < 5 days | Signal too short-lived |
| **Factor Exposure Drift** | Rolling beta to factors | Drift > 2σ | Strategy has drifted from intended exposure |

#### Secondary Metrics (Weekly Review)

| Metric | Calculation | Decay Threshold |
|--------|-------------|-----------------|
| **Trade Frequency Deviation** | trades(30d) / trades(lifetime) | > 1.5x or < 0.5x |
| **Average Trade PnL Decay** | avg_pnl(30d) / avg_pnl(lifetime) | < 0.5 |
| **Max Drawdown Duration** | Longest drawdown period | > 2x historical max |
| **Profit Factor Decay** | PF(60d) vs PF(lifetime) | Drop > 30% |
| **Capacity Utilization** | Actual trades / theoretical max | > 80% |

### 3.3 Our Current Monitoring (from deployment_runbook.md line 394)

```
Alert if rolling Sharpe < 0.5 (potential strategy decay)
```

**Gap:** This is a single metric. Industry practice requires a multi-metric decay detection framework.

### 3.4 Decay-Resistant Design Principles

From AQR's research and industry literature:
1. **Diversify across signals** — "The most effective trend-following programs diversify across signals" (AQR Key Design Choices)
2. **Diversify across asset classes** — including "harder-to-access alternative markets"
3. **Short/long-term signal combination** — combining different timeframes reduces decay correlation
4. **Adaptive weighting** — use regime detection to reweight signals dynamically (Chen & Kawashima 2026)
5. **Sequential testing** — filter signals efficiently to avoid deploying decaying signals (Stephan 2026)

---

## 4. Strategy Return Decomposition (Alpha vs Beta vs Carry)

### 4.1 Framework

From AQR's extensive factor research and industry practice:

**Total Return = Alpha + Beta + Carry + Residual**

| Component | Definition | Measurement | Our TSM Context |
|-----------|------------|-------------|-----------------|
| **Alpha** | Skill-based excess return | Residual after regressing on factors | Signal timing + sizing |
| **Beta** | Market exposure return | Factor loadings × factor returns | Vol-targeted market exposure |
| **Carry** | Yield/interest rate differential | Forward points vs spot | Swap/rollover differentials across 8 assets |
| **Residual** | Unexplained return | ε from factor model | Execution artifacts, costs |

### 4.2 Decomposition Method

**Step 1: Factor Regression**
```
R_strategy = α + β_equity × R_equity + β_bond × R_bond + β_commodity × R_commodity + β_FX × R_FX + β_carry × R_carry + ε
```

**Step 2: Attribute Each Component**
- **Beta contribution** = Σ(β_i × R_i) — what you get from market exposure
- **Carry contribution** = β_carry × R_carry — what you get from yield differentials
- **Alpha** = Total return - Beta contribution - Carry contribution
- **Alpha Sharpe** = Alpha / σ(alpha) — the skill-based risk-adjusted return

### 4.3 Critical Insight for Our TSM Strategy

Our TSM strategy is a **time-series momentum** strategy. Key decomposition findings from academic research:

1. **Time-series momentum has BOTH alpha and beta components** — it's not pure alpha
2. **Carry is a significant component** in multi-asset carry trades — our XAUUSD, EURUSD positions have meaningful carry differentials
3. **The "alpha" in trend following is often crisis alpha** — positive returns during market stress (AQR's "Diversifying Alternatives" paper confirms this)
4. **Vol-targeting masks the true beta** — our 10% vol target scales beta up/down, making decomposition trickier

### 4.4 What This Means for Validation

| Component | Backtest Assumption | Live Reality | Gap |
|-----------|-------------------|--------------|-----|
| **Beta** | Clean factor exposure | Slippage, partial fills | Small gap |
| **Carry** | Static swap rates | Dynamic, can spike | **Large gap** — swap rates change daily |
| **Alpha** | Historical signal quality | Signal decay, crowding | **Largest gap** |
| **Residual** | Modeled execution costs | Real slippage, market impact | Medium gap |

---

## 5. Strategy Portfolio Construction & Allocation

### 5.1 AQR's Framework for Multi-Strategy Allocation

From "Broad Strategic Asset Allocation" (AQR, 2024):
- "Alternatives earn themselves a sizable strategic allocation"
- Key: estimate risk/return characteristics realistically, model realistic constraints
- "Which alternatives deliver the biggest incremental benefit, and what is an appropriate strategic allocation?"

From "Was That Intentional? Ways to Improve Your Active Risk" (AQR, 2020):
- "Unintentional risks can be a large part of a portfolio's total active risk"
- "Even if these risks don't detract from performance, they still make an investor's odds of outperformance lower"
- "Reducing unintentional active risks may be among the clearest sources of 'low hanging fruit'"

From "Key Design Choices When Building a Risk-Mitigating Portfolio" (AQR, 2023):
- "Trend following deserves a prominent place in any serious risk-mitigation portfolio"
- "The most effective trend-following programs diversify across signals, combining both short-/long-term price and economic trend signals"
- "Across asset classes, including harder-to-access alternative markets"

### 5.2 Allocation Methods for Multiple Strategies

#### Method 1: Inverse-Volatility Weighting (What We Use)

```
w_i = (1/σ_i) / Σ(1/σ_j)
```

**Pros:** Simple, stable, no estimation of expected returns
**Cons:** Ignores correlation, can be suboptimal if strategies are highly correlated
**Our implementation:** Used for combining 20d + 120d lookbacks

#### Method 2: Risk Parity

```
w_i × β_i = constant across all strategies
```

**Pros:** Equal risk contribution from each strategy
**Cons:** Requires accurate beta estimation, can concentrate in low-vol strategies
**Best for:** Diversified multi-strategy portfolios

#### Method 3: Maximum Diversification

```
maximize Σ(w_i × σ_i) / σ_portfolio
```

**Pros:** Maximizes diversification ratio
**Cons:** Can be unstable, sensitive to correlation estimation

#### Method 4: Hierarchical Risk Parity (HRP)

**Pros:** No matrix inversion required, robust to estimation errors
**Cons:** More complex implementation
**Best for:** Portfolios with many strategies where correlation matrix is noisy

### 5.3 Practical Allocation Framework for quant_os

Given our 8-asset TSM strategy with dual lookbacks:

| Layer | What | Method | Rebalance |
|-------|------|--------|-----------|
| **Lookback combination** | 20d + 120d signals | Inverse-vol weighting | Weekly (at rebalance) |
| **Asset allocation** | 8 assets | Vol-targeted + position caps | Weekly |
| **Strategy-level** | TSM + future strategies | Risk parity or HRP | Monthly |
| **Portfolio-level** | Strategy + cash buffer | Target vol + max DD constraint | Quarterly |

### 5.4 Portfolio Construction Best Practices

From AQR's research and industry consensus:

1. **Decouple alpha and beta** — use portable alpha structures (AQR "Diversifiers Forever")
2. **Risk-budget, not dollar-budget** — allocate risk, not capital
3. **Rebalance systematically** — calendar-based with tolerance bands
4. **Model realistic constraints** — transaction costs, capacity, liquidity
5. **Reduce unintentional active risk** — eliminate unintended exposures
6. **Diversify across signal types** — momentum + mean reversion + carry
7. **Diversify across timeframes** — short + medium + long-term signals
8. **Diversify across asset classes** — including alternative markets
9. **Account for correlation regime shifts** — correlation is not constant
10. **Stress-test the portfolio** — 2022 showed stock/bond correlation can flip

---

## 6. Validation Gap Analysis: Backtest vs Live

### 6.1 The Five Major Gaps

| # | Gap Category | Backtest Assumption | Live Reality | Severity |
|---|-------------|-------------------|--------------|----------|
| 1 | **Execution Quality** | Ideal fills at signal price | Slippage, partial fills, latency | HIGH |
| 2 | **Signal Decay** | Static historical signal quality | Signals degrade as they're discovered | CRITICAL |
| 3 | **Regime Assumption** | Returns are stationary | Returns are regime-dependent | HIGH |
| 4 | **Cost Estimation** | Fixed or static transaction costs | Dynamic costs (vol, liquidity dependent) | MEDIUM |
| 5 | **Capacity** | Unlimited capital | Market impact limits effective capacity | MEDIUM |

### 6.2 How Our Current System Addresses These Gaps

| Gap | Current Coverage | Status | Action Needed |
|-----|-----------------|--------|---------------|
| **Execution Quality** | Paper trading with ±20% slippage tolerance | PARTIAL | Add market impact model |
| **Signal Decay** | Rolling Sharpe < 0.5 alert | MINIMAL | Build multi-metric decay detector |
| **Regime Assumption** | Not implemented | MISSING | Add regime detection module |
| **Cost Estimation** | Cost model exists | GOOD | Validate against live data |
| **Capacity** | Not modeled | MISSING | Add capacity constraint |

### 6.3 AQR's 5-Step Validation Pipeline (Industry Best Practice)

From our vault research (deep_research_report.md line 143):
> "AQR Capital Management uses a 5-step validation pipeline: 1) in-sample, 2) OOS (temporal), 3) OOS (cross-sectional), 4) paper trading, 5) live. Each step has a statistical gate."

**Our current pipeline:**
- ✅ Phase 1-2: Backtest (in-sample)
- ✅ Phase 3: Walk-forward OOS (temporal)
- ⚠️ Phase 3: Deflated Sharpe + PBO (selection bias correction)
- ❌ Missing: Cross-sectional OOS validation
- ⚠️ Phase 4-5: Paper trading (4 weeks minimum)
- ❌ Missing: Statistical gates between phases

---

## 7. Actionable Recommendations for quant_os

### 7.1 Critical (Must Do Before Live)

| # | Recommendation | Priority | Effort | Impact |
|---|---------------|----------|--------|--------|
| 1 | **Extend paper trading to 12 weeks minimum** | CRITICAL | Low | High |
| 2 | **Add regime detection module** | CRITICAL | Medium | High |
| 3 | **Build multi-metric decay detector** | CRITICAL | Medium | High |
| 4 | **Add statistical gates between validation phases** | CRITICAL | Medium | Medium |

### 7.2 High Priority (Should Do)

| # | Recommendation | Priority | Effort | Impact |
|---|---------------|----------|--------|--------|
| 5 | **Implement return decomposition (alpha/beta/carry)** | HIGH | Medium | High |
| 6 | **Add cross-sectional OOS validation** | HIGH | Medium | Medium |
| 7 | **Build correlation regime monitoring** | HIGH | Low | High |
| 8 | **Add swap rate dynamic modeling** | HIGH | Medium | Medium |

### 7.3 Medium Priority (Nice to Have)

| # | Recommendation | Priority | Effort | Impact |
|---|---------------|----------|--------|--------|
| 9 | **Implement HRP for multi-strategy allocation** | MEDIUM | High | Medium |
| 10 | **Add capacity constraint modeling** | MEDIUM | Medium | Low |
| 11 | **Build adaptive signal reweighting** | MEDIUM | High | Medium |
| 12 | **Add stress-test suite (2022 scenario, carry crash)** | MEDIUM | Medium | Medium |

### 7.4 Implementation Roadmap

```
Phase 5A: Paper Trading Extension (Weeks 1-12)
  ├── Extend paper trade duration to 12 weeks
  ├── Add regime detection during paper trade
  ├── Monitor all decay metrics during paper trade
  └── Validate slippage + swap assumptions

Phase 5B: Monitoring Infrastructure (Weeks 1-8, parallel)
  ├── Build rolling Sharpe/IR/win-rate monitor
  ├── Build regime detection (vol, correlation, trend)
  ├── Build correlation regime dashboard
  └── Add swap rate dynamic tracking

Phase 6: Return Decomposition (Post-Paper)
  ├── Implement factor regression
  ├── Decompose returns into alpha/beta/carry
  ├── Validate alpha component is significant
  └── Set up ongoing decomposition reporting

Phase 7: Multi-Strategy Framework (Future)
  ├── Implement HRP for strategy allocation
  ├── Add capacity constraints
  ├── Build stress-test suite
  └── Implement adaptive signal reweighting
```

---

## Appendix A: Key AQR Papers Referenced

| Paper | Year | Key Insight |
|-------|------|-------------|
| **Active Extension** | 2025 | Long-short frameworks enhance active risk efficiency |
| **Diversifiers Forever** | 2025 | Diversification benefits compound over ultra-long horizons |
| **Diversifying Alternatives and the Rearview Mirror** | 2025 | Investor biases make diversifiers feel disappointing but they're vital |
| **Broad Strategic Asset Allocation** | 2024 | Alternatives earn sizable strategic allocation |
| **Key Design Choices When Building a Risk-Mitigating Portfolio** | 2023 | Trend following deserves prominent role in risk mitigation |
| **Was That Intentional? Ways to Improve Your Active Risk** | 2020 | Unintentional active risk reduces odds of outperformance |

## Appendix B: Vault Research Cross-References

| Document | Section | Relevance |
|----------|---------|-----------|
| EDGE_DETECTION_DEEP_RESEARCH.md | §3 Alpha Decay | Decay theory + 7 sources |
| EDGE_DETECTION_DEEP_RESEARCH.md | §6 Regime-Dependent Edge | Regime-dependent alpha |
| deployment_runbook.md | §1 Pre-Deployment Checklist | Paper trading gates |
| deployment_runbook.md | §4 Escalation | Decay-based halt logic |
| deep_research_report.md | Line 143 | AQR 5-step pipeline |
| broker_verification_report.md | Line 357 | 8-12 week paper trade recommendation |
| pre_register_b2.md | Line 24 | Current 28-day requirement |

## Appendix C: Risk Metrics Dashboard Template

```
DAILY MONITORING:
  - Rolling Sharpe (60d): ___ [Alert: < 0.5]
  - Rolling IR (60d): ___ [Alert: < 0.3]
  - Win Rate (30d): ___% [Alert: Drop > 10pp]
  - Avg Trade PnL (30d): ___ [Alert: < 50% lifetime]
  - Profit Factor (60d): ___ [Alert: Drop > 30%]

WEEKLY MONITORING:
  - Regime Indicator: [Low Vol | Normal | High Vol | Crisis]
  - Cross-Asset Correlation: ___ [Alert: > 0.7]
  - Signal Divergence Duration: ___ days [Alert: > 15]
  - Trade Frequency Ratio: ___ [Alert: > 1.5x or < 0.5x]
  - Factor Exposure Drift: ___σ [Alert: > 2σ]

MONTHLY MONITORING:
  - Return Decomposition: Alpha ___% | Beta ___% | Carry ___% | Residual ___%
  - Drawdown Duration: ___ days [Alert: > 2x historical max]
  - Capacity Utilization: ___% [Alert: > 80%]
  - Correlation Regime: [Normal | Elevated | Crisis]
```
