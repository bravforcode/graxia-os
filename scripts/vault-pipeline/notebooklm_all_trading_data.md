# Master Trading Intelligence — All Data

This notebook contains ALL trading data from the quant_os system.

---


# PART 1: TRADING STRATEGIES


## bos_choch

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [Swing High/Low]
source: bos_choch.py
updated: 2026-06-26
---
# Bos Choch
> Break of Structure / Change of Character

**Class:** `BOSCHoCHStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/bos_choch.py`

## Entry Conditions
- BUY on break above last swing high (BOS)
- SELL on break below last swing low (BOS)

## Exit Conditions
- TP at 2.5x risk (R:R)
- TP at 2.5x risk (R:R)

## Risk Parameters
- SL at midpoint between entry and last swing low
- SL at midpoint between entry and last swing high
- Minimum confidence threshold: 50/100

## Regime Filters
- None (always active)

## Best Market Conditions
Trending markets with clear structure. Best after consolidation breakouts. Weak in choppy price action.

## Known Weaknesses
Requires sufficient swing structure (3-bar lookback). May miss fast breakouts.

## Related Strategies
- [[order_block]]
- [[liquidity_sweep]]


## ema_cross

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [H4, M15]
indicators: [EMA, ATR]
source: ema_cross.py
updated: 2026-06-26
---
# Ema Cross
> EMA 9/21 crossover

**Class:** `EMACrossStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/ema_cross.py`

## Entry Conditions
- BUY when EMA 9 crosses above EMA 21
- SELL when EMA 9 crosses below EMA 21
- +15 bonus if price above EMA 50 (trend alignment)
- +10 bonus if H4 EMA 50 trend confirms

## Exit Conditions
- TP at 3.0x ATR from entry

## Risk Parameters
- SL = 1.5x ATR (tight)
- SL = 3.0x ATR (wide, for multi-TF noise)
- Minimum confidence threshold: 50/100

## Regime Filters
- EMA 50 trend filter
- H4 trend confirmation

## Best Market Conditions
Trending markets. Works best in strong directional moves. Struggles in ranging/choppy conditions.

## Known Weaknesses
Whipsaws in ranging markets. Late entries on slow crossovers. No volume filter.

## Related Strategies
- [[multi_tf_align]]
- [[fibonacci]]


## fair_value_gap

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [FVG]
source: fair_value_gap.py
updated: 2026-06-26
---
# Fair Value Gap
> Fair Value Gap detection

**Class:** `FairValueGapStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/fair_value_gap.py`

## Entry Conditions
- BUY when price enters bullish FVG zone (candle 1 high < candle 3 low)
- SELL when price enters bearish FVG zone

## Exit Conditions
- SL placed 10pt below FVG bottom (buffer)
- SL placed 10pt above FVG top (buffer)

## Risk Parameters
- Minimum confidence threshold: 50/100
- Max base score: 75 (FVG / order block)

## Regime Filters
- None (always active)

## Best Market Conditions
Impulsive moves with unfilled gaps. Works in trending and mean-reversion. Struggles in low-volatility grind.

## Known Weaknesses
FVGs can be filled partially. False gaps on low-timeframe noise. No trend confirmation.

## Related Strategies
- [[order_block]]
- [[supply_demand]]


## fibonacci

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [H1]
indicators: [ATR, Fibonacci, Swing High/Low]
source: fibonacci.py
updated: 2026-06-26
---
# Fibonacci
> Fibonacci retracement levels

**Class:** `FibonacciStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/fibonacci.py`

## Entry Conditions
- Trade at Fibonacci 61.8% retracement level
- Trade at Fibonacci 50% retracement level
- Trade at Fibonacci 38.2% retracement level

## Exit Conditions
- TP targets next Fibonacci level (50%)

## Risk Parameters
- Minimum confidence threshold: 50/100
- Max base score: 75 (FVG / order block)

## Regime Filters
- None (always active)

## Best Market Conditions
Swing trading in trending markets. Best at pullback levels. Fails in strong momentum without pullbacks.

## Known Weaknesses
Subjective swing high/low selection. Proximity threshold (0.3%) may miss moves.

## Related Strategies
- [[supply_demand]]
- [[ema_cross]]


## liquidity_sweep

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [ATR]
source: liquidity_sweep.py
updated: 2026-06-26
---
# Liquidity Sweep
> Liquidity sweep detection

**Class:** `LiquiditySweepStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/liquidity_sweep.py`

## Entry Conditions
- SELL after liquidity sweep above equal highs then price closes back below
- BUY after liquidity sweep below equal lows then price closes back above

## Exit Conditions
- TP at 2.5x risk (R:R)
- TP at 2.5x risk (R:R)

## Risk Parameters
- SL buffer = 0.5x ATR above/below sweep level
- Minimum confidence threshold: 50/100
- Max base score: 80 (liquidity sweep)

## Regime Filters
- None (always active)

## Best Market Conditions
All conditions. Designed to catch institutional stop Hunts. Best around key support/resistance.

## Known Weaknesses
Equal highs/lows detection is approximate. Can false-trigger on thin liquidity.

## Related Strategies
- [[bos_choch]]
- [[order_block]]


## london_breakout

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [Volume, London Range]
source: london_breakout.py
updated: 2026-06-26
---
# London Breakout
> London session open breakout

**Class:** `LondonBreakoutStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/london_breakout.py`

## Entry Conditions
- BUY on breakout above London range high
- SELL on breakdown below London range low
- Volume must exceed 1.3x average for confirmation

## Exit Conditions
- TP at 2.5x opening range size

## Risk Parameters
- Minimum confidence threshold: 50/100

## Regime Filters
- Volume confirmation

## Best Market Conditions
London session (08:00-12:00 UTC). Best on high-impact news days. Weak in quiet Asian session carryover.

## Known Weaknesses
Session-dependent — no signals outside London hours. Range calculation is approximate.

## Related Strategies
- [[opening_range]]
- [[news_fade]]


## multi_tf_align

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [H1, H4, M15]
indicators: [EMA, ATR]
source: multi_tf_align.py
updated: 2026-06-26
---
# Multi Tf Align
> Multi-timeframe trend alignment

**Class:** `MultiTFAlignStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/multi_tf_align.py`

## Entry Conditions
- BUY when all 3 timeframes (M15, H1, H4) show bullish alignment
- SELL when all 3 timeframes show bearish alignment
- BUY on 2/3 timeframe alignment (reduced confidence)

## Exit Conditions
- TP at 3.0x ATR from entry
- TP at 4.5x ATR from entry

## Risk Parameters
- SL = 3.0x ATR (wide, for multi-TF noise)
- Minimum confidence threshold: 50/100
- Max base score: 85 (3/3 TF alignment)
- Max base score: 75 (FVG / order block)

## Regime Filters
- Multi-timeframe alignment gate

## Best Market Conditions
Strong trending markets. Highest win rate when all 3 TFs agree. Rare signals — low frequency.

## Known Weaknesses
Very low signal frequency (3/3 alignment rare). 2/3 alignment has higher false-positive rate.

## Related Strategies
- [[ema_cross]]
- [[order_block]]


## news_fade

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M1]
indicators: [RSI, ATR]
source: news_fade.py
updated: 2026-06-26
---
# News Fade
> Fade news-driven spikes

**Class:** `NewsFadeStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/news_fade.py`

## Entry Conditions
- Fade news spikes > 0.4% move (mean reversion)
- Mandatory RSI confirmation (> 70 for short, < 30 for long)

## Exit Conditions
- TP at 2.5x ATR from entry

## Risk Parameters
- SL = 1.5x ATR (tight)
- Minimum confidence threshold: 50/100

## Regime Filters
- RSI mandatory confirmation
- Minimum volatility threshold (0.4% move)

## Best Market Conditions
High-volatility news events (NFP, FOMC, CPI). Fades overreactions. Dangerous in genuine regime shifts.

## Known Weaknesses
Requires RSI confirmation — misses some valid fades. Dangerous in genuine regime changes.

## Related Strategies
- [[rsi_divergence]]
- [[london_breakout]]


## opening_range

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M5]
indicators: [Volume, Opening Range]
source: opening_range.py
updated: 2026-06-26
---
# Opening Range
> Opening range breakout

**Class:** `OpeningRangeStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/opening_range.py`

## Entry Conditions
- BUY on breakout above opening range high
- SELL on breakdown below opening range low
- Volume must exceed 1.3x average for confirmation

## Exit Conditions
- SL at 30% of opening range below entry
- SL at 30% of opening range above entry

## Risk Parameters
- Minimum confidence threshold: 50/100

