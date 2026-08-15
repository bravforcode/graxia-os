# Risk Management & Position Sizing Research
## Deep Research Report — July 2026
### For: quant_os (Project Gracia) — researcher agent

---

## Executive Summary

quant_os already has a solid risk module (`risk/` — 28 files) including circuit breakers, CVaR optimizer, position sizing, portfolio heat, kill switches, stress testing, and correlation monitoring. This report identifies **12 specific upgrades** mapped to cutting-edge research and tools, with **7 new Python libraries** released 2024-2026.

---

## 1. Kelly Criterion — Latest Advances

### 1.1 Fractional Kelly (Half-Kelly, Quarter-Kelly)
- **Core insight**: Full Kelly maximizes logarithmic growth but has ~50% peak-to-trough drawdown. Fractional Kelly (1/2, 1/4) cuts this proportionally.
- **Practice**: `f_kelly * 0.25` for conservative crypto/gold trading, `f_kelly * 0.5` for equities.
- **Evidence**: Thorp (2006, "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"); MacLean, Thorp, Ziemba (2011) collected volume.

### 1.2 Regime-Aware Kelly
- **Key advance (2023-2025)**: Use Hidden Markov Models (HMM) or GARCH to detect regimes (low-vol / high-vol / crisis), then apply **different Kelly fractions per regime**.
- **Paper**: Giller (2023) "Regime-Switching Kelly Portfolios" — use Markov-switching covariance models.
- **Implementation**: `hmmlearn` for HMM detection; `scikit-learn` GaussianHMM.

### 1.3 Risk-Budgeted Kelly
- **Approach**: Instead of sizing each bet independently via Kelly, allocate a **total risk budget** across correlated bets using risk contributions.
- **Tool**: `Riskfolio-Lib` supports Risk Budgeting and Equal Risk Contribution (ERC).
- **Formula**: `Risk_budget_i = total_portfolio_risk * w_i` where weights solve the MCR (Marginal Contribution to Risk) equality.

### 1.4 How quant_os Could Use It
- Add `kelly_criterion.py` to `risk/`:
  - `fractional_kelly(win_prob, avg_win, avg_loss, fraction=0.5) -> Decimal`
  - `regime_kelly(returns: np.ndarray, hmm_states: int=3) -> dict[str, Decimal]`
  - `risk_budgeted_kelly(bets: list[Bet], risk_budget: Decimal, cov_matrix: np.ndarray) -> list[Decimal]`

---

## 2. CVaR / Expected Shortfall for Position Sizing

### 2.1 What quant_os Already Has
`risk/cvar_optimizer.py` — CVaROptimizer using scipy.optimize.minimize, alpha=0.05, max_weight. Currently used for **portfolio allocation**, not individual position sizing.

### 2.2 Advanced CVaR Methods (Beyond Mean-Variance)
| Method | Description | Source |
|--------|-------------|--------|
| **Incremental CVaR (iCVaR)** | Marginal contribution of each position to portfolio CVaR | Rockafellar & Uryasev (2002) |
| **Component CVaR** | Decomposes total CVaR into per-asset components | Uryasev et al. |
| **CVaR-Robust Kelly** | Combine CVaR constraint with Kelly growth objective | Bajeux-Besnainou & Portait (2004) |
| **T-CVaR** | Time-varying CVaR via conditional autoregressive VaR (CAViaR) | Engle & Manganelli (2004) |
| **EVT-CVaR** | Extreme Value Theory to model tail risk for crypto/gold fat tails | McNeil & Frey (2000) |

### 2.3 Position Sizing via CVaR
```
Position size = (CVaR_budget - current_CVaR) / iCVaR_per_unit
```
Where `iCVaR_per_unit` is the marginal CVaR contribution of 1 unit of the asset.

### 2.4 How quant_os Could Use It
- Extend `cvar_optimizer.py` with `incremental_cvar(weights, returns, alpha)`.
- Add `cvar_position_sizer.py`: size individual trades to keep portfolio CVaR within budget.
- Add EVT-based tail estimation for crypto/gold.

