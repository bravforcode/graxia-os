# What Actually Works in Systematic Trading (2024-2026)

> Research compiled from Quantpedia, academic papers, DuckDuckGo indexed research, and Wikipedia HFT data.
> Focus: 15-instrument intraday system (8 FX, 2 crypto, 2 indices, 1 commodity, 1 metal).

---

## 1. Summary Ranking of Approaches

Ranked by **risk-adjusted returns (Sharpe) × robustness × implementability**:

| Rank | Approach | Exp. Sharpe | Annual Return | Volatility | Complexity | Capacity |
|------|----------|-------------|---------------|------------|------------|----------|
| 1 | **Time Series Momentum (Multi-Asset)** | 1.0-1.5 | 15-21% | 15-16% | Low | High |
| 2 | **Volatility Risk Premium (Options)** | 1.0-1.4 | 20-26% | 19% | High | Medium |
| 3 | **Pairs Trading (ETF/Country)** | 1.3-2.0 | 11-21% | 6-10% | Medium | Low |
| 4 | **Multi-Factor Composite (Carry+Mom+Value)** | 0.8-1.2 | 8-12% | 10% | Medium | High |
| 5 | **FX Carry Trade** | 0.7-0.9 | 5-7% | 8-10% | Low | High |
| 6 | **Mean Reversion (Futures/FX)** | 0.8-1.2 | 15-30% | 20-31% | Medium | Medium |
| 7 | **Dispersion Trading (Options)** | 1.0-1.1 | 15% | 14% | Very High | Low |
| 8 | **Market Making (HFT)** | 3.0-10.0+ | Variable | Very Low | Extreme | Low |
| 9 | **Cryptocurrency Seasonality** | 1.0-1.6 | 33% | 21% | Low | Very Low |

---

## 2. Detailed Analysis by Approach

### 2.1 Time Series Momentum (Multi-Asset) — **BEST FIT FOR THIS SYSTEM**

**Expected Sharpe**: 1.0-1.5
**Annual Return**: 15-21% (gross)
**Volatility**: 15-16%
**Rebalancing**: Monthly (weekly/daily variants exist)

**What it is**:
Long assets with positive excess returns over lookback window (typically 1M, 3M, 12M),
short assets with negative returns. No cross-sectional comparison needed —
each instrument traded independently based on its own signal.

**Key papers**: Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum" — Journal of Financial Economics.
Quantpedia strategy #0118: 20.70% annual return, 15.74% vol.

**Why it works**:
- Initial underreaction + delayed overreaction to news
- Herding behavior by investors
- Central bank policy persistence
- Works across ALL asset classes (equities, bonds, FX, commodities, crypto)

**Why it's #1 for this system**:
- Your 15 instruments span 5 asset classes — perfect diversification
- FX instruments benefit from carry + momentum overlap
- Monthly signals are robust to noise, intraday execution just needs entry timing
- Extremely low model complexity (just compute past returns)
- Survives transaction costs well (few signals per month)

**Implementation**:
```python
signal = (close[-1] / close[-lookback] - 1)  # e.g. lookback = 252 (1Y) or 63 (3M)
position = sign(signal) * risk_budget / atr
```

**Risk management**: Target 15% vol per instrument, equal risk-weight across instruments, cap gross exposure at 200%.

---

### 2.2 FX Carry Trade

**Expected Sharpe**: 0.7-0.9
**Annual Return**: 5-8% (unlevered)
**Volatility**: 8-10%

**What it is**: Buy high-interest-rate currencies, sell low-interest-rate currencies.
Quantpedia #0005: 7.27% return, 9.60% vol. Dollar Carry (#0129): 5.60% return, 8.53% vol.

**Current state (2024-2026)**: Still profitable but regime-dependent.
- Works best in low-vol, risk-on environments
- Suffers severe drawdowns in risk-off (funding currency appreciation)
- 2022-2023 was terrible due to rate hiking cycle
- 2024-2025 showing recovery as rate differentials normalize

**Why it works**:
- Risk premium for bearing crash risk
- Capital flow persistence
- Forward rate bias (forward rates systematically overstate future spot rates)

