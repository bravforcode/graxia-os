# Pre-Registration — Trial 8003: BTCUSD TSMOM + Yang-Zhang Vol (Direction G)

**Status:** FROZEN — 2026-08-06
**Direction G** (`reports/stopping_rule_2026_08_05.md`, ledger `research/trial_ledger_g.json`)
**Evidence:** `reports/strategy_source_research_20260806.md` — Baltas-Kosowski (SSRN 2140091) + Moreira-Muir (JF 2017)

## Hypothesis
BTCUSD time-series momentum with efficient volatility estimation (Yang-Zhang)
and vol-targeted position sizing beats the naive trend/breakout family that
failed in trials 8001 (fast H1 Donchian) — the vol-scaling overlay is the
structurally different component.

## Frozen parameters (no tuning after this point)
- Signal: 12-month lookback momentum on **H1 closes** (12m × ~730 bars/month ≈ slow; use `momentum_lookback_bars` = 24 * 730 ≈ but H1 has 730 bars/month? No — H1 = 24 bars/day × 21 days = 504 bars/month. 12m = 6048 bars. Use **D1 close** for the slow momentum signal to match the literature (Faber 10-mo MA family), execute on D1 bars.)
  - → **Signal timeframe: D1** (504 bars data available? BTCUSD D1 in duckdb: yes, 2016-2026)
- Momentum lookback: 252 D1 bars (12 months)
- Vol estimator: Yang-Zhang (efficient — Baltas-Kosowski)
- Vol targeting: scale position so target annualized vol = 20% (Moreira-Muir)
- Vol lookback: 63 D1 bars (3 months) for YZ estimator
- Direction: long when 12-mo return > 0, flat otherwise (TSMOM, no short on crypto per Direction G scope)
- Max position: 1 (engine max_positions=1)
- Data: data/market_data.duckdb BTCUSD 1d (2016-08 → 2026-08-05)

## Costs (measured, FROM_TICKS 2026-08-05)
- Spread 2.376 bps, commission 10 bps → RT 24.75 bps
- Slippage: fill_simulator_p90_points P90 = 32 pts
- Turnover expectation: LOW (slow signal, monthly rebalance) — cost impact minimal

## Gate stack (unchanged from Direction D)
p-value, WFA-OOS, WFE, DSR, PBO-CSCV, bootstrap CI, min-independent-trades.

## Provenance
Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=8003, id=DIRG-BTC-TSMOM-YZ).

## Sacred holdout
NOT used (LOCKED, Phase 4.5 only).

## Stopping-rule context
Consecutive fails: 2 (8001, 8002). Per Direction G §4.4, a 3rd consecutive
REJECT triggers research stop. This is the last trial under the current
consecutive-fail count.