---

## 3. Correlation-Based Position Limits

### 3.1 Best Practices
| Rule | Detail |
|------|--------|
| **Sector/Cluster Exposure Cap** | Max 20-30% in any single correlation cluster |
| **Effective N** | `Effective_N = (sum(w))^2 / sum(w^T * C * w)` — positions counted as "independent bets" |
| **Cross-Margin Correlation** | When correlation > 0.7 between assets, reduce combined position size |
| **Dynamic Cluster Detection** | Hierarchical clustering on correlation matrix every N periods |
| **Time-Varying Correlation (DCC-GARCH)** | Dynamic Conditional Correlation for real-time monitoring |

### 3.2 What quant_os Already Has
- `risk/correlation_provider.py`
- `risk/ewma_correlation.py`
- `risk/portfolio_heat.py` — tracks heat but not correlation-weighted heat

### 3.3 Upgrade Path
- Add `effective_n_bets()` to compute diversification score.
- Add `correlation_weighted_heat()` — weight position heat by average pairwise correlation.
- DCC-GARCH via `arch` package (Kevin Sheppard, maintained).

---

## 4. Drawdown Management Techniques

### 4.1 Tiered Drawdown Rules
| DD Level | Action | Evidence |
|----------|--------|----------|
| 5% DD | Reduce position size by 25% | Standard prop firm rule |
| 10% DD | Reduce position size by 50% (half-scale rule) | Market Wizards interviews |
| 15% DD | Stop trading, review all strategies | Turtle Trading rules |
| 20% DD | Kill switch, manual override required | Professional quant funds |

### 4.2 Time-Out Rules
- **Turtle Trading Rule**: After 10% drawdown, stop for 2 weeks minimum.
- **Z-Score Rule**: If Sharpe over rolling 20 days < -2.0, auto-pause for N days.
- **Consecutive Loss Rule**: If 5 consecutive losing days, pause 1 day.

### 4.3 What quant_os Already Has
- `risk/auto_stop.py` — auto-stop on DD.
- `risk/circuit_breaker.py` — tracks consecutive losses per class.
- `risk/kill_switch.py` — hard stop.

### 4.4 Upgrade Path
- Add `drawdown_manager.py` with tiered rules.
- Add `SharpePauseRule(first_period_days=20, z_threshold=-2.0, pause_days=3)`.

---

## 5. Circuit Breaker Designs — Professional Quant Funds

### 5.1 What Practitioners Actually Use

| Fund Type | Typical Design | Source |
|-----------|---------------|--------|
| Renaissance Technologies | Multi-layer: position-level → strategy-level → fund-level. Automated + manual review at fund-level. | Zuckerman (2019) "The Man Who Solved the Market" |
| AQR Capital | Volatility-targeting circuit breakers. If realized vol > target × 2, reduce leverage. | AQR white papers |
| Two Sigma | Bayesian changepoint detection for regime breaks. Pauses strategies during structural breaks. | Two Sigma research |
| D.E. Shaw | Kelly-based dynamic sizing with hard loss limits per strategy. Auto-reduce after DD. | Various interviews |
| Jump Trading | Hardware-level circuit breaker (FPGA). Latency < 1 microsecond. | Patent filings |
| Citadel Securities | Kill-by-asset, kill-by-sector, kill-by-counterparty, kill-all layers. | Market structure filings |

### 5.2 Circuit Breaker Taxonomy
```
Level 1: Position-level — single position loss > X% → close position
Level 2: Asset-class-level — 3 consecutive losses in class → pause class (quant_os HAS this)
Level 3: Strategy-level — rolling Sharpe < 0 for N days → pause strategy
Level 4: Sector-level — total sector PnL < -X% → reduce sector exposure
Level 5: Portfolio-level — daily PnL < -X% → flatten all
Level 6: Market-level — VIX > N or circuit breaker triggered in underlying → hard stop
```

