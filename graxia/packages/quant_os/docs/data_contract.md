# Quant OS Data Contract

Version 1.0 — Last updated 2026-06-25

## 1. Purpose

This document defines the formal contract for all data sources, schemas, quality
expectations, naming conventions, and freshness SLAs used in the Quant OS forex
algorithmic trading system. Adherence to this contract is mandatory for all
data ingest, storage, and consumption paths. Violations must be flagged at
ingest time and rejected unless explicitly waived via override token.

Every dataset file must carry a companion manifest with SHA-256 checksum per
**INV-005** (`CONSTITUTION.md`).

---

## 2. Source Tier Classification

| Tier | Source | Description | Status | SLA |
|------|--------|-------------|--------|-----|
| 1 | MT5 Live | Real-time tick stream + order execution via MetaTrader5 Python package. Account 61547941 (Pepperstone demo). | Active | 99.5% uptime; 30s max staleness |
| 2 | Dukascopy (JForex) | Historical tick archive, 5+ year depth. Target symbols: EURUSD, GBPUSD, XAUUSD. | Planned | N/A (bulk, not real-time) |
| 3 | Alternative | News feeds, sentiment indicators, economic calendar. | Future | Best-effort |

**Tier rules:**
- Tier 1 is ground truth for live decisions. If Tier 1 is stale or missing,
  pre-trade risk gates must reject (INV-010).
- Tier 2 is the training/backtest corpus. Never used for live pricing.
- Tier 3 enriches but never overrides Tier 1 signals.

---

## 3. Naming Conventions

### 3.1 File Names

Pattern:

    {source}_{symbol}_{granularity}_{date}.{ext}

Examples:

    mt5_EURUSD_tick_20260624.csv
    dukascopy_GBPUSD_tick_20220101.parquet
    mt5_EURUSD_D1.csv
    mt5_XAUUSD_M15.csv

If source is unambiguous from the directory, the `{source}_` prefix may be
omitted for backward compatibility with legacy files.

### 3.2 Directory Layout

```
data/
    {symbol}_{timeframe}.csv                          # OHLCV (existing)
    manifests/
        {symbol}_{timeframe}.manifest.json             # SHA-256 manifest (preferred)
        {symbol}_{timeframe}_manifest.json              # Legacy variant, accepted
artifacts/
    tick_data/
        {symbol}_ticks_{YYYYMMDD}.parquet               # Daily tick store
    mega_data/
        ticks/
            {symbol}_bulk.csv                           # Bulk tick collection
        orders/
            batch_{YYYYMMDD}_{HHMMSS}.csv               # Order execution batches
            batch_{YYYYMMDD}_{HHMMSS}.parquet
        dataset/
            training_{YYYYMMDD}_{HHMMSS}.csv             # ML training snapshots
            dataset_summary.json
    fill_samples_fixed/
        fill_samples_{symbol}_{timeframe}.csv            # Fill simulation outputs
        fill_summary_{symbol}.json
    backtest_cost/
        backtest_{symbol}_{timeframe}.json               # Cost backtest results
    walk_forward/
        wf_{symbol}_{timeframe}_{params}.json             # Walk-forward results
```

### 3.3 Partition Conventions (Dukascopy Parquet)

For Tier 2 historical archives:

    year={YYYY}/month={MM}/symbol={SYMBOL}/

Partition columns in the Parquet file: `year`, `month`, `symbol`.

### 3.4 Column Naming Rules

- All column names are `snake_case`.
- Timestamp columns are named `time` (OHLCV) or `decision_time`, `send_time`
  (orders), `time` (ticks).
- Price columns: `open`, `high`, `low`, `close`, `bid`, `ask`, `last`.
- All prices in absolute terms (not pips).
- Volume is always in lots (standard: 1 lot = 100,000 units).

### 3.5 Timestamp Conventions

- **All timestamps are UTC.** No local time, no timezone offsets in stored data.
- CSV `time` column format: `YYYY-MM-DD HH:MM:SS` (e.g. `2026-06-22 00:02:00`).
- ISO 8601 with timezone: `YYYY-MM-DDTHH:MM:SS+00:00` for event timestamps
  (fill samples, orders, manifests).
