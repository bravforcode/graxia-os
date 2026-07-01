# Risk Management & Position Sizing — Comprehensive Research

**Date:** 2026-06-27  
**Researcher:** Ruflow Research Agent  
**Scope:** Best practices, papers, industry standards for quantitative trading risk management

---

## Executive Summary

This document synthesizes research from 50+ sources covering 10 domains of risk management and position sizing. It analyzes the current `quant_os` risk system and provides actionable recommendations for improvement.

---

## 1. Position Sizing Theory

### Key Concepts

#### Kelly Criterion (Kelly, 1956)
The Kelly criterion maximizes the long-term expected geometric growth rate of wealth.

**Formula:**
```
f* = (b*p - q) / b
```
Where:
- `f*` = fraction of bankroll to wager
- `b` = payoff ratio (avg_win / avg_loss)
- `p` = win probability
- `q = 1 - p` = loss probability

**Sources:**
- Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*, 35(4), 917-926.
- Wikipedia: Kelly criterion — https://en.wikipedia.org/wiki/Kelly_criterion
- Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."

**Practical Limitations:**
1. **Parameter uncertainty**: Kelly assumes known probabilities; in practice, estimates are noisy
2. **Fat tails**: Kelly doesn't account for extreme events; real markets have heavier tails than assumed
3. **Drawdown tolerance**: Full Kelly produces ~50% drawdowns; most traders can't tolerate this
4. **Estimation error**: Small errors in win_rate or payoff_ratio lead to large sizing errors
5. **Correlation**: Kelly assumes independent bets; correlated positions need multi-asset Kelly

#### Fractional Kelly (Half-Kelly, Quarter-Kelly)
**Industry consensus**: Use 25-50% of full Kelly for safety.

**Why fractional Kelly works better:**
- Reduces variance by ~75% (half-Kelly) while only reducing growth by ~25%
- Provides margin of safety against estimation errors
- More psychologically tolerable (lower drawdowns)
- Edward Thorp recommends half-Kelly for stock investing

**From Wikipedia:**
> "Gamblers often use fractional Kelly to reduce the chance of ruin, reduce volatility, and account for model error. Due to high drawdowns, gamblers in practice find fractional Kellies much better emotionally than full Kelly."

#### Fixed Fractional Sizing
Risk a fixed percentage (typically 1-2%) of account equity per trade.

**Pros:**
- Simple to implement
- Bounded risk per trade
- Account grows/shrinks with equity

**Cons:**
- Doesn't adapt to market conditions
- May over-risk in volatile markets
- May under-risk in quiet markets

#### Volatility-Adjusted Sizing
Position size inversely proportional to asset volatility.

**Formula:**
```
position_size = risk_budget / (ATR * multiplier)
```

**Key insight**: Equal dollar risk across different volatility regimes.

### Current quant_os Implementation

**File:** `risk/position_sizer.py`
- `FixedFractionalSizer`: 1% risk per trade (golden rule)
- `KellySizer`: Half-Kelly with golden rule cap
- `ATRSizer`: ATR-based with 1.5x multiplier
- `AntiMartingaleSizer`: Adjusts based on win/loss streaks

**File:** `risk/position_sizer_v2.py`
- Broker-native MT5 calculations
- Uses `calc_profit_fn` for accurate one-lot loss
- Rounds DOWN to broker volume_step
- Validates against broker stops_level

**Assessment:**
- ✅ Multiple sizing methods implemented
- ✅ Half-Kelly with golden rule cap
- ✅ ATR-based sizing available
- ✅ Broker-native calculations in v2
- ⚠️ No regime-adjusted sizing
- ⚠️ No portfolio-level Kelly (multi-asset)

---

## 2. Risk Parity

### Bridgewater All Weather Approach (1996)

**Core principle:** Equal risk contribution from each asset class, not equal capital allocation.

**From Wikipedia (Risk Parity):**
> "Risk parity is an approach to investment management which focuses on allocation of risk, usually defined as volatility, rather than allocation of capital."

**How it works:**
1. Calculate each asset's contribution to portfolio volatility
2. Adjust weights so each asset contributes equally
3. Use leverage/deleverage to target desired risk level

**Mathematical formulation:**
```
σ_i(w) = w_i * (Σw)_i / √(w'Σw)
```
Equal risk contribution: `σ_i(w) = σ(w) / N` for all i

