# Trial #1029: Regime-Adaptive Multi-Asset Strategy

**Pre-Registration Date**: 2026-07-30
**Status**: PRE-REGISTERED (FROZEN)
**Trial Number**: 1029 (next available after 1028)

---

## 1. Economic Rationale

### Why This Is Structurally Different from All REJECTED Trials

All 6 rejected directions (A–F) failed because they were **single-asset momentum bets**:
- Trial #1001 (RYDC): Single-asset XAUUSD
- Trial #1003 (CAM): DXY→XAUUSD lead-lag (single pair)
- Trial #1005 (MRM): DFII10 regime→XAUUSD (single asset)
- Trial #1008 (CVR): Cross-asset vol rank (single direction)
- Trial #1028 (WS-A): TSMOM across 7 assets (still single-direction momentum)

**Root cause**: Single-asset signals are noise-dominated. When one asset is excluded, the "edge" disappears (jackknife proves this).

### The Regime-Adaptive Multi-Asset Hypothesis

**Claim**: Markets alternate between two regimes:
1. **Trending regime**: Cross-asset correlations are LOW (assets move independently). Momentum works.
2. **Crisis regime**: Cross-asset correlations are HIGH (everything moves together). Mean-reversion works.

**Mechanism**:
- Detect regime via cross-asset correlation matrix (not single-asset autocorrelation)
- Switch between momentum (trending) and mean-reversion (crisis) based on regime
- Apply to **multiple assets simultaneously** with equal-weight diversification

**Why this is different**:
1. Uses **cross-asset** regime detection (not single-asset)
2. Switches **strategy type** based on regime (not just position sizing)
3. Diversifies across **multiple assets** (not single-asset bets)
4. Structural (regime is slow-moving) not momentum (fast, noise-dominated)

---

## 2. Pre-Registered Parameters (FROZEN)

```python
@dataclass(frozen=True)
class RAMConfig:
    """Regime-Adaptive Multi-Asset configuration — frozen at pre-registration."""
    
    # Universe: 7 assets with sufficient history
    universe: tuple[str, ...] = (
        "XAUUSD",   # Gold
        "XAGUSD",   # Silver
        "EURUSD",   # Euro
        "GBPUSD",   # British Pound
        "USDJPY",   # Japanese Yen
        "NAS100",   # Nasdaq 100
        "US30",     # Dow Jones
    )
    
    # Regime detection parameters
    regime_lookback: int = 60          # Rolling correlation window (trading days)
    regime_crisis_threshold: float = 0.6  # Avg correlation > 0.6 = crisis regime
    regime_trend_threshold: float = 0.3   # Avg correlation < 0.3 = trending regime
    
    # Momentum parameters (used in trending regime)
    mom_lookback: int = 20             # Momentum lookback window
    mom_entry_z: float = 1.0           # Entry threshold (z-score)
    
    # Mean-reversion parameters (used in crisis regime)
    mr_lookback: int = 20              # Mean-reversion lookback window
    mr_entry_z: float = 2.0            # Entry threshold (z-score)
    
    # Risk management
    max_position_pct: float = 0.15     # Max 15% per asset
    stop_loss_atr: float = 2.0         # Stop loss at 2x ATR
    take_profit_atr: float = 3.0       # Take profit at 3x ATR
    
    # Data requirements
    min_history_days: int = 252         # Minimum 1 year of data
    bars_per_year: float = 252.0        # Daily bars
```

---

## 3. Signal Generation Logic

### Step 1: Regime Detection

```python
def detect_regime(returns_matrix: pd.DataFrame, lookback: int) -> pd.Series:
    """
    Detect regime from cross-asset correlation matrix.
    
    Args:
        returns_matrix: DataFrame of daily returns, columns = assets
        lookback: Rolling window for correlation calculation
    
    Returns:
        Series of regime labels: "trending", "crisis", or "neutral"
    """
    regimes = []
    
    for i in range(lookback, len(returns_matrix)):
        window = returns_matrix.iloc[i-lookback:i]
        
        # Compute rolling correlation matrix
        corr_matrix = window.corr()
        
        # Average off-diagonal correlation (excluding self-correlations)
        n = len(corr_matrix)
        off_diag = []
        for j in range(n):
            for k in range(j+1, n):
                off_diag.append(corr_matrix.iloc[j, k])
        
        avg_corr = np.mean(off_diag)
        
        # Classify regime
        if avg_corr > regime_crisis_threshold:
            regimes.append("crisis")
        elif avg_corr < regime_trend_threshold:
            regimes.append("trending")
        else:
            regimes.append("neutral")
    
    return pd.Series(regimes, index=returns_matrix.index[lookback:])
```