- Unix epoch seconds: permitted for tick data in bulk CSV (`time` column as
  integer), but daily tick Parquet must use UTC datetime.

---

## 4. Schemas

### 4.1 OHLCV CSV

File: `data/{symbol}_{timeframe}.csv`

| Column | Type | Required | Example | Constraints |
|--------|------|----------|---------|-------------|
| time | string (UTC) | yes | `2007-03-20 00:00:00` | `YYYY-MM-DD HH:MM:SS` |
| open | float | yes | `1.3307` | ohlc relationship: L <= C,H,O <= H |
| high | float | yes | `1.3323` | high >= open, close, low |
| low | float | yes | `1.3268` | low <= open, close, high |
| close | float | yes | `1.3317` | — |
| volume | int | yes | `6527` | non-negative integer |

**Constraints:**
- `low <= open, high, close` and `high >= open, low, close`.
- Time must be monotonically increasing.
- No duplicate timestamps per symbol+timeframe.
- Gaps > 2x the timeframe duration are flagged in the manifest.

### 4.2 Tick CSV (MT5 Bulk)

File: `artifacts/mega_data/ticks/{symbol}_bulk.csv`

| Column | Type | Required | Constraints |
|--------|------|----------|-------------|
| time | int (unix epoch) | yes | monotonic, non-negative |
| bid | float | yes | >= 0 |
| ask | float | yes | >= 0, ask >= bid |
| last | float | yes | >= 0 |
| flags | int | yes | MT5 tick flags bitmask |
| volume_real | float | yes | MT5 real volume |

**Constraints:**
- `bid >= 0`, `ask >= 0`, `ask >= bid`.
- Consecutive `time` delta > 30s is logged as a staleness flag (not rejected,
  but recorded in the daily quality report).
- Duplicate `(time, symbol)` rows are dropped on ingest, keeping the first
  occurrence.

### 4.3 Tick Parquet (Daily Store)

File: `artifacts/tick_data/{symbol}_ticks_{YYYYMMDD}.parquet`

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| time | datetime64[ns] (UTC) | yes | nanosecond precision |
| bid | float64 | yes | — |
| ask | float64 | yes | — |
| last | float64 | yes | — |
| flags | int32 | yes | MT5 flags |
| volume_real | float64 | yes | — |

Same constraints as Tick CSV.

### 4.4 Fill Samples CSV

File: `artifacts/fill_samples_fixed/fill_samples_{symbol}_{timeframe}.csv`

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| symbol | string | yes | e.g. `EURUSD` |
| decision_time | string (ISO 8601 UTC) | yes | e.g. `2026-06-22T00:02:00+00:00` |
| side | string | yes | `buy` or `sell` |
| latency_ms | int | yes | milliseconds |
| decision_price | float | yes | price at decision time |
| fill_price | float | yes | actual fill price |
| slippage_points | float | yes | fill_price - decision_price (in absolute price) |
| spread_price | float | yes | spread in absolute price |
| spread_bucket | string | yes | `tight`, `normal`, `wide` |
| vol_regime | string | yes | `low`, `medium`, `high` |
| session | string | yes | `asian`, `london`, `ny`, `overlap` |
| ms_since_last_tick | float | yes | milliseconds |

### 4.5 Order Execution CSV/Parquet

File: `artifacts/mega_data/orders/batch_{YYYYMMDD}_{HHMMSS}.csv`

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| time | int (unix epoch) | yes | execution timestamp |
| symbol | string | yes | e.g. `EURUSD` |
| side | string | yes | `buy` / `sell` |
| volume | float | yes | lots |
| price | float | yes | execution price |
| slippage | float | yes | points |
| latency_ms | int | yes | round-trip latency |
| comment | string | no | MT5 order comment |

### 4.6 Training Dataset CSV

