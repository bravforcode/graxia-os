# Institutional-Grade Tick Pipeline — Design

Date: 2026-08-04
Status: Approved (brainstorming review)
Scope: Live MT5 collector upgrade + DuckDB query layer + INV-005 manifests + multi-source backfill + real consumers

## 1. Problem

The measurement daemon polls `get_current_tick()` (a snapshot) once per symbol per cycle.
Polling drops ticks that occur between polls — silent data loss during high-volatility
windows — and cannot support the data volumes Direction D (Funding-Rate Arbitrage,
Basis, StatArb) requires. Spawning 100 processes against one MT5 terminal is an
anti-pattern (named-pipe single-writer bottleneck, rate limits, terminal crashes).

Additionally: backtests currently use synthetic midpoint costs (Cost Mismatch 33x,
P0-B1), and there is no data-integrity gate over stored tick datasets.

## 2. Goals

1. Live tick capture with **zero tick loss** (delta-stream, not polling).
2. Institutional storage: flat per-symbol-day parquet + DuckDB query layer.
3. INV-005 data integrity: SHA-256 manifests per dataset, verified by release gate.
4. Historical backfill: Binance (funding rates + trades), Dukascopy (FX/Gold ticks),
   MT5 server history (fill-in) — 3+ years depth, idempotent and resumable.
5. Real consumers: backtest executes on real bid/ask; cost calibration re-derives
   FROM_TICKS; Trial #4002 consumes Binance funding rates; release gate verifies manifests.

## 3. Decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Scope | Full pipeline + consumers |
| 2 | Work structure | Single spec, phased implementation |
| 3 | Storage | Parquet stays physical store; DuckDB is a query layer |
| 4 | Backfill order | Binance → Dukascopy → MT5 history |
| 5 | Backfill depth | Full: 3y+, funding rates + trade ticks |
| 6 | Consumers | Backtest/calibration + Trial #4002 + release gate |
| 7 | Codebase strategy | Extend existing ecosystem; fix P1 audit findings on the tick path |

## 4. Architecture Overview

```
                        LIVE (Phase 1)
   MT5 terminal ──copy_ticks_from(delta)──► StreamCollector
   (symbol_select ×30)                       │  per-symbol:
                                             │   last_seen_msc cursor (>=)
                                             │   catch-up loop (cap 10)
                                             │   bounded dedup (sym,time_msc,bid,ask,last,vol)
                                             ▼
                                     TickRecorder (VALID/STALE/GAP/OUT_OF_ORDER, 2s gap)
                                             │
                              ┌──────────────┴──────────────┐
                              ▼                             ▼
                    MeasurementBatchProcessor        memory buffer
                    (session-day coverage, 2-pass)   (flush: 5s / 50k / day rollover)
                              │                             │
                              ▼                             ▼
                    data/coverage/{sym}_coverage.json   data/ticks/{sym}_{date}.parquet
                                                             │  atomic (tmp → replace)
                        ┌────────────────────────────────────┘
                        ▼
                        QUERY LAYER (Phase 2)
                        DuckDB (data/market_data.duckdb):
                          v_ticks            = read_parquet('data/ticks/*.parquet')
                          v_backfill_{src}   = per backfill dataset
                          v_ticks_combined   = UNION ALL of the above
                          tick_coverage_summary (PK + transactional upsert)
                        ▼
        ┌──────────────────┬───────────────┴──────┬───────────────────
        ▼                  ▼                      ▼
   Consumer A          Consumer B             Consumer C        BACKFILL (Phase 3)
   backtest/data_loader Trial #4002           release gate       Binance (funding+trades)
   (real bid/ask, P0-B1) funding-rate arb     INV-005 verify     Dukascopy (FX/Gold ticks)
        │                  │                      │              MT5 history (fill-in)
        ▼                  ▼                      ▼                      │
   cost_calibration    pre-trade gate         data/manifests/       ────┘
   (FROM_TICKS re-derive)                     (SHA-256 verify)     data/backfill/{source}/
                                                                   {sym}_{date}.parquet
```

Components (7 units, each single-purpose, testable without MT5/network):

1. `broker/mt5_gateway.py` — add `get_ticks_from(symbol, from_msc, count=10000)`
   module function wrapping `mt5.copy_ticks_from(..., COPY_TICKS_ALL)`. Read-only,
   raises `Mt5UnavailableError` on failure (existing pattern). Returns list of dicts:
   `time_msc, bid, ask, last, volume (volume_real preferred), flags`.
   **No class, no is_connected/reconnect here** — the gateway stays a thin read-only
   wrapper; connection recovery is owned by the collector loop.
2. `market_data/tick_recorder.py` — extend `TickRecord` with `time_msc: int | None`,
   `volume: float | None`, `flags: int | None` (optional, default None) so existing
   callers/tests keep working. Quality rules unchanged (2s gap / 5s stale).