**For your system**: Long AUD/USD, NZD/USD vs short USD/JPY, USD/CHF.
Combine with momentum filter (only carry-trade when momentum also positive)
to avoid "carry crash" drawdowns.

---

### 2.3 Value Factor in FX (PPP)

**Expected Sharpe**: 0.6-0.85
**Annual Return**: 7-8%
**Volatility**: 9-10%

Quantpedia #0009: 7.82% return, 9.33% vol.

**What it is**: Buy undervalued currencies (per PPP), sell overvalued.
Uses OECD PPP measures or Big Mac index for valuation signal.
Mean-reverts over 3-5 year horizons.

**For your system**: Supplementary signal. Combine with momentum for timing entry.

---

### 2.4 Currency Momentum Factor

**Expected Sharpe**: 0.7-0.8
**Annual Return**: 7-8%
**Volatility**: 10%

Quantpedia #0008: 7.61% return, 10.22% vol.

Cross-sectional: long top 3 FX, short bottom 3 FX by past returns.

---

### 2.5 Statistical Arbitrage / Pairs Trading

**Expected Sharpe**: 1.3-2.0
**Annual Return**: 11-21%
**Volatility**: 6-10%

**Evidence**:
- Yale Dept Economics (2024): Pairs trading Sharpe 1.35, excess return 6.2% annual
- Quantpedia #0012 (Stocks): 11.16% return, 5.85% vol → Sharpe ~1.91
- Quantpedia #0055 (Country ETFs): 20.60% return, 10.00% vol → Sharpe ~2.06

**For FX**: Look for cointegrated pairs:
- EUR/USD ↔ GBP/USD (highly correlated)
- AUD/USD ↔ NZD/USD (commodity currency pair)
- USD/CAD ↔ WTI oil proxy

**Implementation**: Johansen cointegration test on rolling 252-day window,
trade when spread > 2σ from mean, exit at 0.5σ.

**Caveat**: Cointegration relationships can break down. Needs continuous monitoring.
Transaction costs matter significantly (spread × 2 per round trip).

---

### 2.6 Volatility Risk Premium

**Expected Sharpe**: 1.0-1.4
**Annual Return**: 20-26%
**Volatility**: 19%

Quantpedia #0020: 26.00% return, 19.00% vol.

**What it is**: Sell options systematically — implied volatility consistently exceeds realized
volatility because investors overpay for downside protection (insurance premium).

**Variant strategies**:
- Short ATM straddle/strangle on SPX
- Short VIX futures (in contango)
- Put-writing strategies
- Iron condor on single stocks

**For your system**: Trade VIX products or NDX options.
The NAS100 index in your universe is perfect for this.

**Risk**: Tail risk — massive drawdowns in crashes. MUST have:
- Strict stop-loss at 2-3× premium collected
- Position sizing max 2-5% of portfolio
- VIX spike circuit breaker (>30 VIX, stop selling)

---

### 2.7 Dispersion Trading

**Expected Sharpe**: 1.0-1.2
**Annual Return**: 15%
**Volatility**: 14%

Quantpedia #0237: 15.39% return, 13.86% vol.

**What it is**: Short index volatility, long constituent single-stock volatility.
Profits from correlation risk premium — index implied vol tends to be higher
than the sum of individual stock vols due to correlation being priced into index options.

**For your system**: Not directly applicable (no single stock options).
Possible workaround: Short VIX futures + long OTM NDX puts as proxy.

---

### 2.8 Market Making (HFT)

**Expected Sharpe**: 3-10+ (Wikipedia: "tens of times higher than traditional buy-and-hold")
**Profits**: Declining. US HFT profits: $5B (2009) → $1.25B (2012). Even lower now.

**Models**:
- Avellaneda-Stoikov (inventory-based market making)
- Gueant-Lehalle-Fernandez-Tapia extensions
- Reinforcement learning approaches (modern)

**Feasibility for solo trader**:
- Crypto exchanges (Binance, Bybit) — feasible with maker rebates
- Traditional markets — requires co-location, low-latency infra, exchange membership
- Sharpe is high but absolute dollar returns are small per unit of capital
- Requires deep pockets for inventory holding
- Intense competition from firms spending millions on infrastructure

