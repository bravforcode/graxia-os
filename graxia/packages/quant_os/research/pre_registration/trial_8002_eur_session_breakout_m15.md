# Pre-Registration — Trial 8002: EURUSD M15 London Session Breakout (Direction G)

**Status:** FROZEN — 2026-08-05
**Direction G** (`reports/stopping_rule_2026_08_05.md`, ledger `research/trial_ledger_g.json`)

## Hypothesis
EURUSD breaking out of the Asian-session range at London open (07:00 UTC),
with volatility expansion (ATR(5)/ATR(20) > 1.25), tends to continue — the
liquidity-expansion transition is a genuine structural window, unlike the
mean-reverting noise that killed Trial 1035 (Asian range fade).

## Frozen parameters (no tuning after this point)
- Entry: breakout of Asian range (00:00–06:00 UTC) at London open (07:00 UTC)
- Filter: ATR(5)/ATR(20) > 1.25 (volatility expansion only)
- Exit: fixed R:R >= 1:1.5, or time exit at NY-session end (20:00 UTC)
- Timeframe: M15
- Instrument: EURUSD
- Data: data/market_data.duckdb `ohlcv` (EURUSD 15m, 2024-08 → 2026-08-05)

## Costs (measured, FROM_TICKS 2026-08-05)
- Spread: 0.087 bps (median), commission 7 bps → round trip 14.17 bps
- Slippage: fill_simulator_p90_points, P90 = 1 point (fill_samples_EURUSD_1min.csv)
- Filters spread widening during news (never enter into a widening spread)

## Gate stack (unchanged from Direction D)
p-value, WFA-OOS, WFE, DSR, PBO-CSCV, bootstrap CI, min-independent-trades.

## Provenance
Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=8002, id=DIRG-EUR-SESSION-BREAKOUT-M15).

## Sacred holdout
NOT used (LOCKED, Phase 4.5 only).
