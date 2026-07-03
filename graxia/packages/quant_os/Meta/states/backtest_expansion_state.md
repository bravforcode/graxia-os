# Backtest Expansion State

## Overview
Created `scripts/backtest_suite.py` — multi-strategy backtest engine testing 5 strategies across 7 symbols with regime detection.

## Strategies Implemented
1. **Momentum** — buy when price > MA(12), sell when <
2. **MeanReversion** — buy when z-score < -2.0, sell when > 2.0
3. **TrendFollow** — MA crossover (fast=10, slow=30)
4. **VolBreakout** — volatility breakout via ATR + channel
5. **RSI** — buy when RSI(14) < 30, sell when > 70

## Symbols Tested (all M15, 60k bars each)
- XAUUSD (2023-12-11 → 2026-06-26)
- EURUSD (2024-01-26 → 2026-06-26)
- GBPUSD (2024-01-26 → 2026-06-26)
- USDJPY (2024-01-26 → 2026-06-26)
- US30 (2023-12-07 → 2026-06-26)
- NAS100 (2023-12-07 → 2026-06-26)
- BTCUSD (2024-10-02 → 2026-06-26)

## Best Strategy Per Symbol
| Symbol  | Best Strategy   | Sharpe | Regime           |
|---------|----------------|--------|------------------|
| XAUUSD  | Momentum       | 1.30   | trending/normal  |
| EURUSD  | MeanReversion  | 1.62   | ranging/normal   |
| GBPUSD  | MeanReversion  | 1.07   | ranging/normal   |
| USDJPY  | TrendFollow    | 1.23   | trending/normal  |
| US30    | MeanReversion  | 0.35   | trending/low_vol |
| NAS100  | Momentum       | 0.94   | trending/low_vol |
| BTCUSD  | RSI            | 0.56   | trending/low_vol |

## Regime Detection Results
- Trending: XAUUSD, USDJPY, US30, NAS100, BTCUSD
- Ranging: EURUSD, GBPUSD
- Normal vol: XAUUSD, EURUSD, GBPUSD, USDJPY
- Low vol: US30, NAS100, BTCUSD
- No high_vol regimes detected

## Key Findings
- **EURUSD MeanReversion Sharpe=1.62** — strongest absolute result; ranging regime favors mean reversion
- **XAUUSD Momentum Sharpe=1.30** — strongest trending play with positive returns
- **USDJPY TrendFollow Sharpe=1.23** — trending regime makes trend following effective
- VolBreakout produced 0 trades on all symbols (threshold too tight for M15 data)
- MeanReversion and RSI show low win rates (~6% and ~12%) but positive Sharpe on ranging pairs — high reward:risk on few bets
- US30 and BTCUSD show weaker absolute Sharpe across all strategies

## Files Created
- `scripts/backtest_suite.py` — main backtest engine
- `results/backtest_suite_20260626_*.json` — full results dump
- `Meta/states/backtest_expansion_state.md` — this file

## Issues
- VolBreakout needs threshold tuning (current upper/lower bounds never triggered)
- No transaction cost/spread modeled (purely signal-based)