3. `market_data/measurement_daemon.py` — replace polling internals with
   `StreamCollector` while keeping the `MeasurementDaemon` name, `run_once()`
   interface, and `MeasurementBatchProcessor` untouched. `tick_provider` signature
   becomes `callable(symbol, from_msc) -> list[dict]` (tests inject fakes).
4. `market_data/tick_store.py` — atomic append-once parquet writer for the flat
   layout `data/ticks/{sym}_{YYYY-MM-DD}.parquet` (write `.parquet.tmp`, then
   `os.replace`). Existing schema preserved; new columns appended.
5. `data_pipeline/storage/duckdb_store.py` — extend the existing `DuckDBStore`
   (do NOT create a new class): `register_tick_views()`, `query_ticks(symbol,
   start_msc, end_msc)` (parameterized), `upsert_coverage_summary()` (transaction +
   PRIMARY KEY). P1 fixes on the tick path: parameterized queries, wrapped
   transactions, PK on derived tables. DB path stays `data/market_data.duckdb`
   (from `core/config.py`).
6. `data_pipeline/manifest.py` — `DataManifestManager`: SHA-256 (64KB chunks),
   `update_manifest(dataset_name, files)` → `data/manifests/{dataset}_manifest.json`
   with per-file `{path (relative to repo root), size_bytes, sha256}`, plus
   `verify_manifest()` for the release gate.
7. `data_pipeline/backfill/{binance,dukascopy,mt5}.py` + `scripts/run_backfill.py`
   — backfill workers (Section 6). Consumers: `backtest/data_loader.py`,
   calibration scripts, Trial #4002 harness, `scripts/run_release_gate.py`.

## 5. Storage & Manifest (Phase 1/2)

### 5.1 Parquet layout — flat, unchanged

Keep `data/ticks/{sym}_{YYYY-MM-DD}.parquet` (flat, no hive partitioning).
Rationale: `market_data/promotion.py` hard-verifies parquet evidence paths and
`market_data/tick_store.py` / calibration readers depend on the flat naming.
Hive partitioning (`symbol=X/`) would break all of them for no benefit at
~30 symbols.

Live ticks: `data/ticks/{sym}_{date}.parquet`
Backfill: `data/backfill/{source}/{sym}_{date}.parquet` (same schema, separate
dataset dirs for audit separation and per-dataset manifests).

### 5.2 Schema — extend, don't replace

Existing columns (preserved):
`timestamp_utc, received_at_utc, symbol, bid, ask, last, spread_points, flags,
sequence_id, connection_session_id, source, data_quality`

New columns (appended): `time_msc (int64)`, `volume (float64)`, `flags_mt5 (uint32)`.

Renames are forbidden (e.g. `data_quality` → `quality_tag`) — they break readers.

### 5.3 DuckDB query layer

- Views over the parquet globs: `v_ticks`, `v_backfill_{source}`,
  `v_ticks_combined` (UNION ALL; sources are disjoint by `source` column).
- Derived table `tick_coverage_summary(symbol, date, source, total_ticks,
  valid_ticks, stale_ticks, gap_ticks, out_of_order_ticks, updated_at,
  PRIMARY KEY (symbol, date, source))` — transactional upsert.
- `query_ticks(symbol, start_msc, end_msc)` uses **parameterized queries**
  (P1 SQL-injection fix on the tick path).
- View names in consumer code come from a fixed whitelist mapping, never from
  user input (prevents view injection).

### 5.4 INV-005 manifests

`data/manifests/{dataset}_manifest.json`:
```json
{
  "dataset": "ticks",
  "generated_at": "2026-08-04T12:00:00Z",
  "file_count": 2,
  "files": [
    {"path": "data/ticks/XAUUSD_2026-08-04.parquet", "size_bytes": 12345, "sha256": "..."}
  ]
}
```
- Paths relative to repo root (not `parents[2]` — fragile).
- Live daemon updates the `ticks` manifest on each flush; backfill workers update
  per-dataset manifests and also record the upstream checksum (Binance publishes
  `.CHECKSUM` files — verify before conversion).

## 6. Live Collector (Phase 1)

Per cycle (`run_once`), per symbol:

1. `from_msc = last_seen_msc[symbol]` (cursor uses `>=` so same-ms ticks are never
   dropped; duplicates are removed by the dedup key, not the cursor).
2. `get_ticks_from(symbol, from_msc)` — **catch-up loop**: if the returned batch
   reaches the count limit, fetch again from the new cursor until caught up
   (safety cap ~10 iterations; log if the cap is hit).
3. **Bounded dedup window**: keep composite keys `(symbol, time_msc, bid, ask,
   last, volume)` for ticks with `time_msc >= current cycle from_msc`. Purge older
   keys each cycle. Never call `clear()` mid-stream (that reintroduces duplicates
   at the overlap boundary).
4. Feed each new tick through `TickRecorder.record_tick(..., time_msc=...,
   volume=..., flags=...)` → `TickRecord`. GAP/STALE/OUT_OF_ORDER tagging stays
   entirely with the existing TickRecorder (2s/5s thresholds) — no separate gap
   logic in the collector. A collector outage followed by resume naturally
   produces GAP tags on the time jump.