### Step 2: Strategy Selection

```python
def generate_signals(
    prices: pd.DataFrame,
    regime: pd.Series,
    config: RAMConfig,
) -> pd.DataFrame:
    """
    Generate signals based on regime.
    
    Trending regime: Momentum (buy winners, sell losers)
    Crisis regime: Mean-reversion (buy oversold, sell overbought)
    """
    signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
    
    for asset in prices.columns:
        returns = prices[asset].pct_change()
        
        for i in range(max(config.mom_lookback, config.mr_lookback), len(prices)):
            current_regime = regime.iloc[i-1]  # Use previous regime (no look-ahead)
            
            if current_regime == "trending":
                # Momentum: z-score of recent returns
                window = returns.iloc[i-config.mom_lookback:i]
                z = (returns.iloc[i] - window.mean()) / window.std()
                
                if z > config.mom_entry_z:
                    signals.iloc[i][asset] = 1  # Long
                elif z < -config.mom_entry_z:
                    signals.iloc[i][asset] = -1  # Short
                    
            elif current_regime == "crisis":
                # Mean-reversion: z-score of price deviation from mean
                window = prices[asset].iloc[i-config.mr_lookback:i]
                z = (prices[asset].iloc[i] - window.mean()) / window.std()
                
                if z < -config.mr_entry_z:
                    signals.iloc[i][asset] = 1  # Long (oversold)
                elif z > config.mr_entry_z:
                    signals.iloc[i][asset] = -1  # Short (overbought)
    
    return signals
```

### Step 3: Portfolio Construction

```python
def construct_portfolio(
    signals: pd.DataFrame,
    regime: pd.Series,
    config: RAMConfig,
) -> pd.DataFrame:
    """
    Equal-weight portfolio across all assets with positions.
    
    In trending regime: Only momentum positions
    In crisis regime: Only mean-reversion positions
    """
    portfolio = signals.copy()
    
    # Equal-weight across assets with positions
    for i in range(len(portfolio)):
        active = portfolio.iloc[i] != 0
        if active.sum() > 0:
            portfolio.iloc[i] = portfolio.iloc[i] / active.sum()
    
    # Apply position limits
    portfolio = portfolio.clip(-config.max_position_pct, config.max_position_pct)
    
    return portfolio
```

---

## 4. Validation Pipeline

### Gates (Same as All Other Trials)

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| Driscoll-Kraay t-stat | > 2.0 | Pooled significance across assets |
| Positive Sharpe count | ≥ 4 of 7 | Majority of assets must have positive Sharpe |
| Walk-forward efficiency | > 0.3 | OOS must retain ≥30% of IS performance |
| PBO/CSCV | < 0.5 | Less than 50% probability of overfitting |
| Cost stress 1.5x | Still positive | Robust to cost estimation errors |
| Max drawdown | < 25% | Survive worst-case scenario |

### Data Sources

| Asset | Data File | Rows | Date Range |
|-------|-----------|------|------------|
| XAUUSD | data/XAUUSD_D1.csv | 5,623 | ~2005-2026 |
| XAGUSD | data/XAGUSD_D1.csv | 5,098 | ~2005-2026 |
| EURUSD | data/EURUSD_D1.csv | 5,936 | ~2005-2026 |
| GBPUSD | data/GBPUSD_D1.csv | 5,932 | ~2005-2026 |
| USDJPY | data/USDJPY_D1.csv | 5,933 | ~2005-2026 |
| NAS100 | data/NAS100_D1.csv | 4,803 | ~2005-2026 |
| US30 | data/US30_D1.csv | 2,306 | ~2017-2026 |

### Cost Model