File: `artifacts/mega_data/dataset/training_{YYYYMMDD}_{HHMMSS}.csv`

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| order_id | string (UUID) | yes | unique order identifier |
| symbol | string | yes | — |
| side | string | yes | `BUY` / `SELL` |
| volume | float | yes | lots |
| entry | float | yes | entry price |
| sl | float | yes | stop loss |
| tp | float | yes | take profit |
| send_price | float | yes | price at order send |
| slippage_points | float | yes | execution slippage |
| latency_ms | int | yes | order latency |
| close_retcode | int | yes | MT5 return code |
| hist_bid_mean | float | yes | historical bid mean |
| hist_bid_std | float | yes | historical bid std |
| hist_ask_mean | float | yes | historical ask mean |
| hist_ask_std | float | yes | historical ask std |
| hist_spread_mean | float | yes | historical spread mean |
| hist_spread_std | float | yes | historical spread std |
| hist_spread_max | float | yes | historical spread max |
| hist_tick_count | int | yes | tick count in window |
| send_time | string (ISO 8601 UTC) | yes | precise send timestamp |

---

## 5. Granularities

| Code | Meaning | Typical Bar Span | Used For |
|------|---------|------------------|----------|
| tick | Raw tick | N/A | Live execution, spread analysis |
| 1min | 1-minute OHLC | 1 minute | Fill simulation, micro strategies |
| 5min | 5-minute OHLC | 5 minutes | Cost backtest |
| M15 | 15-minute OHLC | 15 minutes | Strategy entry timing |
| H1 | 1-hour OHLC | 1 hour | Trend analysis |
| D1 | Daily OHLC | 1 day | Regime, top-down analysis |

Legacy aliases accepted: `M15 == 15min`, `H1 == 1h`, `D1 == 1d`. New
files should prefer canonical codes (`M15`, `H1`, `D1`, `1min`, `5min`,
`tick`).

---

## 6. Manifest Requirements (INV-005)

Every dataset file MUST have a companion manifest in `data/manifests/`.

### 6.1 Manifest File Name

    data/manifests/{symbol}_{timeframe}.manifest.json

Legacy variant `{symbol}_{timeframe}_manifest.json` is also accepted.

### 6.2 Manifest Schema

```json
{
    "dataset_id": "EURUSD_D1_MT5_2024_05_03_2026_06_20",
    "symbol": "EURUSD",
    "broker_symbol": "EURUSD",
    "source": "MT5",
    "timeframe": "D1",
    "timezone": "UTC",
    "first_timestamp_utc": "2024-05-03 00:00:00",
    "last_timestamp_utc": "2026-06-20 00:00:00",
    "bar_count": 50000,
    "csv_sha256": "d2606c545920d81b5d33b97a2a14772337100fc88a22a2a6f72f8b7bd89824cc",
    "column_schema": ["time", "open", "high", "low", "close", "volume"],
    "ingested_at_utc": "2026-06-20T00:00:00Z",
    "data_quality_status": "VALIDATED",
    "synthetic": false,
    "known_gaps": []
}
```

### 6.3 Manifest Fields

| Field | Required | Description |
|-------|----------|-------------|
| dataset_id | yes | Unique identifier: `{symbol}_{timeframe}_{source}_{start_date}_{end_date}` |
| symbol | yes | Trading symbol |
| broker_symbol | yes | Broker-specific symbol name (may differ from standard) |
| source | yes | Source identifier: `MT5`, `Dukascopy`, `Yahoo` |
| timeframe | yes | Granularity code |
| timezone | yes | Always `UTC` |
| first_timestamp_utc | yes | First data point timestamp |
| last_timestamp_utc | yes | Last data point timestamp |
| bar_count | yes | Number of rows/ticks |
| csv_sha256 | yes | SHA-256 hex digest of the data file |
| column_schema | yes | Ordered list of column names |
| ingested_at_utc | yes | ISO 8601 UTC ingest timestamp |
| data_quality_status | yes | `VALIDATED`, `WARNING`, `REJECTED` |
| synthetic | yes | `true` if machine-generated, `false` if real market data |
| known_gaps | yes | Array of `{start, end, reason}` objects describing known data gaps |

### 6.4 Data Quality Status Values

| Status | Meaning |
|--------|---------|
| VALIDATED | All quality gates passed |
| WARNING | Non-critical quality issues found (minor gaps, single stale tick) |
| REJECTED | Critical quality failure — dataset must not be used for any purpose |