5. TickRecords go to `MeasurementBatchProcessor` every cycle (coverage updates
   continuously) and to the memory buffer for parquet flush.
6. Flush triggers: cadence 5s, buffer size 50k ticks, or day rollover (finalize
   previous day file, then start the new day buffer).
7. `Mt5UnavailableError` → exponential backoff (1s, 2s, 4s, 8s … max 30s), retry
   from the same cursor — no ticks lost.

## 7. Backfill (Phase 3)

Workers share one pipeline: enumerate/download → verify upstream checksum →
convert to parquet (atomic, flat layout, same schema) → register DuckDB view →
update manifest. Idempotent: skip existing `{sym}_{date}.parquet`; progress is
per-symbol; a crashed run resumes without re-downloading.

| Worker | Source | Data | Notes |
|--------|--------|------|-------|
| `binance.py` | `data.binance.vision` (public S3) | Funding rates (8h, 3y, USD-M perps: BTCUSDT, ETHUSDT, SOLUSDT + majors); trade ticks (3y) | `source=binance_funding` / `binance_trade`; verify `.CHECKSUM` files |
| `dukascopy.py` | datafeed.dukascopy.com (bi5, LZMA) | Tick bid/ask for XAUUSD, EURUSD, GBPUSD, USDJPY, US30 (BTCUSD unavailable on Dukascopy — skip with note) | stdlib `lzma` + `struct`, no new dependency |
| `mt5.py` | `copy_ticks_range()` | Whatever depth the terminal/broker serves (fill-in) | `source=mt5_history` |

CLI: `python scripts/run_backfill.py --source binance --dataset funding
--start 2023-08-01 --end 2026-08-01 [--symbols ...]`

## 8. Consumers (Phase 4)

### Consumer A — Execution realism

- `backtest/data_loader.py`: add `load_real_ticks(symbol, start, end)` reading
  real bid/ask via the DuckDB whitelisted views (`v_ticks` → backfill fallback),
  parameterized. Backtest uses real bid/ask where tick data exists; midpoint
  fallback only when no ticks are available (P0-B1 fix).
- Cost calibration: re-derive `FROM_TICKS` spread/commission from stored ticks
  (live + Dukascopy) and update `config/cost_calibration.json`.

### Consumer B — Trial #4002 (Funding-Rate Arbitrage)

- Harness reads funding rates via `v_backfill_binance_funding`; follows the
  pre-registration → harness → ledger/registry flow used by trial 1033.

### Consumer C — Release gate INV-005

- `scripts/run_release_gate.py` gains `check_data_integrity_inv005()`:
  - No `data/manifests/` → WARN + pass (nothing declared yet).
  - For every `*_manifest.json`: every declared file must exist, `size_bytes`
    must match, and recomputed SHA-256 must match — any mismatch = FAIL
    (fail-closed on declared datasets).

## 9. Error Handling & Edge Cases

| Case | Handling |
|------|----------|
| Same-ms ticks during volatility | cursor `>=` + composite dedup key |
| Batch overflow (news spikes) | catch-up loop until caught up, cap 10 |
| Parquet flush vs DuckDB read race | atomic write (tmp → replace); views only ever see complete files |
| MT5 connection loss | exponential backoff, resume from cursor (no loss) |
| Quiet market (no ticks) | no-op cycle; GAP only when an actual >2s tick gap exists (TickRecorder) |
| Backfill crash mid-download | idempotent by file; resume per-symbol |
| Corrupt/missing declared data | release gate INV-005 fails |

## 10. Phasing

- **Phase 1 — Storage infra + Live collector**: TickRecord extension,
  `get_ticks_from`, tick_store atomic writer, StreamCollector (catch-up, bounded
  dedup, backoff), daemon rewiring, tests. Live collection continues with zero
  tick loss; coverage two-pass unaffected.
- **Phase 2 — Query layer + manifests**: DuckDBStore views + derived table +
  P1 fixes, DataManifestManager, daemon manifest updates.
- **Phase 3 — Backfill**: Binance (funding + trades) → Dukascopy → MT5 history;
  `run_backfill.py` CLI.
- **Phase 4 — Consumers**: data_loader real bid/ask, calibration re-derive,
  Trial #4002 harness, release gate INV-005 step.

## 11. Testing

- Unit: bounded dedup (same-ms dupes), catch-up loop (limited provider),
  backoff state machine, gateway wrapper (fake MT5), manifest SHA-256 +
  tamper detection, LZMA bi5 parsing fixture, resumability.
- Integration: `query_ticks` parameterization, view picks up newly flushed
  parquet, coverage summary upsert, release gate INV-005 pass/fail.
- Existing suite (70 tests) stays green; `tests/test_measurement_daemon.py`
  updated for the delta-provider signature.

## 12. Out of Scope (future roadmap)

- L2/L3 order-book depth ingestion
- GAP/STALE ratio alerting (webhook)
- DuckDB in-memory caching for Trial #4002 parameter grids
