# Trial #4004 Pre-Registration — Perpetual Funding Carry Edge (follow-up to #4002)

- **Trial:** 4004
- **Track:** Hypothesis pipeline (formal validation — NOT exploratory)
- **Registered:** 2026-08-05
- **Status:** PRE-REGISTERED (untested)
- **Predecessor:** Trial #4002 (EXPLORATORY, 2026-08-05) — measured
  BTCUSDT funding: 93 periods, mean 8h = 0.000061, annualized ≈ 666 bps,
  positive_share = 98.92%. Signal exceeded the cost floor (XAUUSD-style
  spread bps), so a formal hypothesis is filed per the #4002 pre-reg §5.
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched

---

## 1. Hypothesis (frozen)

Long perpetual positions (BTCUSDT + ETHUSDT) earn positive funding carry
that is statistically distinguishable from zero AFTER transaction costs,
over a >= 90 day window.

## 2. Method (frozen)

- Universe: BTCUSDT, ETHUSDT (Binance futures/um — the only funding
  datasets backfilled so far; more symbols extend this trial's scope and
  MUST be recorded as a parameter change, not silent).
- Data: `v_backfill_binance_funding` (Task 9 worker, checksum-verified).
- Stats (reuse `scripts/run_funding_arb_4002.py::compute_funding_arb_stats`):
  n_periods, mean_funding_8h, annualized_yield_bps, positive_share.
- Cost floor: per-symbol spread bps from `config/cost_calibration.json`
  (BTCUSD 2.511 bps; ETHUSD to be measured) — annualized carry must clear
  round-trip spread + 2x slippage.

## 3. Success criteria (pre-registered)

Primary:
- `annualized_yield_bps` > 2 x (round-trip spread bps + slippage bps) per symbol.
- `positive_share` > 0.95.

Secondary:
- Consistent sign across both symbols (no single-symbol fluke).
- Result recorded in `research/hypothesis_registry.json` (trial 4004) with
  full stats; verdict EXPLORATORY_STRONG / REJECTED per criteria.

## 4. Stopping rule

ONE measurement per dataset. Any criterion fails → REJECT, stop. No
tuning. No live promotion claim.

## 5. What happens next if PASS

Feasibility only — a follow-up would model holding-cost arbitrage with
slippage and funding-schedule timing on paper, through the normal shadow →
micro_live pipeline. Never a live-profit claim.
