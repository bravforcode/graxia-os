# PHASE 1 — DATA PIPELINE & LEAKAGE FORENSICS
*Per R1–R18. Every claim cited `file:line` or marked `[UNVERIFIED]`.*

---

## 1.1 — Data Acquisition Layer (MT5-Specific)

- **MT5 bar fetch**: `mt5_connector/connection.py:201` uses `copy_rates_range(symbol, mt5_tf, fr, to)` — date-range variant (NOT `copy_rates_from_pos`). This is the documented "more reliable" call.
- **Resolution**: OHLCV bars only via `get_bars()` (`connection.py:178`); ticks via `get_tick()` (`connection.py:160`) and `tick/mt5_tick_recorder.py` + `data/mt5_tick_ingester.py` (separate path).
- **Bar timestamp semantics**: MT5 `copy_rates_range` returns **bar open time** in field `time` (MT5 convention). `connection.py:207` stores `"time": int(r[0])`. **The code does not explicitly assert "this is bar-open time"** — it is the MT5 default and is relied on implicitly. Inconsistency risk is low but the assumption is undocumented in-code.
- **Currently-forming bar inclusion**: `get_bars()` fetches by `now = dt.utcnow()` → `to = now` (`connection.py:197-200`), so the **last returned bar MAY be the still-forming bar**. If feature computation runs on this, it is lookahead. **`[PARTIAL CONCERN]`** — depends on whether the live loop calls `get_bars` then immediately computes features on the last element (not fully traced into the live loop this phase; the backtest engine correctly uses closed bars because it iterates `i in range(1, total_bars)` on already-closed historical CSV data, `backtest/engine.py:444`).
- **MT5 server TZ vs local vs UTC**: `connection.py:197` `datetime.utcnow()`; `core/session_manager.py`, `shadow/canonical_time_authority.py`, `mql5/terminal_time_probe.mq5` exist. **Full DST/timezone reconciliation `[UNVERIFIED this phase — multiple time modules exist but their inter-consistency not traced]`** — deferred, flagged P1.

## 1.2 — Storage Layer

- Raw storage: per-symbol/timeframe CSV in `data/` (e.g. `data/XAUUSD_M1.csv`), plus `data/market_data.duckdb` and `data/market_data.duckdb.wal`.
- Mutation: CSVs are append-on-collect; `build_features.py:106,128` does `sort_values('timestamp').drop_duplicates(subset='timestamp')` on read → dedup-on-read (not on write).
- **Data versioning**: `[NONE FOUND]` — no content hash, no DVC, no manifest lock in code. `scripts/hash_data_manifests.py` exists but is a manual script; no enforcement in the pipeline. Re-running the pipeline on re-collected data can yield different results silently (Phase 19).
- **Gap handling**: `data/pipeline.py`, `data/quality_gate.py`, `data_quality` tests exist — `[not opened this phase]`. `check_data_count.py`, `check_quality.py` present. Gap-fill logic `[PARTIALLY UNVERIFIED]`.

## 1.3 — Feature Engineering Lookahead Audit

`scripts/build_features.py` (the ML feature builder) and `backtest/engine.py` indicator computation:

| Feature | Defined at | Window | `shift()`? | `rolling()`? | Closed/recursive | Lookahead risk | Verdict |
|---|---|---|---|---|---|---|---|
| `strat_ret = signal.shift(1) * returns` | `scripts/backtest_suite.py:25,38,50,64,79` | — | **YES `shift(1)`** | no | closed | **LOW if shift is correct** | shift(1) makes signal at t predict return at t → correct alignment ✓ |
| `returns = close.pct_change()` | `scripts/backtest_suite.py:24` | 1 | no | no | closed | LOW | `pct_change()` is `close[t]/close[t-1]-1` → return realized AT t, paired with `signal.shift(1)` (signal from t-1) ✓ |
| `df['signal']` (Momentum) `close > ma` | `scripts/backtest_suite.py:22` | lookback=12 | no | yes (`.rolling.mean()`) | closed | **CHECK: `center`?** | `rolling(lookback).mean()` default `center=False` → uses past only ✓ |
| EMA/RSI/ATR (engine pandas path) | `backtest/engine.py:643-650` | 9/20/50/200/14 | no | via `pandas_ta` | closed | LOW | `ta.ema/r si/atr` default trailing ✓ |
| Numba EMA/RSI/ATR | `backtest/engine.py:205-290` | as above | no | manual loops | recursive | LOW | loops use `out[i-1]` only ✓ |
| Triple-barrier label | `ml/labeling.py:60-95` | max_bars=12 | n/a | n/a | forward-looking by design | **LABEL uses future bars i+1..i+max_bars** | **Correct by construction** (label must look forward) — BUT must be joined to features at bar `i` only, never let label leak into features |

