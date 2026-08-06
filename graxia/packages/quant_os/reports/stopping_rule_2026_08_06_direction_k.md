# Stopping Rule — Direction K (Crypto Pairs / Statistical Arbitrage) — Pre-Registration

**Status:** LOCKED — 2026-08-06
**Rationale for opening:** Every directional mechanism (A-J) failed; pairs
trading is structurally different (market-neutral, high-frequency, correlated
same-sector). Data available: BTCUSD_H1 + ETHUSD_H1 (50k joint bars 2020-2026,
return corr 0.83), Binance funding + tick backfill infrastructure.

## Scope

BTC/ETH pairs (log-ratio z-score; Engle-Granger) — Trial 4005. Future trials
in this direction: SOL pairs (funding data exists), BTC/ETH vol-spread, etc.

## Budget & stopping

- Budget: 8 trials, range 4005-4012
- Stop when any: 8 used, 3 months (2026-11-06), 40 research-hours,
  3 consecutive fails at same gate
- Costs: Binance taker 10 bps rt + slippage 2 bps/leg = ~14 bps rt per pair trade
- Ledger: research/trial_ledger_k.json

## Preconditions

1. Pre-registration BEFORE backtest (F27) — done 2026-08-06.
2. Registry via registry_schema.stamp_trial_entry() with provenance.
3. Sacred holdout stays LOCKED.
