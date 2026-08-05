# WS-A Pre-Registration — 52-Week High Momentum (George-Hwang 2004) — Trial 1032

- **Trial:** 1032
- **Track:** WS-A (replicate-published-edge) — same track as trial 1028 (MOP TSMOM)
- **Registered:** 2026-08-03
- **Status:** PRE-REGISTERED (NOT yet backtested)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched
- **Cumulative trial count entering:** 1050 (per `validation/n_trials` reconciliation)
- **Note:** Trial 1032 is post-cap (cap=1022 consumed, extended to 1042 by
  `reports/stopping_rule_2026_07_30.md`). Recorded for audit trail, same as 1028/1031.

---

## 1. Published source (faithful replication target)

> George, T.J. & Hwang, C.-Y. (2004), *"The 52-Week High and Momentum Investing,"*
> Journal of Finance 59(5), 2145–2176.
>
> Core result: a stock's proximity to its 52-week high predicts future returns better
> than past returns. A portfolio long stocks trading near their 52-week high and short
> stocks far below it earns significant positive returns (1980–2001, US equities).
> The mechanism: investors anchor on the 52-week high as a reference point; breaking
> above it resolves uncertainty and triggers positive drift (disposition-effect /
> anchoring bias).

**Why replicate here:** this is the *behavioral-anchoring* mechanism — a family
Directions A/B/C tested ~1050 times WITHOUT this specific, published, well-replicated
signal. The 52-week-high proximity signal is a distinct construction from plain TSMOM
(trial 1028, REJECTED) and cross-sectional ranking (trial 1022, REJECTED): it is a
*level-anchored* signal (price vs trailing max), not a return-based signal. One
pre-committed hypothesis, one run, frozen gates — same discipline as 1028.

## 2. Strategy specification (FROZEN)

For each symbol s, each rebalance date t:

```
    high_52w[t] = max(close[t-252 .. t-1])       # trailing 52-week high, EXCLUDING t (no lookahead)
    prox[t]     = close[t-1] / high_52w[t]       # proximity ratio (close vs 52w high), as-of prior close
    signal[t]   = +1 if prox[t] >= 0.95          # near the 52-week high → long
                  -1 if prox[t] <= 0.80          # far below the 52-week high → short
                  0 otherwise                    # middle ground → flat
```

- **Proximity thresholds (0.95 / 0.80)** are taken directly from George-Hwang's
  cross-sectional portfolio construction (near-high vs far-from-high quintile splits).
  FROZEN — no tuning.
- **Position:** long if prox ≥ 0.95, short if prox ≤ 0.80, flat otherwise.
- **Rebalance:** every 21 trading days (monthly, D1 bars) — same cadence as trial 1028.
- **Universe (independent, time-series):** `XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30`
  (7 liquid symbols, 2005→2026 via `provenance.load_provenance_checked`).
- **Equal risk per asset** via vol-target scaling (vol_target=0.10, clip [0.01, 2.0],
  21d realized vol) — identical to trial 1028 for comparability.
- **Costs:** frozen pepperstone_razor table from the 1028 harness
  (XAUUSD 0.32bps, XAGUSD 0.50, EURUSD 0.10+7, GBPUSD 0.12+7, USDJPY 0.12+7,
  NAS100 1.30, US30 0.80). EURUSD/GBPUSD loaded with `require_cost_calibration=False`
  — same caveat recorded for trial 3008: they are in `removed_assets` in
  `config/cost_calibration.json`; the 1028 harness already used this exact table and was
  accepted. Cost stress at 1.5×/2.0× multiplies the same table.
- **Data:** `load_provenance_checked` slices 2005→2026, excludes synthetic pre-inception
  backfill (see 1028 pre-reg §2.1 for the verified data hygiene).

## 3. FROZEN parameters (no tuning after backtest — pre-registration binding)

| Param | Value | Rationale |
|---|---|---|
| lookback_high | 252 (12M trailing max) | George-Hwang canonical 52-week high |
| prox_long | 0.95 | near-high quintile |
| prox_short | 0.80 | far-from-high quintile |
| rebalance_freq | 21 (1M) | monthly, D1 bars |
| vol_target | 0.10 | vol-targeting, clip [0.01, 2.0] |
| universe | 7 symbols | same as 1028 |

Frozen. If the backtest fails → REJECT and stop. No threshold tuning.

## 4. Success criteria (pre-registered BEFORE seeing any result)

Primary (gates the verdict):
- **Deflated Sharpe Ratio p < 0.05** with **N = 1050** (reconciled cumulative count,
  per `validation/n_trials.get_reconciled_n_trials`).
- **Pooled DK-test t-stat > 2.0** (`edge_search_all.run_dk_test`, verified Newey-West HAC).

Secondary (robustness, must hold for GO):
- **Jackknife:** dropping any single asset does not collapse portfolio Sharpe
  (per-asset delta < 0.5 vs full).
- **Cost-stress:** Sharpe stays positive at 1.5× and 2.0× cost multipliers.
- **Label shuffle:** pooled returns null must NOT pass (p > 0.05 → the shuffle says the
  edge is indistinguishable from noise → FAIL). A real signal must FAIL the shuffle null
  (observed result inconsistent with shuffled labels).
- **Data sufficiency — "trade" PINNED:** position change at monthly rebalance
  (entry from flat, exit to flat, long↔short flip). **Gate: ≥ 50 position changes per
  asset** over 2005–2026.

## 5. Stopping rule (single pre-registered hypothesis)

- ONE hypothesis. Run once on full 2005–2026 data through the verified harness.
- Primary criterion fails (DSR p ≥ 0.05 OR dk_t ≤ 2.0) → **REJECT**, stop. No tuning,
  no holdout peek, no "try other thresholds."
- Primary + all secondary pass → **GO** to paper/live gating (separate track).
- Sacred holdout remains LOCKED until Phase 4.5.

## 6. Why this is different from prior rejected work

- Trial 1028 (TSMOM) = return-based signal (sign of 12M return) → REJECT. This is
  **level-anchored** (proximity to trailing max) — different information set.
- Trial 1022 (cross-sectional ranking) = relative ranking across assets → REJECT. This is
  **time-series, per-asset** proximity — no ranking overlay.
- Prior work had selection bias from tuning; this is a frozen replication of a published,
  well-replicated anomaly, with DSR@1050 pre-committed.

## 7. Validation pipeline (exact commands, run AFTER sign-off)

1. Build signal per §2 (no lookahead: high_52w uses closes strictly before t; signal uses close[t-1]).
2. Run through the harness (same structure as `scripts/run_ws_a_tsmom.py`, verified costs).
3. Pooled DK-test → t-stat.
4. Deflated Sharpe with N=1050.
5. Jackknife (drop-each-asset) on portfolio Sharpe.
6. Cost-stress 1.5× / 2.0×.
7. Label-shuffle null (200 shuffles, sign-flip on pooled returns).
8. Record result in `research/hypothesis_registry.json` trial 1032.

## 8. Follow-up (SEPARATE — not blocking this trial)

If trial 1032 passes, next step is a combined WS-A portfolio (1028 TSMOM + 1032 52w-high)
to check decorrelation — separate hypothesis, separate trial, no folding into this verdict.