## Regime Filters
- Volume confirmation
- Time-of-day filter (first 4h only)

## Best Market Conditions
First 4 hours of trading session. Best with volume confirmation. Avoids late-day false breakouts.

## Known Weaknesses
Time-filtered — stops trading after 12:00 UTC. Opening range is approximate (12 M5 bars).

## Related Strategies
- [[london_breakout]]
- [[supply_demand]]


## order_block

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [H1, H4]
indicators: [EMA, Order Blocks]
source: order_block.py
updated: 2026-06-26
---
# Order Block
> ICT Order Block identification

**Class:** `OrderBlockStrategy`
**Min Timeframe:** H1
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/order_block.py`

## Entry Conditions
- BUY when price near bullish order block (last bearish candle before rally)
- SELL when price near bearish order block (last bullish candle before drop)

## Exit Conditions
- TP at 2.0x risk from entry

## Risk Parameters
- Minimum confidence threshold: 50/100
- Max base score: 75 (FVG / order block)

## Regime Filters
- None (always active)

## Best Market Conditions
Institutional reversals on H1/H4. Best at key psychological levels. Requires H4 EMA confirmation.

## Known Weaknesses
Requires H1 + H4 data. OB detection is simplified (single candle pattern).

## Related Strategies
- [[bos_choch]]
- [[fair_value_gap]]


## rsi_divergence

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [RSI, ATR]
source: rsi_divergence.py
updated: 2026-06-26
---
# Rsi Divergence
> RSI divergence with price

**Class:** `RSIDivergenceStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/rsi_divergence.py`

## Entry Conditions
- BUY when RSI drops below 35 (oversold)
- SELL when RSI rises above 65 (overbought)

## Exit Conditions
- TP at 2.5x ATR from entry

## Risk Parameters
- SL = 1.5x ATR (tight)
- Minimum confidence threshold: 50/100
- Max base score: 80 (liquidity sweep)

## Regime Filters
- RSI mandatory confirmation

## Best Market Conditions
Range-bound or exhaustion moves. Best at reversals. Fails in strong trends where RSI can stay extended.

## Known Weaknesses
Divergences can persist for extended periods. No trend filter — catches falling knives.

## Related Strategies
- [[news_fade]]
- [[vwap_rejection]]


## supply_demand

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [ATR, Volume, Supply/Demand Zones]
source: supply_demand.py
updated: 2026-06-26
---
# Supply Demand
> Supply and Demand zone trading

**Class:** `SupplyDemandStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/supply_demand.py`

## Entry Conditions
- BUY when price is near demand zone (bottom 12% of range)
- SELL when price is near supply zone (top 12% of range)
- Volume must exceed 1.3x average for confirmation

## Exit Conditions
- TP at 1.5x SL distance

## Risk Parameters
- Minimum SL = max(1.5x ATR, symbol-specific minimum)
- XAUUSD min SL = $28 (prevents sizing explosion)
- Minimum confidence threshold: 50/100

## Regime Filters
- Volume confirmation

## Best Market Conditions
Range and reversal trading. Best when zones align with higher TF structure. Needs volume confirmation.

## Known Weaknesses
Zone detection is zone-cluster based, not precise. Min SL ($28) may be too wide for small accounts.

## Related Strategies
- [[order_block]]
- [[fibonacci]]


## vwap_rejection

---
type: strategy
category: gold_bot
symbols: [XAUUSD]
timeframes: [M15]
indicators: [ATR, VWAP, Volume]
source: vwap_rejection.py
updated: 2026-06-26
---
# Vwap Rejection
> VWAP rejection with volume

**Class:** `VWAPRejectionStrategy`
**Min Timeframe:** M15
**Symbols:** XAUUSD
**Source:** `gold_bot/strategies/vwap_rejection.py`

## Entry Conditions
- SELL on VWAP rejection (price was above, returned to VWAP)
- BUY on VWAP rejection (price was below, returned to VWAP)

## Exit Conditions
- TP at 2.0x ATR from entry

## Risk Parameters
- SL = 1.5x ATR (tight)
- Minimum confidence threshold: 50/100

## Regime Filters
- Volume confirmation

## Best Market Conditions
Intraday mean reversion. Best in first half of session when VWAP is established. Weak in trend days.

## Known Weaknesses
VWAP is simplified (no rolling reset). 0.05% proximity threshold is tight.

## Related Strategies
- [[rsi_divergence]]
- [[news_fade]]



# PART 2: BACKTEST RESULTS


## 2026-06-20_MLB

---
type: backtest
date: 2026-06-20
symbol: XAUUSD
strategies: [MLB]
status: auto-generated
---

# Backtest: MLB — XAUUSD

**Date:** 2026-06-20
**Strategy:** MLB
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 0 |
| Win Rate | 0.0% |
| Profit Factor | 0.00 |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **NO TRADES** — Strategy produced zero trades in this window.

## Related

- [[trading/backtest/index]]


## 2026-06-20_MRB

---
type: backtest
date: 2026-06-20
symbol: XAUUSD
strategies: [MRB]
status: auto-generated
---

# Backtest: MRB — XAUUSD

**Date:** 2026-06-20
**Strategy:** MRB
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 0 |
| Win Rate | 0.0% |
| Profit Factor | 0.00 |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **NO TRADES** — Strategy produced zero trades in this window.

## Related

- [[trading/backtest/index]]


## 2026-06-20_MTM

---
type: backtest
date: 2026-06-20
symbol: XAUUSD
strategies: [MTM]
status: auto-generated
---

# Backtest: MTM — XAUUSD

**Date:** 2026-06-20
**Strategy:** MTM
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 2 |
| Win Rate | 50.0% |
| Profit Factor | 1.87 |
| Sharpe Ratio | 0.29 |
| Sortino Ratio | 0.08 |
| Max Drawdown | 24.0% |
| Total Return | 0.92% |
| Expectancy | 45.86 |
| Avg R:R | 1.87 |
| CAGR | 0.45% |

## Trade Breakdown

- **Wins / Losses:** 1 / 1
- **Long / Short:** 0 / 0
- **Avg Win:** 197.17
- **Avg Loss:** -105.45
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_BTCUSD_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: BTCUSD
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — BTCUSD

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** BTCUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 6.1% |
| Profit Factor | 1.03 |
| Sharpe Ratio | 0.43 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 29.7% |
| Total Return | 18.99% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_BTCUSD_Momentum

---
type: backtest
date: 2026-06-26
symbol: BTCUSD
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — BTCUSD

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** BTCUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 47.8% |
| Profit Factor | 0.99 |
| Sharpe Ratio | -0.51 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 88.4% |
| Total Return | -49.31% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_BTCUSD_RSI

---
type: backtest
date: 2026-06-26
symbol: BTCUSD
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — BTCUSD

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** BTCUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 11.2% |
| Profit Factor | 1.02 |
| Sharpe Ratio | 0.56 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 22.1% |
| Total Return | 29.62% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_BTCUSD_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: BTCUSD
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — BTCUSD

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** BTCUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.3% |
| Profit Factor | 1.01 |
| Sharpe Ratio | 0.35 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 43.9% |
| Total Return | 33.61% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_BTCUSD_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: BTCUSD
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — BTCUSD

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** BTCUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_EURUSD_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: EURUSD
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — EURUSD

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** EURUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 6.1% |
| Profit Factor | 1.10 |
| Sharpe Ratio | 1.62 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 2.4% |
| Total Return | 11.96% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_EURUSD_Momentum

---
type: backtest
date: 2026-06-26
symbol: EURUSD
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — EURUSD

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** EURUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.1% |
| Profit Factor | 0.97 |
| Sharpe Ratio | -1.42 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 27.9% |
| Total Return | -25.22% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_EURUSD_RSI

---
type: backtest
date: 2026-06-26
symbol: EURUSD
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — EURUSD

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** EURUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 11.9% |
| Profit Factor | 1.06 |
| Sharpe Ratio | 1.35 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 2.4% |
| Total Return | 12.33% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_EURUSD_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: EURUSD
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — EURUSD

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** EURUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.4% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -1.12 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 24.6% |
| Total Return | -19.93% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_EURUSD_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: EURUSD
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — EURUSD

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** EURUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_GBPUSD_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: GBPUSD
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — GBPUSD

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** GBPUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 5.9% |
| Profit Factor | 1.06 |
| Sharpe Ratio | 1.07 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 3.7% |
| Total Return | 7.41% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_GBPUSD_Momentum

---
type: backtest
date: 2026-06-26
symbol: GBPUSD
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — GBPUSD

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** GBPUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.0% |
| Profit Factor | 0.96 |
| Sharpe Ratio | -1.88 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 34.3% |
| Total Return | -33.20% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_GBPUSD_RSI

---
type: backtest
date: 2026-06-26
symbol: GBPUSD
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — GBPUSD

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** GBPUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 12.0% |
| Profit Factor | 1.04 |
| Sharpe Ratio | 1.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 3.5% |
| Total Return | 8.88% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_GBPUSD_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: GBPUSD
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — GBPUSD

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** GBPUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.7% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -1.09 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 25.9% |
| Total Return | -19.18% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_GBPUSD_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: GBPUSD
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — GBPUSD

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** GBPUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_NAS100_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: NAS100
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — NAS100

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** NAS100

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 6.1% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -0.30 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 13.7% |
| Total Return | -7.03% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_NAS100_Momentum

---
type: backtest
date: 2026-06-26
symbol: NAS100
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — NAS100

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** NAS100

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.3% |
| Profit Factor | 1.02 |
| Sharpe Ratio | 0.94 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 18.3% |
| Total Return | 49.25% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_NAS100_RSI

---
type: backtest
date: 2026-06-26
symbol: NAS100
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — NAS100

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** NAS100

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 13.6% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -0.53 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 24.8% |
| Total Return | -14.51% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_NAS100_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: NAS100
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — NAS100

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** NAS100

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.7% |
| Profit Factor | 1.00 |
| Sharpe Ratio | 0.05 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 37.6% |
| Total Return | 2.75% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_NAS100_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: NAS100
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — NAS100

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** NAS100

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_US30_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: US30
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — US30

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** US30

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 6.1% |
| Profit Factor | 1.02 |
| Sharpe Ratio | 0.35 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 7.3% |
| Total Return | 5.85% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_US30_Momentum

---
type: backtest
date: 2026-06-26
symbol: US30
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — US30

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** US30

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.7% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -0.66 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 28.5% |
| Total Return | -25.02% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_US30_RSI

---
type: backtest
date: 2026-06-26
symbol: US30
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — US30

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** US30

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 12.9% |
| Profit Factor | 0.99 |
| Sharpe Ratio | -0.33 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 13.3% |
| Total Return | -6.42% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_US30_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: US30
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — US30

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** US30

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.6% |
| Profit Factor | 1.00 |
| Sharpe Ratio | 0.18 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 21.5% |
| Total Return | 6.90% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_US30_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: US30
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — US30

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** US30

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_USDJPY_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: USDJPY
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — USDJPY

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** USDJPY

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 5.9% |
| Profit Factor | 1.06 |
| Sharpe Ratio | 1.03 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 3.3% |
| Total Return | 10.53% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_USDJPY_Momentum

---
type: backtest
date: 2026-06-26
symbol: USDJPY
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — USDJPY

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** USDJPY

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 48.6% |
| Profit Factor | 0.99 |
| Sharpe Ratio | -0.51 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 15.1% |
| Total Return | -12.16% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_USDJPY_RSI

---
type: backtest
date: 2026-06-26
symbol: USDJPY
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — USDJPY

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** USDJPY

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 12.4% |
| Profit Factor | 1.02 |
| Sharpe Ratio | 0.37 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 11.0% |
| Total Return | 4.81% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_USDJPY_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: USDJPY
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — USDJPY

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** USDJPY

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.4% |
| Profit Factor | 1.03 |
| Sharpe Ratio | 1.23 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 7.9% |
| Total Return | 29.01% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_USDJPY_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: USDJPY
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — USDJPY

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** USDJPY

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_XAUUSD_MeanReversion

---
type: backtest
date: 2026-06-26
symbol: XAUUSD
strategies: [MeanReversion]
status: auto-generated
---

# Backtest: MeanReversion — XAUUSD

**Date:** 2026-06-26
**Strategy:** MeanReversion
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 6.1% |
| Profit Factor | 0.99 |
| Sharpe Ratio | -0.17 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 22.4% |
| Total Return | -4.27% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_XAUUSD_Momentum

---
type: backtest
date: 2026-06-26
symbol: XAUUSD
strategies: [Momentum]
status: auto-generated
---

# Backtest: Momentum — XAUUSD

**Date:** 2026-06-26
**Strategy:** Momentum
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.0% |
| Profit Factor | 1.03 |
| Sharpe Ratio | 1.30 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 13.4% |
| Total Return | 68.91% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_XAUUSD_RSI

---
type: backtest
date: 2026-06-26
symbol: XAUUSD
strategies: [RSI]
status: auto-generated
---

# Backtest: RSI — XAUUSD

**Date:** 2026-06-26
**Strategy:** RSI
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 12.6% |
| Profit Factor | 0.98 |
| Sharpe Ratio | -0.40 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 20.1% |
| Total Return | -11.73% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]


## 2026-06-26_XAUUSD_TrendFollow

---
type: backtest
date: 2026-06-26
symbol: XAUUSD
strategies: [TrendFollow]
status: auto-generated
---

# Backtest: TrendFollow — XAUUSD

**Date:** 2026-06-26
**Strategy:** TrendFollow
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 49.7% |
| Profit Factor | 1.02 |
| Sharpe Ratio | 1.04 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 18.5% |
| Total Return | 54.91% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **MARGINAL** — Profitable but risk-adjusted returns need monitoring.

## Related

- [[trading/backtest/index]]


## 2026-06-26_XAUUSD_VolBreakout

---
type: backtest
date: 2026-06-26
symbol: XAUUSD
strategies: [VolBreakout]
status: auto-generated
---

# Backtest: VolBreakout — XAUUSD

**Date:** 2026-06-26
**Strategy:** VolBreakout
**Symbol:** XAUUSD

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 59999 |
| Win Rate | 0.0% |
| Profit Factor | inf |
| Sharpe Ratio | 0.00 |
| Sortino Ratio | 0.00 |
| Max Drawdown | 0.0% |
| Total Return | 0.00% |
| Expectancy | 0.00 |
| Avg R:R | 0.00 |
| CAGR | 0.00% |

## Trade Breakdown

- **Wins / Losses:** 0 / 0
- **Long / Short:** 0 / 0
- **Avg Win:** 0.00
- **Avg Loss:** 0.00
- **Max Consecutive Wins:** 0
- **Max Consecutive Losses:** 0
- **Total Fees:** 0.00

## Assessment

> **FAIL** — Below profitability or risk thresholds.

## Related

- [[trading/backtest/index]]



# PART 3: MACRO ANALYSIS


## 2026-06-26

---
type: macro-dashboard
date: 2026-06-26
vix_level: 20.18
dxy_trend: "Dollar Strength ^"
---

# Macro Dashboard — 2026-06-26

---

## VIX (S&P 500 Volatility)

| Metric | Value |
|--------|-------|
| Current | **20.18** |
| 52w Percentile | 66.7th |
| MA(20) | 18.01 |
| MA(50) | 17.82 |
| 52w Range | 11.86 – 52.33 |
| Trend | Strong Up |

> 🟡 **Above average** — moderate uncertainty, watch for expansion

## GVZ (Gold Volatility Index)

| Metric | Value |
|--------|-------|
| Current | **29.58** |
| 52w Percentile | 95.1th |
| MA(20) | 27.12 |
| 52w Range | 10.22 – 46.02 |

## DXY (US Dollar Index)

| Metric | Value |
|--------|-------|
| Current | **101.195** |
| 52w Percentile | 42.8th |
| MA(20) | 100.132 |
| MA(50) | 99.217 |
| 52w Range | 91.86 – 114.11 |
| Trend | **Dollar Strength ^** |

## DFII10 (10Y Real Yield)

| Metric | Value |
|--------|-------|
| Current | **2.23%** |
| Window Percentile | 80.0th |
| Window Range | 2.06% – 2.29% |

## COT Positioning (Gold Futures)

*Data as of: 2026-06-16*

| Metric | Value |
|--------|-------|
| Open Interest | 339,330 |
| Managed Money Long | 128,043 |
| Managed Money Short | 14,322 |
| MM Net Long | **113,721** (33.5%) |
| 52w COT Index | 83.3th |
| 3w Trend | +16,275 ^ |
| Producer Net Short % | 5.0% |

## Economic Events

| Currency | Event | Importance | Forecast | Previous |
|----------|-------|------------|----------|----------|
| IT | Italian Trade Balance Non-EU(May)Act:-Cons:-Prev.: | High | — | 3.85B |
| BR | Unemployment Rate(May)Act:-Cons:5.6%Prev.:5.8% | High | 5.6% | 5.8% |
| US | Retail Inventories Ex Auto(May)Act:-Cons:-Prev.:0. | Low | — | 0.6% |
| US | Goods Trade Balance(May)Act:-Cons:-85.00BPrev.:-83 | High | -85.00B | -83.01B |
| US | Wholesale Inventories(MoM)(May)Act:-Cons:0.3%Prev. | Low | 0.3% | 0.6% |
| US | Michigan 1-Year Inflation Expectations(Jun)Act:-Co | High | 4.6% | 4.8% |
| US | Michigan Consumer Sentiment(Jun)Act:-Cons:48.9Prev | High | 48.9 | 44.8 |
| US | Michigan 5-Year Inflation Expectations(Jun)Act:-Co | High | 3.4% | 3.9% |
| US | Michigan Consumer Expectations(Jun)Act:-Cons:49.3P | High | 49.3 | 44.1 |
| US | Michigan Current Conditions(Jun)Act:-Cons:48.4Prev | High | 48.4 | 45.8 |
| US | FOMC Member Williams SpeaksAct:-Cons:-Prev.:- | High | — | — |
| US | FOMC Member Kashkari SpeaksAct:-Cons:-Prev.:- | High | — | — |
| US | U.S. Baker Hughes Oil Rig CountAct:-Cons:-Prev.:43 | Low | — | 433 |
| US | U.S. Baker Hughes Total Rig CountAct:-Cons:-Prev.: | Low | — | 563 |
| US | CFTC S&P 500 speculative net positionsAct:-Cons:-P | Low | — | -194.0K |

## Correlation Insights

- GVZ spiking (p95) while VIX moderate — gold vol underpricing, hedging opportunity
- Real yields elevated (>2.2%) — headwind for gold

---
*Generated: 2026-06-26 23:58 by vault-pipeline/macro_to_vault.py*

## 2026-06-27-credit

---
type: macro-credit
date: 2026-06-27
---

# Credit Stress Monitor — 2026-06-27

---

## Credit Indicators

| Series | Current | 5Y Percentile | 5Y Mean | 5Y Range |
|--------|---------|---------------|---------|----------|
| BAA-10Y Credit Spread | **1.52%** | 11.8th | 1.81% | 1.36 – 2.42 |
| HY OAS | **2.76%** | 13.0th | 3.21% | 2.59 – 4.61 |
| 10Y-2Y (Recession Proxy) | **0.31%** | 58.2th | 0.09% | -1.08 – 1.29 |

## Credit Assessment

- Credit conditions neutral

## High Yield OAS Detail

| Metric | Value |
|--------|-------|
| Current | **2.76%** |
| 5Y Percentile | 13.0th |
| 5Y Mean | 3.21% |
| 5Y Range | 2.59% – 4.61% |
| Last Updated | 2026-06-24 |

> HY OAS < 3% — tight credit, risk-on environment

---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*

## 2026-06-27-cross-market

---
type: macro-cross-market
date: 2026-06-27
---

# Cross-Market Signals — 2026-06-27

---

## Key Markets

| Market | Current | 5Y Percentile | 5Y Mean | Trend |
|--------|---------|---------------|---------|-------|
| S&P 500 | **7,357.49** | 97.4th | 5,148.85 | High |
| Brent Crude | **76.49** | 37.3th | 83.41 | Mid |
| WTI Crude | **78.94** | 57.6th | 78.76 | Mid |
| USD/JPY | **161.37** | 99.5th | 141.40 | High |
| EUR/USD | **1.15** | 71.9th | 1.10 | High |

## Volatility & Dollar

| Indicator | Value | Percentile |
|-----------|-------|------------|
| VIX | 20.18 | 66.7th |
| GVZ | 29.58 | 95.1th |
| DXY | 101.195 | 42.8th |
| DXY Trend | Dollar Strength ^ | — |

## Cross-Market Signals

- S&P 500 at multi-year highs — risk-on, potential gold headwind
- USD/JPY elevated (>150) — BoJ intervention risk, carry trade unwind potential

---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*

## 2026-06-27-liquidity

---
type: macro-liquidity
date: 2026-06-27
---

# System Liquidity — 2026-06-27

---

## Liquidity Indicators

| Series | Current | 5Y Percentile | 5Y Mean | Last Updated |
|--------|---------|---------------|---------|--------------|
| Fed Balance Sheet | **6,735,645** | 24.1th | 7,717,523 | 2026-06-24 |
| ON RRP Facility | **6** | 11.2th | 977 | 2026-06-25 |
| Treasury General Account | **918,696** | 95.0th | 611,848 | 2026-06-24 |

## Liquidity Assessment

- ON RRP drained ($6B) — liquidity moving to markets
- TGA high ($918696B) — Treasury draining liquidity

## Net Liquidity Estimate

- Fed Balance Sheet: $6,735,645B
- ON RRP (drain): -$6B
- TGA (drain): -$918,696B
- **Net System Liquidity: $5,816,943B**

> Net liquidity above $7.5T — ample, supportive for risk assets

---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*

## 2026-06-27-weekly

---
type: macro-weekly
date: 2026-06-27
---

# Weekly Macro Summary — 2026-06-27

---

## Snapshot

| Category | Key Reading | Signal |
|----------|-------------|--------|
| Volatility | VIX 20.18 / GVZ 29.58 | Elevated |
| Dollar | DXY 101.195 (Dollar Strength ^) | Neutral |
| Real Yields | DFII10 2.23% | Gold Headwind |
| XAUUSD Regime | N/A (0%) | Unclear |

- Yield curve: **Normal** (10Y-2Y = 0.31%)

- Credit: **Tight** (HY OAS = 2.76%)

- Net liquidity: **Ample** ($5,816,943B)

- COT: MM net long 113,721 (33.5%), 52w index 83.3th

## Key Themes

- GVZ spiking (p95) while VIX moderate — gold vol underpricing, hedging opportunity
- Real yields elevated (>2.2%) — headwind for gold
- Credit conditions neutral
- ON RRP drained ($6B) — liquidity moving to markets
- TGA high ($918696B) — Treasury draining liquidity
- Inflation expectations anchored

---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*

## 2026-06-27-yields

---
type: macro-yields
date: 2026-06-27
---

# Yield Curve & Rates — 2026-06-27

---

## Current Rates

| Series | Current | 5Y Percentile | 5Y Range |
|--------|---------|---------------|----------|
| Fed Funds Rate | **3.63%** | 28.6th | 0.06 – 5.33 |
| 2Y Treasury | **4.11%** | 58.9th | 0.17 – 5.19 |
| 10Y Treasury | **4.41%** | 83.2th | 1.19 – 4.98 |
| 10Y-2Y Spread | **0.31%** | 58.2th | -1.08 – 1.29 |
| 5Y Breakeven Inflation | **2.23%** | 17.1th | 1.86 – 3.59 |
| 5Y5Y Forward Inflation | **2.19%** | 20.9th | 1.92 – 2.67 |

## Curve Analysis

- **Normal curve** (10Y-2Y = 0.31%)

## Real Yields (DFII10)

| Metric | Value |
|--------|-------|
| Current | **2.23%** |
| Percentile | 80.0th |
| Range | 2.06% – 2.29% |

> Real yields elevated — headwind for gold, risk assets

## Forward Inflation Expectations

- 5Y Breakeven: **2.23%**
- 5Y5Y Forward: **2.19%**


---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*

## 2026-06-27

---
type: macro-dashboard
date: 2026-06-27
vix_level: 20.18
dxy_trend: "Dollar Strength ^"
---

# Macro Dashboard — 2026-06-27

---

## VIX (S&P 500 Volatility)

| Metric | Value |
|--------|-------|
| Current | **20.18** |
| 52w Percentile | 66.7th |
| MA(20) | 18.01 |
| MA(50) | 17.82 |
| 52w Range | 11.86 – 52.33 |
| Trend | Strong Up |

> **Above average** — moderate uncertainty, watch for expansion

## GVZ (Gold Volatility Index)

| Metric | Value |
|--------|-------|
| Current | **29.58** |
| 52w Percentile | 95.1th |
| MA(20) | 27.12 |
| 52w Range | 10.22 – 46.02 |

## DXY (US Dollar Index)

| Metric | Value |
|--------|-------|
| Current | **101.195** |
| 52w Percentile | 42.8th |
| MA(20) | 100.132 |
| MA(50) | 99.217 |
| 52w Range | 91.86 – 114.11 |
| Trend | **Dollar Strength ^** |

## DFII10 (10Y Real Yield)

| Metric | Value |
|--------|-------|
| Current | **2.23%** |
| Window Percentile | 80.0th |
| Window Range | 2.06% – 2.29% |

## COT Positioning (Gold Futures)

*Data as of: 2026-06-16*

| Metric | Value |
|--------|-------|
| Open Interest | 339,330 |
| Managed Money Long | 128,043 |
| Managed Money Short | 14,322 |
| MM Net Long | **113,721** (33.5%) |
| 52w COT Index | 83.3th |
| 3w Trend | +16,275 ^ |
| Producer Net Short % | 5.0% |

## Economic Events

| Currency | Event | Importance | Forecast | Previous |
|----------|-------|------------|----------|----------|
| IT | Italian Trade Balance Non-EU(May)Act:-Cons:-Prev.: | High | — | 3.85B |
| BR | Unemployment Rate(May)Act:-Cons:5.6%Prev.:5.8% | High | 5.6% | 5.8% |
| US | Retail Inventories Ex Auto(May)Act:-Cons:-Prev.:0. | Low | — | 0.6% |
| US | Goods Trade Balance(May)Act:-Cons:-85.00BPrev.:-83 | High | -85.00B | -83.01B |
| US | Wholesale Inventories(MoM)(May)Act:-Cons:0.3%Prev. | Low | 0.3% | 0.6% |
| US | Michigan 1-Year Inflation Expectations(Jun)Act:-Co | High | 4.6% | 4.8% |
| US | Michigan Consumer Sentiment(Jun)Act:-Cons:48.9Prev | High | 48.9 | 44.8 |
| US | Michigan 5-Year Inflation Expectations(Jun)Act:-Co | High | 3.4% | 3.9% |
| US | Michigan Consumer Expectations(Jun)Act:-Cons:49.3P | High | 49.3 | 44.1 |
| US | Michigan Current Conditions(Jun)Act:-Cons:48.4Prev | High | 48.4 | 45.8 |
| US | FOMC Member Williams SpeaksAct:-Cons:-Prev.:- | High | — | — |
| US | FOMC Member Kashkari SpeaksAct:-Cons:-Prev.:- | High | — | — |
| US | U.S. Baker Hughes Oil Rig CountAct:-Cons:-Prev.:43 | Low | — | 433 |
| US | U.S. Baker Hughes Total Rig CountAct:-Cons:-Prev.: | Low | — | 563 |
| US | CFTC S&P 500 speculative net positionsAct:-Cons:-P | Low | — | -194.0K |

## Correlation Insights

- GVZ spiking (p95) while VIX moderate — gold vol underpricing, hedging opportunity
- Real yields elevated (>2.2%) — headwind for gold

---
*Generated: 2026-06-27 16:30 by vault-pipeline/macro_to_vault.py*


# PART 4: ML MODELS


## _20260619_201454

---
type: ml-model
model_name: ""
version: "20260619_201454"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:14:54"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201454.pkl"
file_hash: "90955778b26434dc59f9ed305d6e3517"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_201454

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:14:54
- **Version:** `20260619_201454`
- **Total Features:** 34
- **File Hash:** `90955778b264...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201454.pkl`


## _20260619_201455

---
type: ml-model
model_name: ""
version: "20260619_201455"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:14:55"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201455.pkl"
file_hash: "d5858d781654c5bb3b881a7e254e1d4c"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_201455

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:14:55
- **Version:** `20260619_201455`
- **Total Features:** 34
- **File Hash:** `d5858d781654...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201455.pkl`


## _20260619_201456

---
type: ml-model
model_name: ""
version: "20260619_201456"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:14:56"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201456.pkl"
file_hash: "0851fe306631a2cfb2aa2bd2b2d4c1f4"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_201456

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:14:56
- **Version:** `20260619_201456`
- **Total Features:** 34
- **File Hash:** `0851fe306631...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201456.pkl`


## _20260619_201457

---
type: ml-model
model_name: ""
version: "20260619_201457"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:14:57"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201457.pkl"
file_hash: "26f3448a25c8d300b315fd3ea1bd98ba"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_201457

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:14:57
- **Version:** `20260619_201457`
- **Total Features:** 34
- **File Hash:** `26f3448a25c8...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_201457.pkl`


## _20260619_203244

---
type: ml-model
model_name: ""
version: "20260619_203244"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:32:44"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203244.pkl"
file_hash: "fbd24845b43467cd8cb22ebb9107ab5f"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_203244

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:32:44
- **Version:** `20260619_203244`
- **Total Features:** 34
- **File Hash:** `fbd24845b434...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203244.pkl`


## _20260619_203245

---
type: ml-model
model_name: ""
version: "20260619_203245"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:32:45"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203245.pkl"
file_hash: "47397e87b30463b5af7aa37303cc8149"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_203245

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:32:45
- **Version:** `20260619_203245`
- **Total Features:** 34
- **File Hash:** `47397e87b304...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203245.pkl`


## _20260619_203247

---
type: ml-model
model_name: ""
version: "20260619_203247"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:32:47"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203247.pkl"
file_hash: "f96713cb8c7d1a9e0b5d3742a638ebe4"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_203247

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:32:47
- **Version:** `20260619_203247`
- **Total Features:** 34
- **File Hash:** `f96713cb8c7d...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203247.pkl`


## _20260619_203251

---
type: ml-model
model_name: ""
version: "20260619_203251"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-19 20:32:51"
model_type: "xgboost"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203251.pkl"
file_hash: "f92364a1e106e1087e1e36a38536d71e"
feature_importance_top10: []
feature_count: 34
tags:
  - ml-model
  -
  - trading
---

#  — 20260619_203251

> ML model trained on `xgboost` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** xgboost
- **Trained:** 2026-06-19 20:32:51
- **Version:** `20260619_203251`
- **Total Features:** 34
- **File Hash:** `f92364a1e106...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_20260619_203251.pkl`


## _20260626

---
type: ml-model
model_name: ""
version: "20260626"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "20260626"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_XAUUSD_20260626.pkl"
file_hash: "23b1d3ac705b99efbbb8eb1565d65a10"
feature_importance_top10: []
feature_count: 50
tags:
  - ml-model
  -
  - trading
---

#  — 20260626

> ML model trained on `unknown` for `` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 20260626
- **Version:** `20260626`
- **Total Features:** 50
- **File Hash:** `23b1d3ac705b...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_XAUUSD_20260626.pkl`


## BTCUSD_20260626_160330

---
type: ml-model
model_name: "BTCUSD"
version: "20260626_160330"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:03:30"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_BTCUSD_20260626_160330.pkl"
file_hash: "a85e3aecc1e213efacf6a11c56b25bbb"
feature_importance_top10: []
feature_count: 17
tags:
  - ml-model
  - BTCUSD
  - trading
---

# BTCUSD — 20260626_160330

> ML model trained on `unknown` for `BTCUSD` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 2026-06-26 16:03:30
- **Version:** `20260626_160330`
- **Total Features:** 17
- **File Hash:** `a85e3aecc1e2...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_BTCUSD_20260626_160330.pkl`


## EURUSD_20260626_160329

---
type: ml-model
model_name: "EURUSD"
version: "20260626_160329"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:03:29"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_EURUSD_20260626_160329.pkl"
file_hash: "c35ea029d42547ceafe9fdd9164d751e"
feature_importance_top10: []
feature_count: 17
tags:
  - ml-model
  - EURUSD
  - trading
---

# EURUSD — 20260626_160329

> ML model trained on `unknown` for `EURUSD` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 2026-06-26 16:03:29
- **Version:** `20260626_160329`
- **Total Features:** 17
- **File Hash:** `c35ea029d425...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_EURUSD_20260626_160329.pkl`


## live_20260626_143317

---
type: ml-model
model_name: "live"
version: "20260626_143317"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 14:33:17"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_143317.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_143317

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 14:33:17
- **Version:** `20260626_143317`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_143317.pkl`