---

## 7. Quality Gates

All data files pass through the following quality gates on ingest. Gate
failure results in `REJECTED` status unless the issue is configurable as
a warning.

### 7.1 Schema Validation

| Check | Enforcement |
|-------|-------------|
| Column count matches schema | Hard fail |
| Column names match spec | Hard fail |
| Data types parse correctly | Hard fail |
| Required columns non-null | Hard fail |

### 7.2 Range Checks

| Check | Applies To | Enforcement |
|-------|------------|-------------|
| bid >= 0, ask >= 0 | Ticks | Hard fail |
| ask >= bid | Ticks | Hard fail |
| low <= open, high, close | OHLCV | Hard fail (WARNING if within 0.1% tolerance) |
| high >= open, low, close | OHLCV | Hard fail (WARNING if within 0.1% tolerance) |
| volume >= 0 | All | Hard fail |
| price > 0 | All | Hard fail (zero or negative prices are impossible in FX) |

### 7.3 Sequence Gap Detection

| Check | Applies To | Threshold | Enforcement |
|-------|------------|-----------|-------------|
| Consecutive timestamp delta | Ticks | > 30s | Flag recorded, WARNING status |
| Consecutive timestamp delta | OHLCV 1min | > 2 min | Gap recorded in manifest |
| Consecutive timestamp delta | OHLCV M15 | > 30 min | Gap recorded in manifest |
| Consecutive timestamp delta | OHLCV H1 | > 2 hours | Gap recorded in manifest |
| Consecutive timestamp delta | OHLCV D1 | > 2 days | Gap recorded in manifest |

Gaps during known market closures (weekends, known holidays) are exempt and
logged in `known_gaps` with `reason: "weekend"` or `reason: "holiday"`.

### 7.4 Duplicate Detection

Duplicates are defined as rows with identical `(timestamp, symbol)` values.

| Applies To | Action |
|------------|--------|
| Ticks | Keep first occurrence, log count of dropped |
| OHLCV | Keep first occurrence, log count of dropped |

If duplicate count exceeds 1% of total rows, status becomes `REJECTED`.

### 7.5 Timeliness (Tier 1 Live)

| Check | Threshold | Action |
|-------|-----------|--------|
| Time since last tick | > 30s | Flag stale; log to daily quality report |
| Time since last tick | > 60s | Trigger pre-trade risk gate (INV-010) |
| No tick for entire session block | > 5 minutes | Alert; reject all orders |

---

## 8. FX Market Coverage Expectations

### 8.1 Trading Week

FX spot trades 24 hours/day from Sunday 22:00 GMT to Friday 22:00 GMT.

| Session | GMT Window | Expected Tick Density |
|---------|------------|----------------------|
| Sydney | 22:00-06:00 | Low (1-5 ticks/sec) |
| Tokyo | 00:00-08:00 | Medium (5-15 ticks/sec) |
| London | 07:00-16:00 | High (15-50+ ticks/sec) |
| New York | 12:00-21:00 | High (10-40 ticks/sec) |
| Overlap (London+NY) | 12:00-16:00 | Peak (30-100+ ticks/sec) |

### 8.2 Expected Completeness

| Symbol | Typical Weekly Tick Volume | Expected Coverage |
|--------|--------------------------|-------------------|
| EURUSD | 400k-800k | 24/5, highest liquidity |
| GBPUSD | 250k-500k | 24/5, high liquidity |
| XAUUSD | 100k-300k | 24/5, moderate liquidity, wider spreads |

### 8.3 Acceptable Gaps

- **Weekend gap**: Friday 22:00 GMT to Sunday 22:00 GMT — always expected,
  not flagged.
- **Holiday gap**: Christmas, New Year, Good Friday — flagged in `known_gaps`
  with reason `holiday`.
- **Low-liquidity gap**: > 5 seconds between ticks during Sydney session —
  logged as low-severity flag, does not affect quality status.
- **Unexpected gap**: > 30s during London/NY session — logged as WARNING;
  > 60s is REJECTED.

---

## 9. Data Freshness SLAs

