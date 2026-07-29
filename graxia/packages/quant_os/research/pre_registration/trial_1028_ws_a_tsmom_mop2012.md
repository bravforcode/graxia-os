# WS-A Pre-Registration — Time Series Momentum (Moskowitz-Ooi-Pedersen 2012)

- **Trial:** 1028
- **Track:** WS-A (replicate-published-edge) — primary find-an-edge path
- **Registered:** 2026-07-29
- **Status:** PRE-REGISTERED (NOT yet backtested)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched

---

## 1. Published source (faithful replication target)

> Moskowitz, Ooi & Pedersen (2012), *"Time Series Momentum,"* Journal of
> Financial Economics 104(2), 228–250.
>
> Core result: for each asset, the sign of its trailing 12-month return predicts
> the next month's return. A portfolio that is long assets with positive 12M
> momentum and short assets with negative 12M momentum earns significant,
> positive Sharpe across 58 liquid futures markets (1985–2009).

This is the **most replicated anomaly in finance** (per `Meta/research/EDGE_DETECTION_DEEP_RESEARCH.md:1099`). Replicating it faithfully is the WS-A goal — NOT discovering a new edge.

## 2. Strategy specification (FROZEN)

Pure **time-series** momentum per MOP 2012 — explicitly NOT the cross-sectional
ranking variant (trial 1022, already REJECTED). Each asset is traded
independently on its own past return sign.

```
For each symbol s, each rebalance date t:
    r_12m = close[t] / close[t-252] - 1          # 12-month (252 trading-day) return
    signal = sign(r_12m)                          # +1 long, -1 short, 0 flat
    if |signal| > 0: position = signal * vol_scale
    else: flat
where vol_scale = clip(vol_target / realized_vol_21d, 0.0, 2.0)
      realized_vol_21d = rolling(21).std(pct_change) * sqrt(252)
      vol_target = 0.10
```

- **Position:** long if sign > 0, short if sign < 0, flat if exactly 0.
- **Rebalance:** every 21 trading days (monthly, D1 bars).
- **Universe (independent, time-series — NOT cross-sectional ranking):**
  `XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30`
  (7 liquid symbols, each ~20y D1 data through 2026 — sufficient per MEGA_PLAN ≥8yr rule)
- **Equal risk per asset** via vol_target scaling (matches MOP vol-targeting).
- **Data:** `data/{symbol}_D1.csv`, loaded via the **provenance-checked loader**
  `provenance.py::load_provenance_checked` (slice 2005→2026). The raw
  CSVs contain synthetic **pre-inception backfill** (EURUSD 1971, NAS100 1938,
  XAUUSD 1793 — flat O=H=L=C, placeholder volume). The loader HARD-FAILS on
  impossible dates and excludes all backfill. See §2.1.
- **Costs:** `pepperstone_razor` verified spreads + commissions from
  `config/cost_calibration.json`, applied realistically through the **verified
  BacktestEngine** (NOT the buggy pct_change×signal harness from the old
  cross-sectional script).

## 2.1 Data hygiene & provenance (BLOCK resolved before sign-off)

**Finding (2026-07-29):** the raw `*_D1.csv` files contain impossible
pre-inception rows that are synthetic backfill, not market data:

| Symbol | First raw row | Impossible? | Backfill rows excluded |
|--------|-------------|-------------|------------------------|
| XAUUSD | 1793-03-01 | gold fixed until 1971 | 1,115 before 1971 |
| XAGUSD | 1792-03-01 | silver fixed until 1971 | 2,558 before 1971 |
| EURUSD | 1971-01-04 | euro launched 1999 | 7,079 before 1999 |
| GBPUSD | 1900-03-01 | floats post-1971 | 284 before 1971 |
| USDJPY | 1971-01-04 | floats post-1971 | 0 |
| NAS100 | 1938-01-03 | Nasdaq-100 launched 1985 | 12,396 before 1985 |
| US30   | 1896-05-27 | DJIA history (kept) | 0 |

The backfill signature: flat O=H=L=C, monthly spacing, volume=0/1.0. The core
`load_csv_data` loader reads the **whole file with no date slice**, so any study
calling it directly would train momentum on two centuries of invented candles.

**Fix:** WS-A uses `provenance.py::load_provenance_checked`, which slices
to `>= 2005-01-01` and HARD-FAILS if the slice still contains impossible dates or
a synthetic tell > 10%. Verified modern slice (2005→2026) — **genuinely real, not
frozen backfill** (daily spacing, prices trend correctly):

| Symbol | rows | flat% | synth% | vol=0% | max_gap | verdict |
|--------|------|-------|--------|--------|---------|---------|
| XAUUSD | 10547 | 4.13% | 1.37% | 2.8% | 4d | OK (minor flat-day caveat) |
| XAGUSD | 5573 | 0.04% | 0.04% | 99.5% | 4d | OK (vol unavailable — see note) |
| EURUSD | 5581 | 0.00% | 0.00% | 99.7% | 4d | OK |
| GBPUSD | 5580 | 0.00% | 0.00% | 99.7% | 4d | OK |
| USDJPY | 5821 | 0.53% | 0.53% | 95.6% | 4d | OK |
| NAS100 | 5733 | 0.00% | 0.00% | 0.0% | 5d | OK (pristine) |
| US30   | 5470 | 0.04% | 0.04% | 0.0% | 5d | OK (pristine) |

- `synth%` = flat O=H=L=C with placeholder volume; all ≤1.37% (frozen backfill
  would be ~70%+). `max_gap` ≤5d rules out monthly backfill leakage.