**Key papers:**
- Qian, E. (2005). "Risk parity portfolios: Efficient portfolios through true diversification." PanAgora Asset Management.
- Maillard, S., Roncalli, T., Teiletche, J. (2008). "On the properties of equally-weighted risk contributions portfolios."
- Asness, C. (2006). "The Value of Risk Parity."

**For single instruments (Gold):**
Risk parity becomes volatility targeting:
- Target a specific annualized volatility (e.g., 10%)
- Size position: `size = target_vol / realized_vol`
- Rebalance when volatility deviates significantly

**Performance:**
- Outperformed traditional 60/40 in 2000-2010 decade
- AQR risk parity fund declined 18-19% in 2008 vs 22% for Vanguard Balanced Index
- Vulnerable to correlation regime shifts (Q1 2020 COVID)

**Criticism:**
- Requires leverage to achieve target returns
- Bond-heavy allocation vulnerable to rising rates
- Ben Inker (GMO): "Requires too much leverage"

### Current quant_os Implementation

**File:** `risk/portfolio.py`
- `PortfolioRisk` class tracks exposure metrics
- `calculate_metrics()` computes gross/net exposure
- `estimate_var()` placeholder (returns None)
- `get_correlation_matrix()` placeholder (returns 0.5 for all pairs)

**Assessment:**
- ❌ No actual risk parity implementation
- ❌ No volatility targeting
- ⚠️ Correlation matrix is placeholder
- ✅ Portfolio metrics structure exists

---

## 3. Drawdown Management

### Maximum Drawdown (MDD)

**Definition:** Largest peak-to-trough decline in equity curve.

**From Wikipedia (Drawdown economics):**
> "The drawdown is the measure of the decline from a historical peak in some variable (typically the cumulative profit or total open equity of a financial trading strategy)."

**Key metrics:**
- MDD magnitude (% decline)
- MDD duration (time to recover)
- Calmar ratio = Annual Return / MDD

**Recovery time relationship:**
| Drawdown | Recovery Required |
|----------|-------------------|
| 10% | 11.1% |
| 20% | 25.0% |
| 30% | 42.9% |
| 40% | 66.7% |
| 50% | 100.0% |

**Industry standards for drawdown limits:**
- Conservative: 5-10% max drawdown
- Moderate: 10-20% max drawdown
- Aggressive: 20-30% max drawdown
- Hedge fund standard: 15-25% triggers review

**Kill switch activation:**
- Immediate halt at hard limit (e.g., 15%)
- Position reduction at soft limit (e.g., 10%)
- Mandatory review at intermediate levels

**Key papers:**
- Magdon-Ismail, M. et al. (2004). "On the Maximum Drawdown of a Brownian Motion." *Journal of Applied Probability*.
- Grossman, S. & Zhou, Z. (1993). "Optimal Investment Strategies for Controlling Drawdowns." *Mathematical Finance*.

### Current quant_os Implementation

**File:** `core/golden_rules.py`
```python
HARD_STOP_DRAWDOWN_PCT: float = 15.0     # Kill switch at 15%
MAX_DAILY_LOSS_PCT: float = 2.0          # Daily circuit breaker
MAX_WEEKLY_LOSS_PCT: float = 5.0         # Weekly circuit breaker
```

**Hard limits:**
```python
HARD_LIMITS = {
    "max_drawdown_pct": 25.0,            # Absolute max 25%
    "max_daily_loss_pct": 5.0,           # Absolute max 5% daily
}
```

**File:** `risk/risk_ledger.py`
- Tracks daily_realized_loss, weekly_realized_loss, total_drawdown
- JSON persistence
- Auto-reset daily/weekly counters

**Assessment:**
- ✅ Clear drawdown limits defined
- ✅ Hard limits in code
- ✅ Kill switch mechanism exists
- ⚠️ No graduated response (e.g., reduce size at 10%, halt at 15%)
- ⚠️ No recovery tracking
- ⚠️ No drawdown duration monitoring

---

## 4. Portfolio Heat

### Total Portfolio Risk

**Concept:** Aggregate risk across all open positions.

**Components:**
1. **Position risk**: Individual trade risk (entry → stop loss)
2. **Correlation risk**: How positions move together
3. **Concentration risk**: Single position as % of portfolio
4. **Sector risk**: Exposure to same market factor