## live_20260626_160730

---
type: ml-model
model_name: "live"
version: "20260626_160730"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:07:30"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_160730.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_160730

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 16:07:30
- **Version:** `20260626_160730`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_160730.pkl`


## live_20260626_161034

---
type: ml-model
model_name: "live"
version: "20260626_161034"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:10:34"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_161034.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_161034

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 16:10:34
- **Version:** `20260626_161034`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_161034.pkl`


## live_20260626_173551

---
type: ml-model
model_name: "live"
version: "20260626_173551"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:35:51"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_173551.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_173551

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:35:51
- **Version:** `20260626_173551`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_173551.pkl`


## live_20260626_173759

---
type: ml-model
model_name: "live"
version: "20260626_173759"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:37:59"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_173759.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_173759

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:37:59
- **Version:** `20260626_173759`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_173759.pkl`


## live_20260626_174009

---
type: ml-model
model_name: "live"
version: "20260626_174009"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:40:09"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174009.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_174009

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:40:09
- **Version:** `20260626_174009`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174009.pkl`


## live_20260626_174445

---
type: ml-model
model_name: "live"
version: "20260626_174445"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:44:45"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174445.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_174445

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:44:45
- **Version:** `20260626_174445`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174445.pkl`


## live_20260626_174624

---
type: ml-model
model_name: "live"
version: "20260626_174624"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:46:24"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174624.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_174624

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:46:24
- **Version:** `20260626_174624`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174624.pkl`


## live_20260626_174837

---
type: ml-model
model_name: "live"
version: "20260626_174837"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:48:37"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174837.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_174837

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:48:37
- **Version:** `20260626_174837`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_174837.pkl`