| Dataset | Source | Max Age (Normal) | Max Age (Degraded) | Refresh Trigger |
|---------|--------|-------------------|--------------------|-----------------|
| Live ticks | MT5 | 30s | 60s | Continuous poll (1s interval) |
| Daily ticks | MT5 | End of trading day + 1h | End of day + 4h | Scheduler: `QuantOS-MegaCollect` daily 13:00 UTC |
| Orders | MT5 | 30s | 60s | Continuous poll |
| Fill samples | MT5 | Realtime (on fill event) | N/A | Event-driven |
| OHLCV D1 | MT5 | End of day + 1h | End of day + 6h | Daily cron |
| OHLCV H1 | MT5 | End of hour + 5min | End of hour + 15min | Hourly cron |
| OHLCV M15 | MT5 | End of bar + 2min | End of bar + 10min | Continuous bar builder |
| Training dataset | Pipeline | Per-run | N/A | On-demand |

---

## 10. Ingestion Pipeline Contract

All data ingestion must implement the following pipeline:

```
Raw source
    -> Schema validator
    -> Range checker
    -> Sequence gap detector
    -> Duplicate deduplicator
    -> Manifest generator (SHA-256, quality status)
    -> Storage writer (CSV/Parquet)
    -> Quality report log (JSON, artifacts/quality_reports/)
```

Ingestion is atomic: a dataset is either fully written with a valid manifest
or discarded entirely. Partial writes must be rolled back.

---

## 11. Cross-Reference: CONSTITUTION.md Invariants

| Invariant | Relation to Data Contract |
|-----------|--------------------------|
| INV-005 | Every dataset has manifest with SHA-256 checksum. Enforced by Section 6. |
| INV-010 | Missing/invalid/stale contract data = reject + fail closed. Enforced by Section 7.5 and pre-trade gate tie-in. |
| INV-011 | Every sizing decision bound to immutable contract_snapshot_id. Requires tick data freshness gate before snapshot capture. |

---

## 12. Appendices

### A. Symbol Canonical Names

| Symbol | Asset Class | Pip Location | Tick Size | Typical Spread (normal) |
|--------|-------------|-------------|-----------|------------------------|
| EURUSD | FX Major | 0.0001 | 0.00001 | 0.2-0.8 pips |
| GBPUSD | FX Major | 0.0001 | 0.00001 | 0.5-1.5 pips |
| XAUUSD | Commodity (Gold) | 0.01 | 0.01 | 15-40 points |

### B. Frequency Canonical Codes

| Canonical | Aliases | Bar Seconds |
|-----------|---------|-------------|
| tick | raw | 0 |
| 1min | 1m, 1_min | 60 |
| 5min | 5m, 5_min | 300 |
| M15 | 15min, 15m | 900 |
| M30 | 30min, 30m | 1800 |
| H1 | 1h, 1hour, 60min | 3600 |
| H4 | 4h, 4hour, 240min | 14400 |
| D1 | 1d, 1day, daily | 86400 |
| W1 | 1w, 1week, weekly | 604800 |

### C. Manifest Example (EURUSD D1)

```json
{
    "dataset_id": "EURUSD_D1_MT5_2007_03_20_2026_06_19",
    "symbol": "EURUSD",
    "broker_symbol": "EURUSD",
    "source": "MT5",
    "timeframe": "D1",
    "timezone": "UTC",
    "first_timestamp_utc": "2007-03-20 00:00:00",
    "last_timestamp_utc": "2026-06-19 00:00:00",
    "bar_count": 5000,
    "csv_sha256": "e9fda3574a7cdb561e327a8b01254b1d6692908fbd0af03c72e81041d79a9efa",
    "column_schema": ["time", "open", "high", "low", "close", "volume"],
    "ingested_at_utc": "2026-06-22T00:00:00Z",
    "data_quality_status": "VALIDATED",
    "synthetic": false,
    "known_gaps": [
        {"start": "2025-12-25 00:00:00", "end": "2025-12-26 00:00:00", "reason": "holiday"},
        {"start": "2026-01-01 00:00:00", "end": "2026-01-02 00:00:00", "reason": "holiday"}
    ]
}
```
