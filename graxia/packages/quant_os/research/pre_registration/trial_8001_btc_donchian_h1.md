# Pre-Registration — Trial 8001: BTCUSD H1 Donchian Trend (Direction G)

**Status:** FROZEN — 2026-08-05
**Direction G** (`reports/stopping_rule_2026_08_05.md`, ledger `research/trial_ledger_g.json`)

## Hypothesis
BTCUSD H1 closes above the Donchian(20) channel high with volume expansion
(volume > 1.5x SMA(vol,20)) tend to continue — momentum/trend continuity is
exploitable on H1 where M15 scalping was not (trials 1034/1035 closed that
space).

## Frozen parameters (no tuning after this point)
- Entry: close > Donchian(20) high (long) / < Donchian(20) low (short)
- Filter: volume > 1.5x SMA(volume, 20)
- Exit: Chandelier/ATR trailing stop (2.5x ATR)
- R:R target: >= 1:2
- Timeframe: H1
- Instrument: BTCUSD
- Data: data/market_data.duckdb `ohlcv` (BTCUSD 1h, 2016-08 → 2026-08-05)

## Costs (measured, FROM_TICKS 2026-08-05)
- Spread: 2.376 bps (median), commission 10 bps → round trip 24.75 bps
- Slippage: fill_simulator_p90_points, P90 = 32 points (fill_samples_BTCUSD_1min.csv)
- Cost ceiling: avg win >= 3% so total friction < 5% of win

## Gate stack (unchanged from Direction D)
p-value, WFA-OOS, WFE, DSR, PBO-CSCV, bootstrap CI, min-independent-trades.

## Provenance
Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=8001, id=DIRG-BTC-DONCHIAN-H1).

## Sacred holdout
NOT used (LOCKED, Phase 4.5 only).