## live_20260626_175431

---
type: ml-model
model_name: "live"
version: "20260626_175431"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 17:54:31"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_175431.pkl"
file_hash: "3ff8fb8dbc7760d221a297bf2189cc2f"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260626_175431

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-26 17:54:31
- **Version:** `20260626_175431`
- **Total Features:** 0
- **File Hash:** `3ff8fb8dbc77...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260626_175431.pkl`


## live_20260627_130006

---
type: ml-model
model_name: "live"
version: "20260627_130006"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-27 13:00:06"
model_type: "XGBClassifier"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260627_130006.pkl"
file_hash: "c7b0711e7054954263046f058ecb3f11"
feature_importance_top10: []
feature_count: 0
tags:
  - ml-model
  - live
  - trading
---

# live — 20260627_130006

> ML model trained on `XGBClassifier` for `live` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** XGBClassifier
- **Trained:** 2026-06-27 13:00:06
- **Version:** `20260627_130006`
- **Total Features:** 0
- **File Hash:** `c7b0711e7054...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_live_20260627_130006.pkl`


## NAS100_20260626_160329

---
type: ml-model
model_name: "NAS100"
version: "20260626_160329"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:03:29"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_NAS100_20260626_160329.pkl"
file_hash: "98d2b4e1508586313395416de7c7f66e"
feature_importance_top10: []
feature_count: 17
tags:
  - ml-model
  - NAS100
  - trading
