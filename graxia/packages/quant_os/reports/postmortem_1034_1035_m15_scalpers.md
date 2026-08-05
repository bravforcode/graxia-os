# Post-Mortem — Trials 1034/1035: M15 Scalper Benchmarks (2026-08-05)

## Status
CLOSED — both trials REJECTED on measured costs. No re-test, no tuning, per
frozen pre-registration discipline.

## Verdict summary

| Trial | ID | Instrument | PF | Sharpe | Monthly | MaxDD | Gates |
|---|---|---|---|---|---|---|---|
| 1034 | EA-BENCH-HAPPY-GOLD | XAUUSD M15 | 0.9515 | −0.6167 | −1.78% | 52.88% | 2/7 |
| 1035 | EA-BENCH-ASIAN-SCALPER | EURUSD/GBPUSD/USDJPY M15 | 0.68–0.94 | −1.78 to −4.73 | −1.75 to −3.08% | up to 60% | 2/7 |

Source: `research/hypothesis_registry.json` entries 1034/1035; runner artifact
`reports/edge_search_m15_scalper_core4.json`.

## Why they failed (structural, not cost)

1. **Cost is not the killer.** Trial 1034 ran XAUUSD at the *measured* ECN-grade
   cost: spread 0.324 bps median, commission $0, round-trip ≈ 0.65 bps
   (Pepperstone Razor, FROM_TICKS). That is cheaper than any real retail
   account — and the strategy still lost (PF 0.95).
2. **Bad risk/reward.** 43.9% win rate with average loss exceeding average win
   (M15 breakout scalper with ATR SL/TP on gold): the winner profile cannot
   overcome the loss frequency.
3. **Noise dominates M15.** FX pairs in Trial 1035 (Asian-session range fade)
   trade against mean-reverting noise without a volatility-expansion filter;
   stop losses get run over, edge is eaten by market structure, not by spread.
4. **Broker switching cannot fix this.** The broker-switch thesis (move to a
   cheaper ECN/raw-spread broker to find edge) is falsified for these two
   trials: they were already tested at raw-spread, zero/low-commission costs.

## Cost provenance (backfilled 2026-08-05)

Both registry entries now carry `cost_model_version`, `cost_source`,
`round_trip_bps_used`, `slippage_source` via
`research/backfill_trial_provenance.py`. Slippage was **not modelled** in the
runner (`slippage_pips=None`) — recorded as `slippage_source: "none"` (honest,
not faked 0.0). See provenance_note in each entry.

## Lessons for Direction G (trials 8001/8002)

- Do NOT re-attempt M15 scalping on gold/FX without a session/volatility filter
  — trials 1034/1035 close that hypothesis space.
- BTCUSD H1 Donchian trend (8001) and EURUSD M15 London-session breakout (8002)
  must carry a real fill-simulator slippage source (now available:
  `artifacts/fill_samples_fixed/fill_samples_{BTCUSD,EURUSD}_1min.csv`, P90
  32 pts / 1 pt) — never `slippage_source: "none"` for a directional claim.
- Use `research/registry_schema.stamp_trial_entry()` for all new verdicts so
  provenance is written at registration time, not backfilled later.

## Evidence files
- `reports/edge_search_m15_scalper_core4.json` (runner artifact, 2026-08-04)
- `research/hypothesis_registry.json` entries 1034/1035 (stamped 2026-08-05)
- `config/cost_calibration.json` (per-symbol measured costs used at run time)