**Minimum viable crypto market maker**:
1. Connect to exchange WebSocket for order book
2. Place bid at best_bid + 1 tick, ask at best_ask - 1 tick
3. Quote size proportional to (max_inventory - |current_inventory|)
4. Skew quotes based on inventory (A-S model)
5. Hedge excess inventory periodically

---

### 2.9 Short-Term Reversal / Mean Reversion

**Expected Sharpe**: 0.8-1.2
**Annual Return**: 15-30%
**Volatility**: 20-31%

Quantpedia #0071 (Futures): 29.64% return, 31.40% vol.

**What it is**: Assets that declined this week tend to rise next week, and vice versa.
Works on 1-5 day horizons. Driven by liquidity-provider effects and overreaction.

**For your system**: Works on equity indices (NAS100, US30).
Does NOT work well on trend-following FX pairs.
Crypto: mixed evidence — sometimes mean reverts intraday, trends on longer horizons.

---

### 2.10 Cryptocurrency Intraday Seasonality

**Expected Sharpe**: 1.0-1.6
**Annual Return**: 33%
**Volatility**: 21%

Quantpedia #0753: 33.00% return, 20.93% vol — overnight seasonality in Bitcoin.

BTC tends to have distinct intraday patterns related to:
- Asian market open (liquidity influx)
- European/US overlap (highest volume)
- US market close
- Weekend effects (crypto trades 24/7)

---

## 3. What's DEAD — Don't Waste Time

### 3.1 ML Direction Prediction on Liquid Markets
**Verdict**: 50% accuracy on XAUUSD/EURUSD is NORMAL — the market IS efficient.
- Financial time series have SNR approaching zero at daily+ frequencies
- **Kaggle competitions consistently find**: best models achieve ~51-53% accuracy, insufficient after costs
- **Academic meta-analyses**: most ML trading papers suffer from data snooping, look-ahead bias, and lack of out-of-sample testing
- **Lopez de Prado**: "Most academic papers in ML for finance would not survive a 5-minute conversation with a practitioner"
- What Renaissance/Two Sigma actually do: they use ML for **microstructure prediction**, **execution optimization**, and **alternative data processing** — NOT for simple direction prediction

### 3.2 Overfit Backtests
- Walk-forward analysis with 1 split = overfitting
- In-sample Sharpe > 2.0 with no out-of-sample = dead giveaway
- Using the same instruments for feature engineering and signal generation leaks future info
- The "Infinite Sharpe" backtest: survivorship bias + look-ahead + no transaction costs

### 3.3 Technical Analysis as ML Features
- RSI, MACD, Bollinger Bands → already priced in
- Pattern recognition on candlestick charts → no edge
- Ichimoku, Fibonacci → noise
- These have been arbed away for 20+ years

### 3.4 The "AI Hedge Fund" Graveyard
Common failure pattern:
1. Train LSTM/Transformer on OHLCV data → 55% accuracy in backtest
2. Deploy live → 48% accuracy, losing money
3. "The model needs more data" → add more features → 49% accuracy
4. Shut down

**Why it fails**: OHLCV alone has zero predictive content for ML models to extract
that isn't already captured by simple factor models.

### 3.5 Triangular Arbitrage in FX
Dead for retail. Banks and HFTs capture these in microseconds.
Available only if you have DMA + co-location + sub-millisecond execution.

### 3.6 Single-Pair Mean Reversion on Major FX
EUR/USD, GBP/USD etc. are near-random-walks on daily+ horizons.
Mean reversion alpha is in **cross-sectional** (basket) or **intraday** (sub-hour) horizons only.

---

## 4. What Renaissance/Two Sigma/Citadel Actually Do

(Based on available research, ex-employee talks, and public papers.)