---

# NAS100 — 20260626_160329

> ML model trained on `unknown` for `NAS100` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 2026-06-26 16:03:29
- **Version:** `20260626_160329`
- **Total Features:** 17
- **File Hash:** `98d2b4e15085...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_NAS100_20260626_160329.pkl`


## US30_20260626_160329

---
type: ml-model
model_name: "US30"
version: "20260626_160329"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:03:29"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_US30_20260626_160329.pkl"
file_hash: "393f50dc32b8c35141bdb9e12fcabc0f"
feature_importance_top10: []
feature_count: 17
tags:
  - ml-model
  - US30
  - trading
---

# US30 — 20260626_160329

> ML model trained on `unknown` for `US30` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 2026-06-26 16:03:29
- **Version:** `20260626_160329`
- **Total Features:** 17
- **File Hash:** `393f50dc32b8...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_US30_20260626_160329.pkl`


## XAUUSD_20260626_160329

---
type: ml-model
model_name: "XAUUSD"
version: "20260626_160329"
accuracy: 0.0000
precision: 0.0000
recall: 0.0000
f1_score: 0.0000
oos_accuracy: 0.0000
trained_date: "2026-06-26 16:03:29"
model_type: "unknown"
training_samples: 0
model_path: "C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_XAUUSD_20260626_160329.pkl"
file_hash: "02e33d9350b3fcd93434d33f5c54bf98"
feature_importance_top10: []
feature_count: 17
tags:
  - ml-model
  - XAUUSD
  - trading