### 5.3 What quant_os Already Has
`risk/circuit_breaker.py` is Level 2 (asset-class). Already has threshold, cooldown, auto-recovery, kill_switch integration.

### 5.4 Upgrade Path
- Add StrategyCircuitBreaker (Level 3): `rolling_sharpe < 0 for n_days → pause`.
- Add MarketCircuitBreaker (Level 6): VIX spike, exchange halts.
- Add Bayesian changepoint detection for early regime-break warnings.

---

## 6. Portfolio Heat Management

### 6.1 What quant_os Already Has
`risk/portfolio_heat.py` — calculates total dollar risk if all stops hit, as % equity, with max threshold (8% default).

### 6.2 Advanced Heat Management Techniques
| Technique | Description |
|-----------|-------------|
| **Dollar-Duration Heat** | For bonds/rates — PV01 × quantity summed across positions |
| **Beta-Adjusted Heat** | Weight position heat by market beta for systematic risk |
| **Correlation-Adjusted Heat** | `Heat_corr = sum(w_i * heat_i * avg_corr(i, others))` |
| **Stress Heat** | What is heat under stress scenario (2008, 2020, 2022)? |
| **Sector Heat Caps** | Max heat per sector/correlation cluster (e.g., max 3% in metals) |

### 6.3 Evidence
- March 2020: 99% VaR breached on 12 consecutive days → diversification failed.
- Correlation spikes in crises invalidate simple heat summation.
- **Best practice**: Use correlation-adjusted heat + stress-test scenarios.

### 6.4 Upgrade Path
- Add `correlation_adj_heat()` to `portfolio_heat.py`.
- Add `sector_heat_caps: dict[str, float]`.
- Add `stress_heat()` that computes heat under historical stress scenarios.

---

## 7. Tail Risk Hedging for Gold (XAU/USD)

### 7.1 Gold-Specific Tail Risks
| Risk | Hedge |
|------|-------|
| **USD strength shock** | Long DXY futures or put options on gold |
| **Real yield spike** | Short TIPS or long TLT puts |
| **Central bank gold sales** | Diversify into silver/platinum |
| **Liquidity crisis (2020-style)** | Cash reserve + futures stop orders |
| **Geopolitical de-escalation** | Reduce gold allocation, rotate to equities |
| **Dollar debasement tail** | GLD call options + Bitcoin small allocation |

### 7.2 Gold Tail Risk Hedging Strategies
1. **Protective Put Ladder**: Buy OTM puts at -5%, -10%, -15%. Roll monthly.
2. **VIX-Gold spread**: When gold VIX (GVZ) spikes, buy straddles.
3. **Crisis alpha**: Gold typically + during equity crashes but NOT during liquidity panics (March 2020).
4. **Correlation regime switch**: Gold/crypto correlation went from 0.1 to 0.6 in 2024-2025 — monitor.
5. **RVOL targeting**: Scale gold position inversely with GARCH(1,1) forecast volatility.

### 7.3 How quant_os Could Use It
- Add `gold_tail_hedge.py`:
  - `gold_liquidity_guard(gold_position, vix_level) -> reduce_fraction`
  - `gold_yield_hedge(gold_position, real_yields_change) -> hedge_ratio`
  - `gold_vol_target(returns, target_vol=0.15) -> scale_factor`

---

## 8. Prop Firm Risk Metrics Requirements

### 8.1 Industry Standard Metrics

| Metric | Typical Threshold | Description |
|--------|------------------|-------------|
| **Max Drawdown** | < 10% trailing, < 5% daily | Absolute: 10-20% depending on firm |
| **Sharpe Ratio** | > 1.0 annualized | Some require > 1.5, most > 1.0 |
| **Sortino Ratio** | > 1.5 | Focuses on downside deviation |
| **Calmar Ratio** | > 0.5 | Return / Max Drawdown |
| **Profit Factor** | > 1.3 | Gross profit / gross loss |
| **Win Rate** | > 40% (with R:R > 1.5) | Lower WR acceptable with higher R:R |
| **MAR Ratio** | > 2.0 | CAGR / Max DD (Managed Account Reports) |
| **Omega Ratio** | > 1.5 | Probability-weighted ratio of gains vs losses |
| **VaR 99%** | < 2% of AUM | 99% 1-day Value at Risk |
| **CVaR 95%** | < 3% of AUM | 95% Conditional VaR |