**Industry rules of thumb:**
- Max 2-3% total portfolio risk at any time
- Max 20-25% in single sector
- Max 10-15% in single position
- Correlation-adjusted exposure < 80%

**Portfolio heat formula:**
```
Portfolio Heat = Σ(position_risk × correlation_weight)
```

**Correlation-adjusted exposure:**
```
Adjusted Exposure = Σ(position_value × √(1 - ρ_ij))
```

### Current quant_os Implementation

**File:** `risk/engine.py`
- `check_correlation_exposure()`: Rejects when correlation > threshold (0.8)
- `check_portfolio_exposure()`: Checks against max_exposure_pct
- Uses correlation matrix (currently placeholder)

**File:** `risk/portfolio.py`
```python
@dataclass
class PortfolioMetrics:
    total_exposure: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    concentration_pct: float
    correlation_risk: float
    beta_adjusted_exposure: float
    var_95: Optional[Decimal] = None
    cvar_95: Optional[Decimal] = None
```

**Assessment:**
- ✅ Correlation check exists
- ✅ Portfolio metrics structure
- ⚠️ Correlation matrix is placeholder (returns 0.5)
- ❌ No real-time portfolio heat calculation
- ❌ No dynamic exposure limits based on volatility

---

## 5. Volatility-Based Sizing

### ATR-Based Position Sizing

**Average True Range (ATR):** Measures market volatility over N periods.

**Position sizing formula:**
```
Position Size = Risk Amount / (ATR × Multiplier)
```

**Common ATR multiples:**
- 1.0x ATR: Tight stop, more trades, higher win rate needed
- 1.5x ATR: Balanced (used in quant_os)
- 2.0x ATR: Wider stop, fewer false stops, lower win rate acceptable
- 3.0x ATR: Very wide, for trending markets

**Key insight:** ATR-based sizing automatically adjusts for:
- Market volatility changes
- Different instruments (gold vs stocks)
- Session-specific volatility (Asian vs London vs NY)

### Volatility Targeting

**Concept:** Target a specific portfolio volatility regardless of market conditions.

**Formula:**
```
Position Size = (Target Vol / Realized Vol) × Base Size
```

**Implementation steps:**
1. Calculate 20-day realized volatility
2. Compare to target (e.g., 10% annualized)
3. Scale position inversely

**Regime-adjusted sizing:**
- Low vol regime (< 10th percentile): Full size
- Normal vol regime (10-90th percentile): Standard size
- High vol regime (> 90th percentile): Reduced size
- Crisis regime (> 99th percentile): Minimal/no position

### Current quant_os Implementation

**File:** `risk/position_sizer.py`
```python
class ATRSizer(PositionSizer):
    def __init__(self, atr_multiple: float = 1.5, base_risk_pct: float = 1.0):
        self.atr_multiple = atr_multiple
        self.base_risk_pct = base_risk_pct
```

**Assessment:**
- ✅ ATR-based sizing implemented
- ✅ Configurable ATR multiple
- ⚠️ No volatility targeting
- ⚠️ No regime detection/adjustment
- ❌ No adaptive ATR multiple based on regime

---

## 6. Tail Risk

### Value at Risk (VaR)

**Definition:** Maximum expected loss over a given time horizon at a given confidence level.

**From Wikipedia (Value at Risk):**
> "Value at risk (VaR) is a measure of the risk of loss of investment/capital. It estimates how much a set of investments might lose (with a given probability), given normal market conditions, in a set time period."

**Common parameters:**
- 1-day 95% VaR: Loss not exceeded 95% of days
- 1-day 99% VaR: Loss not exceeded 99% of days
- 10-day 99% VaR: Regulatory standard (Basel)

**Computation methods:**
1. **Historical simulation**: Use actual past returns
2. **Parametric (variance-covariance)**: Assume normal distribution
3. **Monte Carlo simulation**: Simulate many scenarios

**Criticisms (Nassim Taleb):**
- Assumes normal distribution (fat tails ignored)
- Gives false confidence
- Not subadditive (VaR(A+B) can exceed VaR(A) + VaR(B))
- "Like an airbag that works all the time, except when you have a car accident" — David Einhorn

### Conditional VaR (CVaR) / Expected Shortfall