---

# XAUUSD — 20260626_160329

> ML model trained on `unknown` for `XAUUSD` signal prediction.

## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | 0.0000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1 Score | 0.0000 |
| OOS Accuracy | 0.0000 |
| Training Samples | 0 |

## Top 10 Feature Importance

| Rank | Feature | Importance |
|------|---------|------------|

## Details

- **Model Type:** unknown
- **Trained:** 2026-06-26 16:03:29
- **Version:** `20260626_160329`
- **Total Features:** 17
- **File Hash:** `02e33d9350b3...`
- **Source:** `C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models\xgboost_XAUUSD_20260626_160329.pkl`



# PART 5: TRADE JOURNAL


## 2026-06-25

---
type: trade-journal
date: 2026-06-25
total_trades: 3
daily_pnl: 35.00
win_rate: 66.7%
generated: 2026-06-26 23:48:19
---

# Trade Journal - 2026-06-25

> 3 trades  |  P&L **GREEN +35.00**  |  Win rate **66.7%**

## Daily Summary

| Metric | Value |
|--------|-------|
| Total trades | 3 |
| Winners | 2 |
| Losers | 1 |
| Daily P&L | +35.00 |
| Win rate | 66.7% |
| Best trade | XAUUSD GREEN +41.25 |
| Worst trade | XAUUSD RED -18.75 |

## Strategy Breakdown

| Strategy | Trades | P&L | Win Rate |
|----------|--------|-----|----------|
| mean_reversion | 1 | +12.50 | 100% |
| trend_following | 2 | +22.50 | 50% |

## Trade Log

| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |
|---|--------|-----|-------|------|--------|-------|-----|----------|
| 1 | XAUUSD | LONG | 08:15 | 10:30 | 3310.50 | 3318.75 | GREEN +41.25 | trend_following |
| 2 | XAUUSD | SHORT | 13:00 | 14:45 | 3322.00 | 3319.50 | GREEN +12.50 | mean_reversion |
| 3 | XAUUSD | LONG | 16:00 | 17:30 | 3319.00 | 3315.25 | RED -18.75 | trend_following |

## Best Trade

- **XAUUSD** LONG - P&L: GREEN +41.25 (0.25%)
- Strategy: trend_following  |  Regime: trending_up
- Entry: 2026-06-25 08:15 @ 3310.50
- Exit: 10:30 @ 3318.75

## Worst Trade

- **XAUUSD** LONG - P&L: RED -18.75 (-0.12%)
- Strategy: trend_following  |  Regime: trending_up
- Entry: 2026-06-25 16:00 @ 3319.00
- Exit: 17:30 @ 3315.25

## Regime Distribution

- **trending_up**: 2 trades
- **range_bound**: 1 trades


## 2026-06-26

---
type: trade-journal
date: 2026-06-26
total_trades: 1
daily_pnl: 0.00
win_rate: 0%
generated: 2026-06-27 16:30:08
---

# Trade Journal - 2026-06-26

> 1 trades  |  P&L **RED 0.00**  |  Win rate **0%**

## Daily Summary

| Metric | Value |
|--------|-------|
| Total trades | 1 |
| Winners | 0 |
| Losers | 1 |
| Daily P&L | +0.00 |
| Win rate | 0% |
| Best trade | XAUUSD RED 0.00 |
| Worst trade | XAUUSD RED 0.00 |

## Strategy Breakdown

| Strategy | Trades | P&L | Win Rate |
|----------|--------|-----|----------|
| unknown | 1 | +0.00 | 0% |

## Trade Log

| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |
|---|--------|-----|-------|------|--------|-------|-----|----------|
| 1 | XAUUSD | long | 13:43 | -- | 4060.11 | 0 | RED 0.00 |  |

## Best Trade

- **XAUUSD** long - P&L: RED 0.00 (0%)
- Strategy:   |  Regime:
- Entry: 2026-06-26 13:43 @ 4060.11
- Exit:  @ 0

## Regime Distribution

- **unknown**: 1 trades


## 2026-06-26_original_backup

---
type: trade-journal
date: 2026-06-26
total_trades: 1
daily_pnl: 0.00
win_rate: 0.0%
generated: 2026-06-27 15:34:20
---

# Trade Journal — 2026-06-26

> 1 trades  |  P&L **🔴 0.00**  |  Win rate **0.0%**

## Daily Summary

| Metric | Value |
|--------|-------|
| Total trades | 1 |
| Winners | 0 |
| Losers | 1 |
| Daily P&L | +0.00 |
| Win rate | 0.0% |
| Best trade | XAUUSD 🔴 0.00 |
| Worst trade | XAUUSD 🔴 0.00 |

## Strategy Breakdown

| Strategy | Trades | P&L | Win Rate |
|----------|--------|-----|----------|
| unknown | 1 | +0.00 | 0% |

## Trade Log

| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |
|---|--------|-----|-------|------|--------|-------|-----|----------|
| 1 | XAUUSD | long | 13:43 | — | 4060.11000 | 0.00000 | 🔴 0.00 |  |

## Best Trade