**Specific lookahead checks (per protocol 1.3):**
- `center=True` anywhere? `grep` not run repo-wide `[PARTIAL]` — but the two audited feature builders use default `center=False`. **`[NEEDS repo-wide grep to close]`** → P1.
- Same-bar lookahead (close[t] predicting return from close[t]): `scripts/backtest_suite.py:25` uses `signal.shift(1)` → avoids this ✓. But the `Momentum` signal itself is `close[t] > ma[t]` computed on bar t, then shifted to t+1 return — that is correct.
- `bfill` / `fillna(method='bfill')`: `[NOT GREP'D this phase]` → P1 verification item.
- Normalization on full dataset before split: **see 1.4**.

## 1.4 — Train/Validation/Test Boundary Leakage

- `walk_forward.py:144-180` extracts IS and OOS as **separate DataFrame slices** then runs a fresh `BacktestEngine` per fold — good isolation in principle.
- **Scaler fit location**: `[UNVERIFIED]` — `StandardScaler`/`MinMaxScaler` usage not traced into `ml/pipeline.py` / `scripts/build_features.py` this phase. **If features are normalized across the full dataset before walk-forward splitting, that is leakage.** Flagged P0-candidate pending grep.
- **Hyperparameter selection on val**: `walk_forward.py:170-172` `optimize_func(strategy, is_data, ...)` runs only on IS — correct ✓. But `is_oos_ratio` is computed per-fold and the *final* reported number is the aggregate OOS (`walk_forward.py:212-215`) — if the *aggregation method itself* was tuned, that is meta-overfit (Phase 6).
- **Same WF code for selection + reporting**: `walk_forward.py` is used for both — see Phase 6.7 (PBO/CSCV `[not computed in code found]`).

## 1.5 — Timestamp & Alignment Integrity

- Label = forward return / triple-barrier (uses bars i+1..i+max_bars, `ml/labeling.py:74`). Feature at row i + label at row i is the correct alignment **as long as the label column was built shifted**. `prepare_labeled_dataset` (`labeling.py:143-184`) assigns `df["label"] = labels` where `labels.iloc[i]` was computed from bars `i+1..i+max_bars` → label at row i already encodes future info relative to row i. **Joining feature[i] with label[i] is correct** ✓.
- Cross-source joins (`merge`/`join`/`concat`): `data/multi_source_pipeline.py`, `core/multi_source_pipeline.py` exist `[not opened]`. Economic calendar join by event-time vs event-date: `news_events/integration.py`, `events/event_provider.py` exist `[not traced]` → **P1 item**.

## 1.6 — Leakage Checklist

| Item | Status | Evidence |
|---|---|---|
| No future bar data in features | PASS (audited paths) | `backtest/engine.py:444` iterates closed bars; `backtest_suite.py:25` uses `shift(1)` |
| Rolling windows use `min_periods`, not `center=True` | PARTIAL | audited paths use `center=False`; **repo-wide grep not run** |
| Scaler fit only on training fold | UNVERIFIED | scaler usage not traced |
| Label aligned to correct future bar | PASS | `ml/labeling.py:60-95` |
| No backfill (`bfill`) in features | UNVERIFIED | grep not run |
| Bar timestamp semantics consistent | PARTIAL | MT5 default open-time assumed, not asserted in code |
| DST transitions handled | UNVERIFIED | `shadow/canonical_time_authority.py` exists, not traced |
| Unclosed bar excluded from live decisions | PARTIAL | `get_bars()` may include forming bar (`connection.py:197-200`); backtest safe |
| Calendar data joined by event time, not date | UNVERIFIED | not traced |
| No cross-fold contamination in normalization | UNVERIFIED | not traced |

## 1.7 — Multi-Account / Multi-Server Consistency

`[PARTIAL]` — Three server identities referenced (see Phase 0.4 #3): `ICMarketsSC-Demo` (config default), `Pepperstone-Demo` (.env), `Pepperstone-Demo03` (creds file). Whether research data and live data come from the same broker server is **not verifiable from code alone** — flag P1, requires developer confirmation.

## 1.8 — Holiday / Low-Liquidity Calendar Handling

`backtest/dynamic_spread_model.py:9-31` models session-dependent spread (Asian/London/NY/overlap/closed) and widens spread 21:00–00:00 UTC to 5 pips — **this is the closest thing to holiday/illiquidity handling, but it is a session-spread model, NOT a holiday calendar**. Christmas/Good Friday/Thanksgiving early-close / weekend-gap spread widening: `[NOT FOUND in code]`. The Friday-close-to-Sunday-open gap is not modeled → backtest that includes the gap transition overstates achievable fills (R-risk). Flag P2.

---

## Phase 1 — Verdict

**STATUS: PARTIAL.** Lookahead is *well-defended in the audited hot paths* (LookaheadGuard, MTF cursor, shift(1) in the suite script, conservative triple-barrier labeling). However **multiple leakage-adjacent items remain UNVERIFIED** because the relevant modules (`ml/pipeline.py` scaler fit, repo-wide `bfill`/`center=True` grep, calendar join, DST) were not opened this phase. These are P1, not P0, *unless* a scaler-fit-on-full-dataset bug is found — that would be P0. **Recommend: targeted grep + read of `ml/pipeline.py` before any paper trade.**