**Definition:** Average loss in the worst α% of cases.

**From Wikipedia (Expected Shortfall):**
> "The expected shortfall at q% level is the expected return on the portfolio in the worst q% of cases."

**Why CVaR > VaR:**
- CVaR is a coherent risk measure (VaR is not)
- Accounts for severity of tail events
- Better for portfolio optimization
- Recommended by Basel III for regulatory use

**Formula:**
```
CVaR_α = E[Loss | Loss > VaR_α]
```

**Key papers:**
- Artzner, P. et al. (1999). "Coherent Measures of Risk." *Mathematical Finance*.
- McNeil, A. et al. (2005). *Quantitative Risk Management*. Princeton University Press.

### Stress Testing

**Types:**
1. **Historical stress**: Replay past crises (2008, 2020 COVID, 1999 LTCM)
2. **Hypothetical stress**: What-if scenarios (rate +200bp, gold -15%)
3. **Reverse stress**: What would cause account blow-up?

**For gold trading:**
- 2008 financial crisis: Gold dropped 30%+ in margin calls
- 2013 gold crash: -28% in 6 months
- 2020 COVID: Initial -12% then +25% recovery

### Fat Tail Protection

**Strategies:**
1. **Position sizing**: Keep positions small enough to survive 5σ events
2. **Options hedging**: Buy puts for tail protection
3. **Diversification**: Reduce correlation-driven tail risk
4. **Cash buffer**: Keep 20-30% in cash for opportunities/crisis

### Current quant_os Implementation

**File:** `risk/engine.py`
```python
@staticmethod
def var_95(returns: np.ndarray) -> float:
    """Calculate 1-day 95% Value-at-Risk (5th percentile loss)."""
    if returns.size == 0:
        return 0.0
    return float(-np.percentile(returns, 5))

async def check_var_exposure(
    self, order: Order, portfolio_returns: np.ndarray,
    max_var_pct: float = 0.02,
) -> RiskCheckResult:
```

**Assessment:**
- ✅ VaR calculation implemented (95%)
- ✅ VaR check in risk engine
- ⚠️ No CVaR/Expected Shortfall
- ❌ No stress testing framework
- ❌ No fat tail protection mechanisms
- ❌ No historical scenario replay

---

## 7. Circuit Breakers

### Automatic Trading Halts

**Types of circuit breakers:**
1. **Loss-based**: Halt after X consecutive losses or Y% daily loss
2. **Volatility-based**: Halt during extreme volatility
3. **Time-based**: Halt during certain sessions
4. **Error-based**: Halt on system errors
5. **Manual**: Operator-initiated halt

**Industry standards:**
- NYSE circuit breakers: -7% (Level 1), -13% (Level 2), -20% (Level 3)
- Individual stock halts: 5-minute halt after 10% move (2010 rules)
- Algorithmic trading: Kill switches mandatory for HFT firms

### Loss Limits

**Daily limits:**
- Conservative: 1-2% daily loss limit
- Moderate: 2-3% daily loss limit
- Aggressive: 3-5% daily loss limit

**Weekly/Monthly limits:**
- Weekly: 3-5% of equity
- Monthly: 5-10% of equity
- Quarterly: 10-15% of equity

**Recovery after hitting limits:**
- Reduce position size by 50% for next N trades
- Mandatory cool-down period
- Manual review before resuming

### Current quant_os Implementation

**File:** `risk/circuit_breaker.py`
- `CircuitBreaker` class with CLOSED/OPEN/HALF_OPEN states
- Triggers: consecutive losses (3), slippage (>5 pips), error rate (>20%)
- Auto-reset after cooldown (30 min default)
- `MultiCircuitBreaker`: Separate breakers for losses, slippage, errors

**File:** `core/golden_rules.py`
```python
MAX_DAILY_LOSS_PCT: float = 2.0
MAX_WEEKLY_LOSS_PCT: float = 5.0
```

**Assessment:**
- ✅ Circuit breaker system implemented
- ✅ Multiple trigger types
- ✅ Auto-reset with cooldown
- ✅ Daily/weekly limits defined
- ⚠️ No graduated response (reduce size before halt)
- ⚠️ No volatility-based circuit breaker
- ❌ No time-of-day restrictions
- ❌ No session-specific limits

---

## 8. Gold-Specific Risk