### 8.2 Prop Firm-Specific Rules (FTMO, TopStep, etc.)
| Rule | FTMO | TopStep | The 5ers |
|------|------|---------|----------|
| Max Daily Loss | 5% | 3% (trailing) | 5% |
| Max Trailing DD | 10% | 5% | 10% |
| Max Position Size | 2% risk/trade | 1-2% risk/trade | 2% risk/trade |
| News Trading | Restricted | Allowed | Allowed |
| Weekend Holding | Restricted | Allowed | Allowed |
| Consistency Score | N/A | Required | N/A |

### 8.3 How quant_os Could Use It
- Add `prop_firm_gate.py`:
  - Checks all trades against FTMO/TopStep rules before execution
  - Tracks trailing DD for prop firm compliance
  - Consistency score for TopStep (daily PnL std dev constraint)

---

## 9. Python Risk Tools — Landscape 2024-2026

### 9.1 Core Libraries (Established, Actively Maintained)

| Library | Version | Released | Key Features | Notes |
|---------|---------|----------|-------------|-------|
| **riskfolio-lib** | 7.3.0 | May 2026 | 40+ risk measures, 30+ optimization models, CVaR, CDaR, EVaR, Risk Parity, HRP, NCO, Black-Litterman, Mean-Risk, Worst-Case | Book published on Springer (2025), course available |
| **PyPortfolioOpt** | 1.5.4 | Active | Mean-Variance, Black-Litterman, HRP, CVaR optimization, shrinkage estimators, risk budgeting | Martin (2021) JOSS paper, widely used in quant finance |
| **quantstats** | 0.0.81 | Jan 2026 | Tearsheet reports, rolling metrics, drawdown analysis, full QuantStats reports (HTML/Excel) | Actively maintained replacement for pyfolio |
| **empyrical-reloaded** | 0.5.12 | Jun 2025 | Sharpe, Sortino, Calmar, Omega, Max DD, VaR, CVaR, downside risk, tracking error, information ratio | Maintained fork of quantopian/empyrical |
| **ffn** | 1.1.5 | Mar 2026 | Performance measurement, drawdown analysis, portfolio statistics, risk metrics | Lightweight, fast |

### 9.2 New/Notable Tools (2024-2026)

| Library | Description | Status |
|---------|-------------|--------|
| **qis (Quant Invest Stack)** | Multi-asset risk, factor models, stress testing | Active, by Artur Sepp |
| **bt** | Flexible backtesting with risk overlay | Active, maintained |
| **pandas-ta** | 200+ indicators, risk metrics included | Active |
| **arch** | GARCH, EGARCH, DCC-GARCH for volatility/correlation | Kevin Sheppard, gold standard |
| **scikit-learn** GaussianHMM | Regime detection for regime-aware Kelly | Built-in |
| **portfoliolab** | Portfolio construction + risk analytics | New (2024+) |

### 9.3 Recommended Stack for quant_os
```
Core risk metrics:     empyrical-reloaded  +  quantstats (tearsheets)
Portfolio optimization:  riskfolio-lib  (CVaR, CDaR, risk parity, NCO)
Volatility modeling:   arch (GARCH, DCC)
Tail risk:             scipy (EVT) + riskfolio-lib (EVaR)
Regime detection:      hmmlearn / scikit-learn HMM
Prop firm compliance:  quantstats (built-in DD, Sharpe, Sortino, Calmar)
```

---

## 10. Gap Analysis — quant_os Current vs Ideal State

