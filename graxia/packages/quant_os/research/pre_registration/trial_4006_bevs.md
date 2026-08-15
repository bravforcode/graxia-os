# Pre-Registration — Trial 4006: BTC/ETH Volume-Divergence Spread (BEVS) (Direction K)

**Status:** RESOLVED — REJECTED 2026-08-06 (dk_t=-10.25, 6331 trades — falsified)
**Direction K** (`reports/stopping_rule_2026_08_06_direction_k.md`, ledger `research/trial_ledger_k.json`)

## Hypothesis

Relative volume divergence between BTC and ETH predicts the cross-sectional
return spread: when BTC volume/vol diverges from ETH by >= 0.3 (threshold),
the lagging asset catches up over the next 5 bars. This is a **cross-sectional
crypto vol/flow** signal — different from pairs-trading (no cointegration
required; uses volume flow rather than price ratio).

## Why not pairs trading

Trial 4005 showed BTC/ETH is NOT cointegrated (beta 0.61, half-life 255 bars).
BEVS does not assume cointegration — it trades the volume-divergence spread,
a structurally different mechanism.

## Frozen parameters

- Strategy: `compute_bevs_signals` (strategies/btc_eth_vol_spread.py)
- vol_window = 15, divergence_threshold = 0.3, hold_days = 5,
  atr_period = 14, stop_atr = 2.0 (all defaults — pre-registered Trial 2003 config)
- BTCUSD_H1 + ETHUSD_H1 (50k joint bars, includes volume)
- Cost: Binance taker 10 bps rt + 4 bps slippage = 14 bps rt per pair trade
- Min trades >= 100

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