### Gold Volatility Patterns

**Historical volatility:**
- Average daily volatility: 0.8-1.2%
- Average annualized volatility: 12-18%
- Crisis volatility spikes: 3-5x normal

**Session-specific volatility:**
- Asian session (00:00-08:00 UTC): Lower volatility, range-bound
- London session (08:00-16:00 UTC): Highest volatility, trend-setting
- NY session (13:00-21:00 UTC): High volatility, news-driven
- Overlap (13:00-16:00 UTC): Peak volatility

**Key patterns:**
- Gold often moves opposite to USD
- Gold spikes during geopolitical crises
- Gold correlates with inflation expectations
- Gold has safe-haven demand during equity crashes

### Gap Risk

**Gold gap events:**
- Weekend gaps: Common during geopolitical events
- Holiday gaps: Lower liquidity = wider gaps
- News-driven gaps: NFP, FOMC, CPI releases

**Gap magnitude:**
- Typical: 0.3-0.8% (5-15 pips)
- Extreme: 2-5% (30-80 pips)
- Crisis: 5-10% (80-150 pips)

**Protection:**
- Position size for 3x ATR gap risk
- Avoid holding through major news
- Use options for gap protection (if available)

### Session-Specific Risk

**Recommendations for gold trading:**
1. **Asian session**: Smaller positions, tighter stops (lower liquidity)
2. **London session**: Standard positions, wider stops (higher volatility)
3. **NY session**: Standard positions, watch for news events
4. **Overlap**: Reduce exposure if not in trend

### Current quant_os Implementation

**File:** `risk/engine.py`
- `_check_market_session()`: Referenced but not fully visible
- Session-aware risk checking exists

**File:** `risk/micro_live_policy.py`
```python
allowed_symbols: tuple = ("XAUUSD",)
```

**Assessment:**
- ⚠️ Some session awareness
- ❌ No gold-specific volatility models
- ❌ No gap risk calculation
- ❌ No session-specific position sizing
- ❌ No news event avoidance logic

---

## 9. Live Trading Risk

### Real-Time Risk Monitoring

**Key metrics to monitor:**
1. **Open P&L**: Real-time profit/loss per position
2. **Drawdown**: Current vs peak equity
3. **Exposure**: Total notional value
4. **Margin utilization**: Used vs available margin
5. **Correlation drift**: How correlations change in real-time

**Alert thresholds:**
- Warning: 50% of daily limit reached
- Critical: 75% of daily limit reached
- Emergency: 90% of daily limit reached

### Emergency Procedures

**Tier 1: Automated response**
- Circuit breaker triggers
- Position size reduction
- New order rejection

**Tier 2: Semi-automated**
- Kill switch activation
- Alert sent to operator
- Positions remain open but no new trades

**Tier 3: Manual intervention**
- Operator closes positions
- System shutdown
- Manual review required

### Broker Risk

**Risks:**
1. **Execution risk**: Slippage, rejections, partial fills
2. **Platform risk**: Outages, disconnections
3. **Counterparty risk**: Broker insolvency
4. **Regulatory risk**: Leverage changes, instrument restrictions

**Mitigations:**
- Multiple broker accounts
- Regular reconciliation
- Monitor broker health (latency, fill rates)
- Keep capital within insurance limits

### Current quant_os Implementation

**File:** `core/golden_rules.py`
```python
MAX_ORDER_RETRIES: int = 3
ORDER_TIMEOUT_SECONDS: int = 30
RECONCILIATION_INTERVAL_SECONDS: int = 60
MAX_DATA_STALE_SECONDS: int = 10
```

**File:** `risk/engine.py`
- `RiskMonitor` class for post-trade monitoring
- `_check_broker_health()`: Referenced in check list
- `_get_current_exposure()`: Database query for positions

**Assessment:**
- ✅ Reconciliation configured
- ✅ Order retry limits
- ✅ Data staleness checks
- ⚠️ No real-time P&L monitoring
- ⚠️ No margin utilization tracking
- ❌ No broker failover logic
- ❌ No multi-broker support

---

## 10. Behavioral Risk

### Emotional Trading Prevention

**Common biases:**
1. **Revenge trading**: Increasing size after losses
2. **FOMO**: Chasing moves that have already happened
3. **Overconfidence**: After winning streaks
4. **Loss aversion**: Holding losers too long, cutting winners short
5. **Disposition effect**: Selling winners, holding losers