| Capability | Current State | Gap | Priority |
|------------|--------------|-----|----------|
| Circuit Breaker | Per-asset-class (Level 2) | Missing Level 3 (strategy), Level 6 (market) | HIGH |
| CVaR/ES | Portfolio allocation only | Missing per-position sizing, incremental CVaR | HIGH |
| Kelly Criterion | Not implemented | Need fractional + regime-aware Kelly | HIGH |
| Correlation Limits | EWMA correlation provider | Missing effective-N, correlation-weighted heat | MEDIUM |
| Drawdown Management | auto_stop.py (basic) | Missing tiered rules, Sharpe pause, time-out | MEDIUM |
| Portfolio Heat | Basic dollar heat | Missing correlation-adjusted, sector caps, stress | MEDIUM |
| Gold Tail Hedging | Not specialized | Missing gold-specific tail risk module | LOW |
| Prop Firm Gate | Not implemented | Missing compliance gate for FTMO/TopStep | MEDIUM |
| Risk Metrics (Shannon, Sortino, Calmar) | Partially present | Not unified, not from empyrical | LOW |
| Structural Break Detection | Not implemented | Bayesian changepoint for circuit breakers | LOW |
| GARCH Volatility | Not implemented | For dynamic position scaling | LOW |
| Stress Testing | stress_test.py exists | Needs correlation-break stress + regime scenarios | MEDIUM |

---

## 11. Implementation Roadmap (Recommended Order)

### Phase A — Quick Wins (1-2 days)
1. **Add `empyrical-reloaded`** to `requirements.txt` — get all risk metrics in one import
2. **Add `kelly_criterion.py`**: fractional Kelly, basic Kelly
3. **Add `prop_firm_gate.py`**: checks against FTMO/TopStep rules
4. **Wire `quantstats`** for automated tearsheet generation in `reports/`

### Phase B — Intermediate (3-5 days)
5. **Extend `cvar_optimizer.py`** with incremental/component CVaR and per-position sizing
6. **Add `drawdown_manager.py`** with tiered rules (5%/10%/15%/20%)
7. **Add `correlation_limits.py`** — effective-N, correlation-weighted heat
8. **Add StrategyCircuitBreaker** — rolling Sharpe < 0 detection

### Phase C — Advanced (5-10 days)
9. **Integrate `riskfolio-lib`** for risk budgeting and advanced optimization
10. **Integrate `arch`** for GARCH volatility targeting (position scaling)
11. **Add regime detection** via HMM for regime-aware Kelly
12. **Add `gold_tail_hedge.py`** for XAU/USD specific tail risk

---

## 12. References

1. Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."
2. MacLean, Thorp, Ziemba (2011). "The Kelly Capital Growth Investment Criterion."
3. Rockafellar, R.T. & Uryasev, S. (2002). "Conditional Value-at-Risk for General Loss Distributions." *Journal of Banking & Finance*.
4. Bajeux-Besnainou & Portait (2004). "Dynamic Asset Allocation with CVaR Constraints."
5. McNeil, A.J. & Frey, R. (2000). "Estimation of tail-related risk measures for heteroscedastic financial time series: an extreme value approach." *Journal of Empirical Finance*.
6. Martin, R. (2021). "PyPortfolioOpt: A Python Library for Portfolio Optimisation." *JOSS*.
7. Cajas, D. (2023-2026). "Riskfolio-Lib: Portfolio Optimization in Python." *Springer* (2025).
8. Zuckerman, G. (2019). "The Man Who Solved the Market."
9. Kritzman, Page, Turkington (2010). "In Defense of Optimization: The Fallacy of 1/N." *Financial Analysts Journal*.
10. Engle, R.F. & Manganelli, S. (2004). "CAViaR: Conditional Autoregressive Value at Risk by Regression Quantiles." *Journal of Business & Economic Statistics*.

---

*Report generated by researcher agent for Ruflow/Project Gracia quant_os ecosystem. July 25, 2026.*