- Pepperstone Razor account
- Spread: Dynamic (from `dynamic_spread_model.py` with `spread_pips_override`)
- Commission: $3.50 per lot round-turn
- Slippage: 0.5 pips average

---

## 5. Expected Performance (Honest Assessment)

### Academic Benchmarks

| Metric | Academic Range | Our Target | Confidence |
|--------|---------------|------------|------------|
| Sharpe Ratio | 0.5–1.5 (regime-switching) | 0.8 | MEDIUM |
| Max Drawdown | 10–25% | < 20% | MEDIUM |
| Win Rate | 50–60% | 55% | LOW |
| Profit Factor | 1.2–1.8 | 1.3 | LOW |

### Risk Factors

1. **Regime detection lag**: Correlation regimes can change abruptly (March 2020). Our 60-day lookback may be too slow.
2. **Transaction costs**: Switching between momentum and mean-reversion generates trades. Costs could eat edge.
3. **Overfitting risk**: LOW — parameters are simple (z-scores, correlation thresholds) and structurally motivated.
4. **Data quality**: US30 only has 2,306 rows (2017-2026). May not capture full regime cycle.

### Prior Probability

Given that:
- All single-asset momentum strategies have been REJECTED
- Regime-switching has strong academic support
- Multi-asset diversification is structurally more robust
- Simple parameters reduce overfitting risk

**Estimated prior probability of passing all gates: 15–25%**

This is LOW but higher than the ~5% prior for single-asset strategies.

---

## 6. Implementation Plan

### Phase 1: Data Preparation (Day 1)
- [ ] Load all 7 D1 data files
- [ ] Align on common date range (2005-01-01 to 2026-01-01)
- [ ] Handle missing data (forward-fill, then drop)
- [ ] Compute daily returns for all assets

### Phase 2: Regime Detection (Day 1)
- [ ] Implement cross-asset correlation regime detector
- [ ] Validate on historical data (visual inspection)
- [ ] Check regime stability (how often does it switch?)

### Phase 3: Signal Generation (Day 2)
- [ ] Implement momentum signals (trending regime)
- [ ] Implement mean-reversion signals (crisis regime)
- [ ] Combine into unified signal matrix

### Phase 4: Backtesting (Day 2)
- [ ] Implement equal-weight portfolio construction
- [ ] Run backtest with transaction costs
- [ ] Compute performance metrics (Sharpe, drawdown, etc.)

### Phase 5: Validation (Day 3)
- [ ] Driscoll-Kraay t-stat
- [ ] Walk-forward analysis (3+ windows)
- [ ] PBO/CSCV analysis
- [ ] Cost stress testing (1.5x, 2.0x)
- [ ] Jackknife leave-one-out

### Phase 6: Documentation (Day 3)
- [ ] Write pre-registration document
- [ ] Update trial ledger
- [ ] Update hypothesis registry

---

## 7. Forbidden Actions

Per `research/generation_framework.md`:

- ❌ "Let me see what parameters fit best" = Search #1
- ❌ "Try opposite arm" without new pre-registration = PBO=0.5
- ❌ "Lower gate slightly" = invalid test
- ❌ "Just one more backtest" past 20 = cap is real
- ❌ "Peek at holdout" = opening IS the test

---

## 8. Stopping Rules

Per `research/trial_ledger.json`:

- **Trial cap**: 1022 reached. This is trial #1029 (post-cap, pre-approved).
- **Sacred holdout**: LOCKED (0 uses, 1 max). Phase 4.5 only.
- **Three-month deadline**: Phase 3 started 2026-07-13, deadline 2026-10-13.
- **80-hour cap**: Not yet tracked.
- **Three-in-a-row same gate**: Not yet triggered.

---

## 9. Evidence Requirements

Every claim must be backed by:
1. **Direct output** from backtest engine
2. **Statistical test** with p-value or confidence interval
3. **Cross-validation** (walk-forward, jackknife, or bootstrap)
4. **Cost stress** at 1.5x and 2.0x realistic costs

**No trust, no hype. No claims without evidence.**

---

## 10. Signatures

- **Pre-registered by**: Builder Agent
- **Date**: 2026-07-30
- **Trial number**: 1029
- **Status**: FROZEN (parameters cannot be changed after backtests are run)