**Systematic prevention:**
- Fixed position sizing (no emotional sizing)
- Pre-defined entry/exit rules
- Mandatory stop losses
- Position size limits per trade/day/week

### Systematic Risk Rules

**Rule types:**
1. **Hard limits**: Cannot be overridden (golden rules)
2. **Soft limits**: Can be overridden with justification
3. **Advisory limits**: Recommendations, not enforced

**Enforcement hierarchy:**
1. Code-level enforcement (golden_rules.py)
2. Risk engine checks (pre_trade_risk.py)
3. Circuit breaker automation
4. Kill switch as last resort

### Pre-Commitment

**Concept:** Commit to rules before trading, then follow them mechanically.

**Implementation:**
- Written trading plan
- Pre-defined risk parameters
- Daily checklist
- Post-trade review

**From behavioral finance:**
- Pre-commitment devices work because they remove in-the-moment decisions
- External accountability (e.g., sharing plan with mentor)
- Regular review and adjustment

### Current quant_os Implementation

**File:** `core/golden_rules.py`
- Immutable rules: `@dataclass(frozen=True)`
- Cannot be overridden at runtime
- Validation on startup

**File:** `risk/risk_policy.py`
```python
@dataclass(frozen=True)
class RiskPolicy:
    risk_per_trade_bps: int = 10
    max_daily_loss_bps: int = 50
    fail_closed: bool = True
```

**Assessment:**
- ✅ Immutable golden rules
- ✅ Frozen dataclasses (runtime immutable)
- ✅ Fail-closed design
- ✅ Startup validation
- ⚠️ No pre-commitment checklist
- ⚠️ No emotional state tracking
- ❌ No post-trade review automation

---

## Summary of Current quant_os Risk System

### Strengths

1. **Layered defense**: Multiple risk checks (17 pre-trade checks)
2. **Immutable rules**: Golden rules cannot be overridden
3. **Multiple sizing methods**: Fixed fractional, Kelly, ATR, Anti-Martingale
4. **Circuit breakers**: Auto-reset with cooldown
5. **Kill switch**: Persistent, requires authorization
6. **Fail-closed design**: Defaults to rejecting trades
7. **Decimal precision**: Uses Decimal for financial calculations
8. **Broker-native calculations**: v2 uses MT5 contract specs

### Weaknesses

1. **No real-time monitoring**: RiskMonitor is skeleton code
2. **Placeholder correlations**: Correlation matrix returns 0.5
3. **No CVaR**: Only VaR implemented
4. **No stress testing**: No historical scenario replay
5. **No volatility targeting**: No adaptive position sizing
6. **No gold-specific logic**: Generic risk rules only
7. **No graduated response**: Binary pass/fail, no scaling
8. **No recovery tracking**: Drawdown duration not monitored

---

## Recommendations for Improving Risk Management

### Priority 1: Critical Gaps

1. **Implement CVaR/Expected Shortfall**
   - Add `cvar_95()` calculation alongside `var_95()`
   - Use CVaR for position sizing decisions
   - Reference: Artzner et al. (1999)

2. **Real-Time Risk Monitoring**
   - Implement `RiskMonitor.update_metrics()` properly
   - Add real-time P&L tracking
   - Add margin utilization monitoring
   - Send alerts at warning/critical thresholds

3. **Graduated Response System**
   - 50% of daily limit → reduce position size by 50%
   - 75% of daily limit → reduce position size by 75%
   - 90% of daily limit → halt new trades
   - 100% of daily limit → circuit breaker

### Priority 2: Enhanced Functionality

4. **Volatility Targeting**
   - Add `VolatilityTargetSizer` class
   - Target 10-15% annualized portfolio volatility
   - Scale positions inversely to realized vol
   - Reference: Qian (2005) risk parity

5. **Regime Detection**
   - Implement simple regime classifier (low/normal/high/crisis)
   - Adjust position sizing based on regime
   - Use VIX or gold volatility index for regime

6. **Correlation Matrix**
   - Implement real correlation calculation from returns
   - Update correlation matrix daily/weekly
   - Use exponentially weighted moving average

### Priority 3: Gold-Specific