- **XAUUSD** long — P&L: 🔴 0.00 (+0.00%)
- Strategy:   |  Regime:
- Entry: 2026-06-26 13:43 @ 4060.11000
- Exit: open

## Regime Distribution

- **unknown**: 1 trades


## 2026-06-27

---
type: trade-journal
date: 2026-06-27
total_trades: 1
daily_pnl: 20.00
win_rate: 100%
generated: 2026-06-26 23:48:19
---

# Trade Journal - 2026-06-27

> 1 trades  |  P&L **GREEN +20.00**  |  Win rate **100%**

## Daily Summary

| Metric | Value |
|--------|-------|
| Total trades | 1 |
| Winners | 1 |
| Losers | 0 |
| Daily P&L | +20.00 |
| Win rate | 100% |
| Best trade | GBPUSD GREEN +20.00 |
| Worst trade | GBPUSD GREEN +20.00 |

## Strategy Breakdown

| Strategy | Trades | P&L | Win Rate |
|----------|--------|-----|----------|
| breakout | 1 | +20.00 | 100% |

## Trade Log

| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |
|---|--------|-----|-------|------|--------|-------|-----|----------|
| 1 | GBPUSD | LONG | 08:00 | 10:00 | 1.2710 | 1.2735 | GREEN +20.00 | breakout |

## Best Trade

- **GBPUSD** LONG - P&L: GREEN +20.00 (0.20%)
- Strategy: breakout  |  Regime: trending
- Entry: 2026-06-27 08:00 @ 1.2710
- Exit: 10:00 @ 1.2735

## Regime Distribution

- **trending**: 1 trades



# PART: RISK MANAGEMENT


## dashboard

---
type: risk-dashboard
last_updated: 2026-06-27 09:30:08 UTC
drawdown_pct: 0
circuit_breaker: CLOSED
kill_switch: DISENGAGED
source: ledger
---

# Risk Dashboard

> Generated: 2026-06-27 09:30:08 UTC | Trade date: 2026-06-27

## Core Limits

| Metric | Current | Limit | Headroom | Status |
|--------|---------|-------|----------|--------|
| Drawdown | 0.00% | 15% | 15.0% | [OK] |
| Daily P&L | $0.00 | 2% loss cap | 0% used | [OK] |
| Weekly P&L | $0.00 | 5% loss cap | -- | -- |
| Open Positions | 0 | 5 | 5 slots | [OK] |

## Circuit Breaker

| Field | Value |
|-------|-------|
| Status | [OFF] |
| State | CLOSED |
| Reason | None |
| Consecutive Losses | 0 |
| Error Rate | 0.0% |

## Kill Switch

| Field | Value |
|-------|-------|
| Status | [DISENGAGED] |
| Reason | N/A |
| Activated At | N/A |

## Exposure

| Metric | Value | Limit |
|--------|-------|-------|
| Gross Exposure | $0.00 | 50% of capital |
| Net Exposure | $0.00 | -- |
| Long Exposure | $0.00 | -- |
| Short Exposure | $0.00 | -- |

### Exposure by Symbol

| Symbol | Direction | Value | % of Capital |
|--------|-----------|-------|--------------|
| (no positions) | -- | $0.00 | 0.0% |

## Direction Summary

- **Net bias:** Flat ($0.00)

## Correlation Risk

| Pair | Correlation | Risk |
|------|-------------|------|
| (no pairs) | -- | -- |

> Threshold: 0.7 -- Pairs above are correlated.

## Risk Budget

`
.................... 0.0%
`

| Component | Utilization |
|-----------|-------------|
| Drawdown budget | 0.0% |
| Daily loss budget | 0% |
| Position slots | 0.0% |
| **Total budget** | **0.0%** |

## Trade Activity

| Metric | Value |
|--------|-------|
| Orders Today | 0 |
| Trades Today | 0 |
| Consecutive Losses | 0 |

---
*Auto-generated by risk-dashboard.ps1 -- Pipeline 7: Risk Dashboard to Vault*



# PART: REGIME DETECTION


## current

---
type: regime
current_regime: UNCLEAR
confidence: 0.5
adx: 5.636985433729284
atr_state: NORMAL
affected_strategies: []
sizing: 0.3
synced: 2026-06-27 15:33
---

# [UNKNOWN] Current Regime: UNCLEAR

> **Confidence:** 50% | **ADX:** 5.6 | **ATR:** NORMAL
> **Spread:** NORMAL | **Reason:** `ADX_LOW(6) | SLOPE_UP | ATR_NORMAL`
> **Last sync:** 2026-06-27 15:33

---

## Strategy Recommendations

### Enabled Strategies
- _None_

### Disabled Strategies
- [ ] all

---

## Position Sizing

| Level | Adjustment |
|-------|-----------|
| Current | **MINIMAL** (30% of base) |
| ATR State | NORMAL |
| Spread | NORMAL |

---

## Historical Regime Distribution (Last 30 Days)

| Regime | Days | % | Distribution |
|--------|------|---|-------------|
| RANGE | 15d | 50% | ########## |
| TREND_UP | 8d | 27% | ##### |
| TREND_DOWN | 5d | 17% | ### |
| UNCLEAR | 2d | 7% | # |

---

## Recent Regime Transitions

| Date | Transition | Confidence |
|------|-----------|------------|
| 2026-06-27 | RANGE → UNCLEAR | 50% |

---

## Decision Checklist

- [ ] Confirm regime aligns with timeframe (M15)
- [ ] Check spread state before entry
- [ ] Verify enabled strategies match current regime
- [ ] Apply sizing adjustment to risk calculator
- [ ] Log regime in trade journal



# PART: SIGNAL QUALITY


## 2026-06-26

---
type: signal-quality
date: 2026-06-26
overall_accuracy: 0.00%
best_strategy: N/A
---

# Signal Quality Report — 2026-06-26

## Overview

| Metric | Value |
|--------|-------|
| Total Signals | 1 |
| Wins | 0 |
| Losses | 0 |
| Pending | 1 |
| Overall Accuracy | 0.00% |
| Config | B2 (conf≥0.85, stop $6.30) |
| Symbol | XAUUSD |

## Strategy Breakdown

| Strategy | Total | Wins | Losses | Accuracy | Avg PnL | Total PnL |
|----------|-------|------|--------|----------|---------|-----------|
| default | 1 | 0 | 0 | 0.00% | 0.00 | 0.00 |

## Confidence Distribution

| Bucket | Count | Accuracy |
|--------|-------|----------|
| low | 1 | 0.00% |

## Time-of-Day Performance

| Hour | Signals | Accuracy |
|------|---------|----------|

## Feature Drift Detection

- **Drift Detected**: No
- First Half Accuracy: 0.00%
- Second Half Accuracy: 0.00%
- Drift Magnitude: 0.00%

## Threshold Optimization Suggestions

1. Overall accuracy below 50% — review signal generation logic

## Trade Log

| Time | Dir | Entry | Exit | PnL | Outcome | Conf |
|------|-----|-------|------|-----|---------|------|
| 2026-06-26 13:43 | long | 4060.11 | — | — | pending | 0.50 |

---
*Generated: 2026-06-26 23:58 by Pipeline 9 — Signal Quality Tracker*

## 2026-06-26_precision

---
type: signal-quality
date: 2026-06-26
overall_accuracy: 0.00%
best_strategy: default
---

# Signal Quality Analysis — 2026-06-26

## Precision / Recall / F1 per Strategy

| Strategy | Signals | Wins | Precision | Recall | F1 | Avg Conf | Total PnL |
|----------|---------|------|-----------|--------|-----|----------|-----------|
| default | 1 | 0 | 0.00% | 0.00% | 0.000 | 0.50 | 0.00 |

## Confidence Band Analysis

| Band | Signals | Precision | Win Rate |
|------|---------|-----------|----------|
| 0.50–0.59 | 1 | 0.00% | 0.00% |

## Key Findings

- **Best Strategy (F1)**: default (0.000)
- **Overall Precision**: 0.00%
- **Total Signals Evaluated**: 1

## Recommendations

- No critical issues detected — continue monitoring

---
*Generated: 2026-06-26 23:44 by Pipeline 9 — Signal-to-Vault*

## 2026-06-27

---
type: signal-quality
date: 2026-06-27
overall_accuracy: 0.00%
best_strategy: N/A
---

# Signal Quality Report — 2026-06-27

## Overview

| Metric | Value |
|--------|-------|
| Total Signals | 1 |
| Wins | 0 |
| Losses | 0 |
| Pending | 1 |
| Overall Accuracy | 0.00% |
| Config | B2 (conf≥0.85, stop $6.30) |
| Symbol | XAUUSD |

## Strategy Breakdown

