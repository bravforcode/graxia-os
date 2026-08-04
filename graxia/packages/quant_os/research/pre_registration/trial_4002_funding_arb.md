# Trial #4002 Pre-Registration — Funding-Rate Arbitrage Signal Feasibility

- **Trial:** 4002
- **Track:** EXPLORATORY feasibility (not a live-readiness trial)
- **Registered:** 2026-08-04
- **Status:** PRE-REGISTERED (harness only — requires backfill data to run)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched
- **Prerequisite:** Binance funding-rate backfill (`scripts/run_backfill.py --source binance --dataset funding`)

---

## 1. Why this trial exists

Funding rates on perpetual futures are paid every 8h and can be positive
(carry). Question: is holding the perp to collect funding a *measurable*
signal source, or noise? This trial only measures the funding-rate
statistics (mean, annualized yield, positive share) from stored Binance
funding history — it does NOT claim a tradable strategy, does NOT backtest
a PnL, and makes no live-profit claim. It feeds the hypothesis pipeline
only (same discipline as all Phase-2 hypothesis feeds).

## 2. Method (FROZEN)

```
compute_funding_arb_stats(df):
    n_periods          = len(df)
    mean_funding_8h    = mean(funding_rate)
    annualized_yield_bps = mean(funding_rate) * 3 * 365 * 10_000
    positive_share     = fraction(funding_rate > 0)
    first_ts, last_ts  = min/max(timestamp_utc)
```

- **Data:** `v_backfill_binance_funding` view over
  `data/backfill/binance_funding/*.parquet` (Task 9 worker, checksum-verified)
- **Symbol:** BTCUSDT (first funding dataset; others follow)
- **Recorded:** append to `research/trial_ledger.json` **`lineage`** key only
  (NEVER `trials` — this is exploratory, not a verdict trial)

## 3. Success criteria (feasibility thresholds)

- EXPLORATORY output recorded with stats; no gate pass/fail verdict.
- A positive `annualized_yield_bps` above the cost floor (> spread bps) is
  the *signal* for a follow-up hypothesis — NOT proof of tradability.

## 4. Stopping rule

- ONE measurement per dataset refresh. No tuning.
- No live promotion. Verdict printed includes "EXPLORATORY — not live-ready proof".

## 5. What happens next if signal looks positive

File a follow-up hypothesis (perpetual-carry edge) through the normal
hypothesis pipeline with full gates (DK/DSR/WFA/cost-stress) before any
paper-trading consideration.