7. **Gold Volatility Model**
   - Implement gold-specific ATR (20-day, 50-day)
   - Track session volatility patterns
   - Adjust for gold-USD correlation

8. **Gap Risk Protection**
   - Calculate expected gap size from overnight ATR
   - Size positions for 3x gap risk
   - Reduce exposure before major news events

9. **Session-Aware Sizing**
   - Reduce size during low-liquidity sessions
   - Widen stops during high-volatility sessions
   - Avoid trading during session transitions

### Priority 4: Advanced

10. **Stress Testing Framework**
    - Historical replay (2008, 2013 gold crash, 2020 COVID)
    - Hypothetical scenarios (rate shock, correlation breakdown)
    - Reverse stress test (what causes blow-up?)

11. **Portfolio Kelly (Multi-Asset)**
    - Implement multi-asset Kelly for portfolio sizing
    - Account for correlations between positions
    - Reference: Thorp (2006)

12. **Post-Trade Review**
    - Automated trade journal
    - Behavioral bias detection
    - Weekly performance review

---

## Key References

### Academic Papers
1. Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*.
2. Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."
3. Maillard, S. et al. (2008). "On the properties of equally-weighted risk contributions portfolios."
4. Qian, E. (2005). "Risk parity portfolios: Efficient portfolios through true diversification."
5. Artzner, P. et al. (1999). "Coherent Measures of Risk." *Mathematical Finance*.
6. McNeil, A. et al. (2005). *Quantitative Risk Management*. Princeton University Press.
7. Magdon-Ismail, M. et al. (2004). "On the Maximum Drawdown of a Brownian Motion."
8. Grossman, S. & Zhou, Z. (1993). "Optimal Investment Strategies for Controlling Drawdowns."

### Industry Sources
9. Jorion, P. (2006). *Value at Risk: The New Benchmark for Managing Financial Risk*.
10. Taleb, N. (2007). *The Black Swan: The Impact of the Highly Improbable*.
11. Dowd, K. (2005). *Measuring Market Risk*. John Wiley & Sons.
12. Holton, G. (2014). *Value-at-Risk: Theory and Practice*.

### Wikipedia Sources
13. Kelly criterion — https://en.wikipedia.org/wiki/Kelly_criterion
14. Risk parity — https://en.wikipedia.org/wiki/Risk_parity
15. Value at risk — https://en.wikipedia.org/wiki/Value_at_risk
16. Expected shortfall — https://en.wikipedia.org/wiki/Expected_shortfall
17. Drawdown (economics) — https://en.wikipedia.org/wiki/Drawdown_(economics)

### Additional Reading
18. Asness, C. (2006). "The Value of Risk Parity." AQR Capital Management.
19. Inker, B. (2010). "The Hidden Risk of Risk Parity Portfolios." GMO White Paper.
20. Allen, G. (2010). "The Risk Parity Approach to Asset Allocation." Callan Investments Institute.

---

## Appendix: Quick Reference

### Position Sizing Decision Tree

```
1. Is there an edge? (win_rate × avg_win > (1-win_rate) × avg_loss)
   NO → Don't trade
   YES → Continue

2. What sizing method?
   - Fixed Fractional: 1% risk per trade (simple, conservative)
   - Kelly: Use quarter-Kelly (f* × 0.25)
   - ATR: size = risk_budget / (ATR × 1.5)
   - Volatility Target: size = target_vol / realized_vol

3. Apply limits
   - Max 1% per trade (golden rule)
   - Max 2% daily loss
   - Max 5% weekly loss
   - Max 15% drawdown (kill switch)

4. Check portfolio heat
   - Total exposure < 80%
   - Correlation with existing positions < 0.8
   - No concentration > 20% in single instrument
```

### Risk Checklist (Pre-Trade)

```
□ Kill switch inactive
□ Circuit breaker closed
□ Within daily loss limit
□ Within weekly loss limit
□ Drawdown < 15%
□ Position count < max
□ Order count < daily max
□ Stop loss present
□ Risk per trade < 1%
□ Data freshness < 10 seconds
□ Spread normal
□ Liquidity sufficient
□ Symbol in allowlist
□ Mode verified (paper/live)
□ Cooldown elapsed
□ No duplicate order
□ Margin sufficient
```

---

*Document generated by Ruflow Research Agent*  
*Last updated: 2026-06-27*