### Renaissance Technologies (Medallion Fund)
- **~66% average annual return before fees (1988-2018)**
- **Short-term mean reversion** is the core signal (Simons' original insight)
- **Statistical arbitrage** across thousands of instruments simultaneously
- Uses **Hidden Markov Models** for regime detection, not deep learning
- **Billions of data points** — tick-level, order book, news sentiment, satellite imagery
- Single most important factor: **execution quality** (market impact minimization)
- Uses ML for **feature extraction** from alternative data, not for direct price prediction
- Capacity-constrained: Medallion closed to outside capital since 2005

### Two Sigma
- Systematic macro + equity stat arb
- Heavy use of **natural language processing** on news, filings, transcripts
- ML for **alpha discovery** (searching for new factors), not for prediction
- Combines thousands of weak signals into one strong composite
- "We don't predict prices. We find statistical patterns that repeat."

### Citadel
- Market making is the core business (not directional trading)
- Options market making — the largest in the world
- Volatility arbitrage and dispersion trading
- Convertible bond arbitrage
- Merger arbitrage
- Fundamental + quantitative hybrids

### Key Lesson: Why they succeed where retail fails
1. **Infrastructure** — co-location, FPGA, microwaves, exchange memberships
2. **Diversification** — thousands of uncorrelated signals, not one "AI model"
3. **Execution** — they capture 1-2bp of edge per trade, a million times
4. **Discipline** — they don't predict direction, they harvest statistical premia
5. **Turnover** — Renaissance trades thousands of times daily, not swing trading
6. **Scale** — at $50B AUM, capturing 0.01% edge = $5M/day

---

## 5. Recommendation for YOUR 15-Instrument System

### Your instruments:
| Type | Instruments | Count |
|------|------------|-------|
| Major FX | EURUSD, GBPUSD, USDCAD, USDJPY, USDCHF | 5 |
| Commodity FX | AUDUSD, NZDUSD | 2 |
| Crypto | BTCUSD, ETHUSD | 2 |
| Indices | NAS100, US30 | 2 |
| Precious Metals | XAGUSD | 1 |
| Non-USD FX | XAUUSD | 1 |

### Recommended Strategy Stack (ranked by expected contribution):

#### PRIMARY (80% of capital): Multi-Asset Time Series Momentum
- **Instruments**: All 15
- **Lookback**: 1M (21d), 3M (63d), 12M (252d) — composite signal
- **Signal**: Weighted average of 3 lookbacks: `0.4 × 1M + 0.35 × 3M + 0.25 × 12M`
- **Position sizing**: 1/15th risk budget per instrument, scaled to target 15% annual vol
- **Rebalance**: Weekly (every Monday)
- **Expected Sharpe**: 1.0-1.3

#### SECONDARY (15% of capital): Carry + Momentum Overlay on FX
- **Instruments**: The 8 FX pairs (7 forex + XAUUSD as proxy)
- **Signal**: Carry signal (interest rate differential) × Momentum filter (3M return > 0)
- **Position sizing**: Equal risk weight, cap at 3× leverage total
- **Expected Sharpe**: 0.7-1.0

#### TERTIARY (5% of capital): Mean Reversion on Indices + Crypto
- **Instruments**: NAS100, US30, BTCUSD, ETHUSD
- **Signal**: Z-score of 5-day return. Enter at z < -2, exit at z > -0.5
- **Stop loss**: 2× ATR
- **Expected Sharpe**: 0.5-0.8

### Expected Combined Performance:

| Metric | Conservative | Base | Optimistic |
|--------|-------------|------|------------|
| Sharpe | 0.8 | 1.2 | 1.5 |
| Annual Return | 12% | 18% | 24% |
| Max Drawdown | 25% | 18% | 12% |
| Win Rate | 52% | 55% | 58% |

### Risk Controls:
1. **Per-instrument risk**: Max 7% of NAV
2. **Gross exposure**: Cap at 300%
3. **Correlation circuit breaker**: If 5+ instruments highly correlated (>0.7), reduce exposure by half
4. **Volatility scaling**: Position size inversely proportional to recent (20d) realized vol
5. **Max daily loss**: 5% stop for the day
6. **Max drawdown**: 25% — halt and review

### Best Data Sources:
| Data Type | Source | Cost |
|-----------|--------|------|
| FX tick data | Dukascopy (free), TrueFX | Free-$100/mo |
| Crypto | Binance/Bitget WebSocket | Free |
| Index CFDs | Broker feed (MT5/CTrader) | Included |
| Interest rates | Central bank APIs, FRED | Free |
| Alternative | Tiingo, Polygon.io | $30-$200/mo |

---

## 6. Minimum Viable Path to Profitability

### Phase 0: Infrastructure (Week 1-2)
- [x] Live data pipeline to all 15 instruments (already have via MT5)
- [ ] Clean OHLCV storage (Parquet format, partitioned by instrument+date)
- [ ] Signal computation pipeline (daily batch)
- [ ] Order execution interface (MT5 Python API)

### Phase 1: Single-Factor Time Series Momentum (Week 3-4)
- Implement 12-month time series momentum on all 15 instruments
- Weekly rebalancing
- Risk parity position sizing
- **Paper trade for 2 weeks minimum**
- **Target**: Sharpe > 0.5 in paper trading

### Phase 2: Add Volatility Targeting (Week 5)
- Scale positions inversely to trailing 20-day ATR
- Equal risk contribution across instruments
- Set per-instrument risk limit at 5% of portfolio

### Phase 3: Add Carry Signal for FX (Week 6)
- Overlay carry filter on FX momentum signals
- Only take momentum signals that align with carry direction

### Phase 4: Live — Minimum Size (Week 7+)
- Start with 0.01 lots per instrument
- Run for 2 weeks
- If Sharpe > 1.0 (annualized) on live, scale up to 0.05 lots
- Scale gradually: never increase size after a winning week
- Kill switch: 20% drawdown from peak → halt and review

### What NOT to do:
- Don't add ML before phases 1-3 prove profitable without it
- Don't trade more than 2% risk per instrument
- Don't override signals manually
- Don't add instruments beyond the 15 you already have
- Don't optimize parameters on live data — use walk-forward only

---

## 7. Appendix: Quantpedia Strategy Reference Table

| ID | Strategy | Return | Vol | Implied Sharpe | Markets |
|----|----------|--------|-----|----------------|---------|
| #0001 | Asset Class Trend-Following | 11.27% | 6.87% | 1.64 | Multi-Asset |
| #0005 | FX Carry Trade | 7.27% | 9.60% | 0.76 | Currencies |
| #0008 | Currency Momentum Factor | 7.61% | 10.22% | 0.74 | Currencies |
| #0009 | Currency Value (PPP) | 7.82% | 9.33% | 0.84 | Currencies |
| #0012 | Pairs Trading Stocks | 11.16% | 5.85% | 1.91 | Equities |
| #0020 | Volatility Risk Premium | 26.00% | 19.00% | 1.37 | Equities |
| #0055 | Pairs Trading Country ETFs | 20.60% | 10.00% | 2.06 | Equities |
| #0071 | Short-Term Reversal Futures | 29.64% | 31.40% | 0.94 | Multi-Asset |
| #0118 | Time Series Momentum | 20.70% | 15.74% | 1.31 | Multi-Asset |
| #0237 | Dispersion Trading | 15.39% | 13.86% | 1.11 | Equities |
| #0753 | Overnight Bitcoin Seasonality | 33.00% | 20.93% | 1.58 | Crypto |

---

## 8. Key Academic References

1. **Moskowitz, Ooi, Pedersen (2012)** — "Time Series Momentum" — JFE. The foundational paper.
   https://doi.org/10.1016/j.jfineco.2011.11.003

2. **Asness, Moskowitz, Pedersen (2013)** — "Value and Momentum Everywhere" — JF.
   Shows value+momentum works across all asset classes.

3. **Koijen, Moskowitz, Pedersen, Vrugt (2018)** — "Carry" — JFE.
   Carry as a unified factor across equities, bonds, FX, commodities.

4. **Avellaneda & Stoikov (2008)** — "High-frequency trading in a limit order book" — QF.
   The canonical market making model.

5. **Gatev, Goetzmann, Rouwenhorst (2006)** — "Pairs Trading: Performance of a Relative-Value Arbitrage Rule" — RFS.
   Replicated in 2024 by Yale with Sharpe 1.35.

6. **Lopez de Prado (2018)** — "Advances in Financial Machine Learning" — Book.
   The definitive guide on avoiding overfitting in ML for finance.

7. **Bollerslev, Tauchen, Zhou (2009)** — "Expected Stock Returns and Variance Risk Premia" — RFS.
   Foundation for volatility risk premium harvesting.