| Strategy | Total | Wins | Losses | Accuracy | Avg PnL | Total PnL |
|----------|-------|------|--------|----------|---------|-----------|
| default | 1 | 0 | 0 | 0.00% | 0.00 | 0.00 |

## Confidence Distribution

| Bucket | Count | Accuracy |
|--------|-------|----------|
| low | 1 | 0.00% |

## Time-of-Day Performance

| Hour | Signals | Accuracy |
|------|---------|----------|

## Feature Drift Detection

- **Drift Detected**: No
- First Half Accuracy: 0.00%
- Second Half Accuracy: 0.00%
- Drift Magnitude: 0.00%

## Threshold Optimization Suggestions

1. Overall accuracy below 50% — review signal generation logic

## Trade Log

| Time | Dir | Entry | Exit | PnL | Outcome | Conf |
|------|-----|-------|------|-----|---------|------|
| 2026-06-26 13:43 | long | 4060.11 | — | — | pending | 0.50 |

---
*Generated: 2026-06-27 16:30 by Pipeline 9 — Signal Quality Tracker*


# PART: ATTRIBUTION


## week-25

---
type: attribution
week: 25
year: 2026
total_pnl: 0
best_strategy: N/A
worst_strategy: N/A
generated: 2026-06-26 23:43
---

# Week 25 — No Trades

No trades recorded for this week.


## week-26

---
type: attribution
week: 26
year: 2026
total_pnl: 0.0
best_strategy: "default"
worst_strategy: "default"
generated: 2026-06-27 16:30
---

# Week 26 — Performance Attribution

## Summary

| Metric | Value |
|--------|-------|
| Total P&L | **$0.00** |
| Total Trades | 1 |
| Win Rate | 0.0% |
| Avg Win | $0.00 |
| Avg Loss | $0.00 |
| Profit Factor | ∞ |
| Expectancy | $0.00 |

## P&L by Strategy

| Metric | Trades | P&L | Avg P&L | Win Rate | Max Win | Max Loss |
| --- | --- | --- | --- | --- | --- | --- |
| default | 1 | $0.00 | $nan | 0.0% | $nan | $nan |


## P&L by Regime

| Metric | Trades | P&L | Avg P&L | Win Rate |
| --- | --- | --- | --- | --- |
| ranging | 1 | $0.00 | $nan | 0.0% | $nan | $nan |


## P&L by Session

| Metric | Trades | P&L | Avg P&L | Win Rate |
| --- | --- | --- | --- | --- |
| London | 1 | $0.00 | $nan | 0.0% | $nan | $nan |


## P&L by Day of Week

| Metric | Trades | P&L | Avg P&L | Win Rate |
| --- | --- | --- | --- | --- |
| Friday | 1 | $0.00 | $nan | 0.0% | $nan | $nan |


## P&L by Direction

| Metric | Trades | P&L | Avg P&L | Win Rate |
| --- | --- | --- | --- | --- |
| long | 1 | $0.00 | $nan | 0.0% | $nan | $nan |


## Best Trades

| Timestamp | Direction | Entry | Exit | P&L | Strategy |
| --- | --- | --- | --- | --- | --- |
| 2026-06-26 13:43 | long | 4060.11 | nan | $nan | default |


## Worst Trades

| Timestamp | Direction | Entry | Exit | P&L | Strategy |
| --- | --- | --- | --- | --- | --- |
| 2026-06-26 13:43 | long | 4060.11 | nan | $nan | default |


## Strategy Correlation Matrix

_Insufficient strategies for correlation._


## Ensemble Weight Optimization

| Strategy | Suggested Weight |
| --- | --- |
| default | 0.0% |

> Weights derived from `pnl × win_rate` normalized. Rebalance weekly.




# PART: ENSEMBLE


## week-26

---
type: ensemble-optimize
week: 26
date: 2026-06-27
current_weights: MTM=0.4, MRB=0.25, MLB=0.35
suggested_weights: MTM=0.05, MRB=0.9, MLB=0.05
---

# Ensemble Optimizer — Week 26
*Generated 2026-06-27 16:30*

## Current Weights

| Strategy | Weight |
|----------|--------|
| MTM | 40% |
| MRB | 25% |
| MLB | 35% |

## Grid Search Results (Top 20)

| # | MTM | MRB | MLB | Sharpe | PF | Win Rate | Exp Ret | Max DD | Score |
|---|-----|-----|-----|--------|-----|----------|---------|--------|-------|
| 1 **★** | 5% | 90% | 5% | 1.216 | 1.586 | 62.3% | 0.391 | 10.2% | 0.0211 |
| 2 | 10% | 85% | 5% | 1.229 | 1.595 | 62.1% | 0.393 | 10.3% | 0.0169 |
| 3 | 5% | 85% | 10% | 1.238 | 1.613 | 61.9% | 0.399 | 10.5% | 0.0133 |
| 4 | 15% | 80% | 5% | 1.242 | 1.603 | 61.8% | 0.395 | 10.4% | 0.0128 |
| 5 | 10% | 80% | 10% | 1.251 | 1.622 | 61.6% | 0.401 | 10.6% | 0.0092 |
| 6 | 20% | 75% | 5% | 1.256 | 1.611 | 61.6% | 0.397 | 10.6% | 0.0086 |
| 7 | 5% | 80% | 15% | 1.260 | 1.641 | 61.4% | 0.407 | 10.7% | 0.0056 |
| 8 | 15% | 75% | 10% | 1.264 | 1.631 | 61.4% | 0.403 | 10.7% | 0.0050 |
| 9 | 25% | 70% | 5% | 1.270 | 1.620 | 61.3% | 0.399 | 10.7% | 0.0045 |
| 10 | 10% | 75% | 15% | 1.273 | 1.649 | 61.2% | 0.409 | 10.8% | 0.0015 |
| 11 | 20% | 70% | 10% | 1.278 | 1.639 | 61.1% | 0.405 | 10.8% | 0.0009 |
| 12 | 30% | 65% | 5% | 1.283 | 1.629 | 61.1% | 0.401 | 10.8% | 0.0003 |
| 13 | 5% | 75% | 20% | 1.282 | 1.669 | 61.0% | 0.416 | 11.0% | -0.0022 |
| 14 | 15% | 70% | 15% | 1.286 | 1.658 | 60.9% | 0.411 | 11.0% | -0.0027 |
| 15 | 25% | 65% | 10% | 1.292 | 1.647 | 60.9% | 0.407 | 11.0% | -0.0033 |
| 16 | 35% | 60% | 5% | 1.296 | 1.637 | 60.8% | 0.403 | 10.9% | -0.0038 |
| 17 | 10% | 70% | 20% | 1.295 | 1.677 | 60.7% | 0.418 | 11.1% | -0.0063 |
| 18 | 20% | 65% | 15% | 1.300 | 1.667 | 60.7% | 0.413 | 11.1% | -0.0069 |
| 19 | 30% | 60% | 10% | 1.305 | 1.656 | 60.6% | 0.409 | 11.1% | -0.0074 |
| 20 | 40% | 55% | 5% | 1.310 | 1.645 | 60.6% | 0.405 | 11.1% | -0.0080 |

*Tested 171 weight combinations (step=0.05)

## Optimal Weights

- **MTM**: 5%  (was 40%)
- **MRB**: 90%  (was 25%)
- **MLB**: 5%  (was 35%)

- Sharpe: 1.216
- Profit Factor: 1.586
- Win Rate: 62.3%
- Max Drawdown: 10.2%
- Composite Score: 0.0211

## Regime-Dependent Weight Suggestions

| Regime | MTM | MRB | MLB |
|--------|-----|-----|-----|
| Trending | 45% | 18% | 37% |
| Ranging | 23% | 51% | 26% |
| Volatile | 31% | 28% | 42% |

## Impact Analysis (Current → Optimal)

| Metric | Current | Optimal | Delta |
|--------|---------|---------|-------|
| Sharpe | 1.442 | 1.216 | -0.227 |
| Profit Factor | 1.810 | 1.586 | -0.225 |
| Win Rate | 57.9% | 62.3% | +4.5% |
| Max Drawdown | 12.7% | 10.2% | -2.5% |

## Overfitting Risk

- **Level**: HIGH
- **Reason**: Optimal far from current (dist=0.797); large rebalance needed
- Distance (current→optimal): 0.7969
- Score range across all combos: 0.1317
- Peakiness: 0.0181

---

> [!warning] Overfitting Caution
> These weights are derived from backtest data on a specific historical window.
> Always validate on out-of-sample data before live deployment.
> Regime-dependent weights are heuristic estimates, not optimized values.