- **Volume caveat:** FX (EUR/GBP/JPY) and XAGUSD report ~96–99.7% volume=0. This
  is expected (FX has no centralized volume; silver source omits it) and does
  **not** affect TSMOM, which uses returns + realized vol, never volume.
- **XAUUSD caveat:** 4.13% flat candles (1.37% synth) — gold has genuine
  low-range days; not frozen backfill (prices trend 428→1900+). Flagged, accepted.
- Tests: `tests/test_provenance.py` (4 tests) pin the exclusion + hard-fail contract.

## 3. FROZEN parameters (no tuning after backtest — pre-registration binding)

| Param | Value | Rationale |
|-------|-------|-----------|
| lookback | 252 (12M) | MOP canonical 12-month momentum |
| rebalance_freq | 21 (1M) | Monthly rebalance, D1 bars |
| vol_target | 0.10 | MOP vol-targeting; clipped [0,2] |
| min_signal_strength | 0.0 | Pure sign-of-return (no threshold) |
| universe | 7 symbols (above) | Independent time-series, not ranked |

These are taken from the published paper + the existing `compute_tsmom_signal`
defaults. **They are frozen. If the backtest fails, we REJECT and stop — we do
NOT tune lookback/rebalance/vol to recover a positive result.**

## 4. Success criteria (pre-registered BEFORE seeing any result)

Primary (gates the verdict):
- **Deflated Sharpe Ratio p < 0.05** with **N = 1050** (project cumulative
  trial count per `ws_b_paper_bot_revalidation` — NOT N=1).
  - **Acknowledged risk:** N=1050 is conservative and MAY reject even a genuine
    edge. This is accepted. We will NOT lower N or relax p after seeing the
    result. A real edge that fails DSR@1050 is reported as REJECT, not tuned.
- **Pooled DK-test t-stat > 2.0** (per `scripts/edge_search_cross_sectional.py` harness).

Secondary (robustness, must hold for GO):
- **Jackknife:** dropping any single asset does not collapse portfolio Sharpe
  (per-asset Sharpe delta < 0.5 vs full).
- **Cost-stress:** passes at **1.5× and 2.0×** spread/commission multipliers
  (Sharpe stays positive at 2.0×).
- **PBO (CSCV) < 0.5** (`backtest/walk_forward.py` / `validation/probability_overfitting.py`).
- **Data sufficiency — "trade" PINNED:** a *trade* = a **position change at a
  monthly rebalance** (target position sign differs from the prior rebalance's
  target: entry from flat, exit to flat, or long↔short flip). Counting monthly
  rebalances trivially passes (~252); counting only raw sign-flips may trivially
  fail (momentum persists years). Position-change counting is the meaningful
  middle. **Gate: ≥ 50 position changes per asset** over the 2005–2026 sample
  (conservative for slow TSMOM; ~12 rebalances/yr × 21y ≈ 252 opportunities,
  but sign persists so actual flips are fewer).

## 5. Stopping rule (single pre-registered hypothesis)

- ONE hypothesis. Run once on the full 2005–2026 data through the verified
  BacktestEngine + `governance/validation_stack.py` (all 7 gates).
- If **primary criterion fails** (DSR p ≥ 0.05) → **REJECT**, stop. No parameter
  tuning, no peeking at sacred holdout, no "try another lookback."
- If primary + all secondary pass → **GO** to paper/live gating (separate track).
- Sacred holdout remains LOCKED until Phase 4.5 — never opened for this decision.

## 6. Why this is different from prior rejected work

- Trial 1022 (MULTI-ASSET-TSMOM-RANKING) tested a **cross-sectional** variant
  (top_n/bottom_n ranking overlay) → REJECT (dk_t=-2.1255). WS-A is the
  **pure time-series** sign-of-return, per MOP original. Different mechanism.
- Prior edge search used a **buggy pct_change×signal harness** that dropped
  index commissions. WS-A uses the **verified BacktestEngine** with realistic
  costs. Different (correct) execution.
- Prior work had **no frozen pre-registration** → selection bias (N=1050 DSR
  exposed the 4-asset paper bot as p=0.208). WS-A pre-registers N=1050 DSR
  BEFORE running. Different (disciplined) protocol.

## 7. Validation pipeline (exact commands, run AFTER sign-off)

1. Build signal via `strategies/tsmom.py::compute_tsmom_signal` (lookback=[252],
   vol_target=0.10) — single 12M lookback (not the 3-lookback consensus).
2. Run through **verified BacktestEngine** per asset (realistic costs).
3. Pooled DK-test (`run_dk_test`) → t-stat.
4. Deflated Sharpe (`validation/deflated_sharpe.py`) with N=1050.
5. Jackknife (drop-each-asset) on portfolio Sharpe.
6. Cost-stress at 1.5× / 2.0× (`SYMBOL_SPREAD_PIPS` × multiplier).
7. PBO/CSCV (`backtest/walk_forward.py`).
8. Record result in `research/hypothesis_registry.json` trial 1028.

## 8. Follow-up (SEPARATE from WS-A — not blocking this trial)

The same contaminated CSVs fed the prior ~1050 edge-search trials. Some of those
REJECTIONS may also be on bad (pre-inception) data, not on a true absence of edge.
This is a **scoped re-check**, tracked independently — it does NOT change WS-A's
frozen params or gates, and must not be used to "rescue" a WS-A rejection.
Action: re-run the edge-search harness against `load_provenance_checked` slices
and diff which prior REJECTs flip to PASS. File under a separate trial/registry
entry when scoped.
