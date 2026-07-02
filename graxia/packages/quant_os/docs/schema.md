# Quant OS — Data Warehouse Schema

## 1. Physical Storage Layout

All warehouse data lives under `data/warehouse/`. Two partition layouts coexist:

### Hive-style partitioned Parquet (preferred)

```
data/warehouse/
  ticks/
    source=MT5/
      symbol=EURUSD/
        year=2024/
          month=06/
            data.parquet
    source=Dukascopy/
      symbol=GBPUSD/
        year=2024/
          month=06/
            data.parquet
  ohlcv/
    symbol=EURUSD/
      frequency=M15/
        year=2024/
          month=06/
            data.parquet
  orders/
    symbol=EURUSD/
      year=2025/
        month=03/
          data.parquet
  fill_samples/
    symbol=EURUSD/
      year=2025/
        month=03/
          data.parquet
  manifests/
    source=MT5/
      symbol=EURUSD/
        year=2024/
          month=06/
            manifest.parquet
    source=MT5/
      timeframe=H1/
        manifest.json
```

### Flat naming fallback (for simple consumers)

```
data/warehouse/ticks__MT5__EURUSD__2024__06.parquet
data/warehouse/ohlcv__EURUSD__M15__2024__06.parquet
data/warehouse/orders__EURUSD__2025__03.parquet
data/warehouse/fill_samples__EURUSD__2025__03.parquet
data/warehouse/manifests__MT5__EURUSD__2024__06.parquet
```

The tick storage layer (`TickStorage`) uses a broker/server/symbol/date layout for real-time ingestion:

```
data/warehouse/
  broker={broker}/
    server={server}/
      symbol={symbol}/
        date={date}/
          part-000.jsonl
          manifest.json
          sha256.txt
```

## 2. Table Schemas

### 2.1 `ticks` — Unified raw tick data (MT5 + Dukascopy)

```sql
CREATE TABLE ticks (
    time        TIMESTAMP   NOT NULL,  -- converted from unix epoch or parsed
    bid         DOUBLE      NOT NULL,
    ask         DOUBLE      NOT NULL,
    last        DOUBLE,                -- nullable; 0.0 during off-hours in MT5
    flags       INTEGER,               -- MT5 tick flags bitmask; null for Dukascopy
    volume      DOUBLE,                -- tick volume (MT5 volume_real, Dukascopy bid vol)
    ask_volume  DOUBLE,                -- Dukascopy ask-side volume; null for MT5
    spread      DOUBLE,                -- ask - bid (computed on ingest); null if missing
    source      VARCHAR     NOT NULL,  -- 'MT5' | 'Dukascopy' | 'other'
    symbol      VARCHAR     NOT NULL
)
```

| Column | Parquet Type | DuckDB Type | Nullable | Description | Example |
|---|---|---|---|---|---|
| `time` | `TIMESTAMP_MICROS` | `TIMESTAMP` | No | UTC timestamp | `2024-06-13 04:45:00` |
| `bid` | `DOUBLE` | `DOUBLE` | No | Bid price | `1.08076` |
| `ask` | `DOUBLE` | `DOUBLE` | No | Ask price | `1.08083` |
| `last` | `DOUBLE` | `DOUBLE` | Yes | Last traded price (0.0 = none) | `1.08046` |
| `flags` | `INT32` | `INTEGER` | Yes | MT5 tick flags bitmask | `134` |
| `volume` | `DOUBLE` | `DOUBLE` | Yes | Tick volume / bid volume | `0.0` |
| `ask_volume` | `DOUBLE` | `DOUBLE` | Yes | Dukascopy ask volume | `2.5` |
| `spread` | `DOUBLE` | `DOUBLE` | Yes | Computed spread in price units | `0.00007` |
| `source` | `BYTE_ARRAY` | `VARCHAR` | No | Originating source | `MT5` |
| `symbol` | `BYTE_ARRAY` | `VARCHAR` | No | Forex pair | `EURUSD` |

**Partitioning**: `source`, `symbol`, `year`, `month`
**Sorting within file**: `time ASC`

### 2.2 `ohlcv` — Resampled bars at multiple frequencies

```sql
CREATE TABLE ohlcv (
    time        TIMESTAMP   NOT NULL,  -- bar open time (UTC)
    open        DOUBLE      NOT NULL,
    high        DOUBLE      NOT NULL,
    low         DOUBLE      NOT NULL,
    close       DOUBLE      NOT NULL,
    volume      BIGINT      NOT NULL,  -- tick count within bar
    frequency   VARCHAR     NOT NULL,  -- 'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN1'
    symbol      VARCHAR     NOT NULL,
    source      VARCHAR     NOT NULL   -- 'MT5' | 'Dukascopy' | 'aggregated'
)
```

| Column | Parquet Type | DuckDB Type | Nullable | Description | Example |
|---|---|---|---|---|---|
| `time` | `TIMESTAMP_MICROS` | `TIMESTAMP` | No | Bar open timestamp (UTC) | `2024-06-13 04:45:00` |
| `open` | `DOUBLE` | `DOUBLE` | No | Open price | `1.08076` |
| `high` | `DOUBLE` | `DOUBLE` | No | High price | `1.08083` |
| `low` | `DOUBLE` | `DOUBLE` | No | Low price | `1.08040` |
| `close` | `DOUBLE` | `DOUBLE` | No | Close price | `1.08046` |
| `volume` | `INT64` | `BIGINT` | No | Tick count | `335` |
| `frequency` | `BYTE_ARRAY` | `VARCHAR` | No | Bar frequency label | `M15` |
| `symbol` | `BYTE_ARRAY` | `VARCHAR` | No | Forex pair | `EURUSD` |
| `source` | `BYTE_ARRAY` | `VARCHAR` | No | Originating source | `MT5` |

**Partitioning**: `symbol`, `frequency`, `source`, `year`, `month`
**Sorting within file**: `time ASC`

### 2.3 `orders` — Execution logs

```sql
CREATE TABLE orders (
    time                TIMESTAMP   NOT NULL,
    symbol              VARCHAR     NOT NULL,
    side                VARCHAR     NOT NULL,  -- 'buy' | 'sell'
    volume              DOUBLE      NOT NULL,  -- lot size
    requested_price     DOUBLE      NOT NULL,
    fill_price          DOUBLE      NOT NULL,
    slippage_points     DOUBLE      NOT NULL,  -- fill_price - requested_price, in points
    spread_at_entry     DOUBLE,                -- spread observed at entry time; nullable
    latency_ms          DOUBLE,                -- order submission to fill, ms; nullable
    order_type          VARCHAR,               -- 'market' | 'limit' | 'stop'; nullable
    strategy_id         VARCHAR,               -- which strategy placed the order; nullable
    broker              VARCHAR     NOT NULL,  -- 'MT5' | 'Dukascopy' | 'simulated'
    client_order_id     VARCHAR                -- broker-assigned order id; nullable
)
```

| Column | Parquet Type | DuckDB Type | Nullable | Description | Example |
|---|---|---|---|---|---|
| `time` | `TIMESTAMP_MICROS` | `TIMESTAMP` | No | Order submission timestamp | `2025-03-15 10:30:00` |
| `symbol` | `BYTE_ARRAY` | `VARCHAR` | No | Forex pair | `EURUSD` |
| `side` | `BYTE_ARRAY` | `VARCHAR` | No | Trade direction | `buy` |
| `volume` | `DOUBLE` | `DOUBLE` | No | Lot size | `0.10` |
| `requested_price` | `DOUBLE` | `DOUBLE` | No | Price at order submission | `1.08750` |
| `fill_price` | `DOUBLE` | `DOUBLE` | No | Actual fill price | `1.08753` |
| `slippage_points` | `DOUBLE` | `DOUBLE` | No | Slippage in price points | `0.00003` |
| `spread_at_entry` | `DOUBLE` | `DOUBLE` | Yes | Spread when order was placed | `0.00008` |
| `latency_ms` | `DOUBLE` | `DOUBLE` | Yes | Round-trip latency | `12.5` |
| `order_type` | `BYTE_ARRAY` | `VARCHAR` | Yes | Order type | `market` |
| `strategy_id` | `BYTE_ARRAY` | `VARCHAR` | Yes | Originating strategy | `mean_reversion_v3` |
| `broker` | `BYTE_ARRAY` | `VARCHAR` | No | Execution venue | `MT5` |
| `client_order_id` | `BYTE_ARRAY` | `VARCHAR` | Yes | Broker order identifier | `12345678` |

**Partitioning**: `symbol`, `broker`, `year`, `month`
**Sorting within file**: `time ASC`

### 2.4 `fill_samples` — Simulated fill data

```sql
CREATE TABLE fill_samples (
    time                TIMESTAMP   NOT NULL,
    symbol              VARCHAR     NOT NULL,
    side                VARCHAR     NOT NULL,  -- 'buy' | 'sell'
    volume              DOUBLE      NOT NULL,
    simulation_id       VARCHAR     NOT NULL,  -- run identifier or config hash
    fill_price          DOUBLE      NOT NULL,
    requested_price     DOUBLE      NOT NULL,
    slippage_points     DOUBLE      NOT NULL,
    spread_at_fill      DOUBLE,                -- spread observed at fill time; nullable
    latency_model       VARCHAR,               -- 'zero' | 'fixed' | 'distribution'; nullable
    tick_sequence_index BIGINT,                -- index into tick stream for reproducibility; nullable
    sigma_slippage      DOUBLE                 -- std dev of slippage in this simulation run; nullable
)
```

| Column | Parquet Type | DuckDB Type | Nullable | Description | Example |
|---|---|---|---|---|---|
| `time` | `TIMESTAMP_MICROS` | `TIMESTAMP` | No | Simulated fill timestamp | `2025-03-15 10:30:00` |
| `symbol` | `BYTE_ARRAY` | `VARCHAR` | No | Forex pair | `EURUSD` |
| `side` | `BYTE_ARRAY` | `VARCHAR` | No | Trade direction | `sell` |
| `volume` | `DOUBLE` | `DOUBLE` | No | Lot size | `0.05` |
| `simulation_id` | `BYTE_ARRAY` | `VARCHAR` | No | Simulation run hash/label | `mc_100k_v2` |
| `fill_price` | `DOUBLE` | `DOUBLE` | No | Simulated fill price | `1.08750` |
| `requested_price` | `DOUBLE` | `DOUBLE` | No | Price at order intent | `1.08748` |
| `slippage_points` | `DOUBLE` | `DOUBLE` | No | Simulated slippage | `0.00002` |
| `spread_at_fill` | `DOUBLE` | `DOUBLE` | Yes | Spread at fill from tick data | `0.00007` |
| `latency_model` | `BYTE_ARRAY` | `VARCHAR` | Yes | Latency model used | `normal` |
| `tick_sequence_index` | `INT64` | `BIGINT` | Yes | Tick index for reproducibility | `1042837` |
| `sigma_slippage` | `DOUBLE` | `DOUBLE` | Yes | Slippage std dev for this run | `0.000015` |

**Partitioning**: `symbol`, `simulation_id`, `year`, `month`
**Sorting within file**: `time ASC`

### 2.5 `manifests` — Dataset file metadata

```sql
CREATE TABLE manifests (
    sha256      VARCHAR     NOT NULL,
    rows        BIGINT      NOT NULL,
    columns     VARCHAR[],              -- column name array
    date_start  TIMESTAMP,              -- first row timestamp; nullable for ticks
    date_end    TIMESTAMP,              -- last row timestamp; nullable for ticks
    symbol      VARCHAR     NOT NULL,
    source      VARCHAR     NOT NULL,   -- 'MT5' | 'Dukascopy'
    timeframe   VARCHAR,                -- 'M15', 'H1', 'D1', etc.; null for ticks
    file_path   VARCHAR     NOT NULL,
    file_size   BIGINT,                 -- bytes; nullable
    created_at  DATE        NOT NULL
)
```

| Column | Parquet Type | DuckDB Type | Nullable | Description | Example |
|---|---|---|---|---|---|
| `sha256` | `BYTE_ARRAY` | `VARCHAR` | No | File content hash | `0eb9dd7d...` |
| `rows` | `INT64` | `BIGINT` | No | Row count | `50000` |
| `columns` | `LIST` | `VARCHAR[]` | Yes | Column names | `["time","open","high","low","close","volume"]` |
| `date_start` | `TIMESTAMP_MICROS` | `TIMESTAMP` | Yes | Dataset start | `2018-06-01 21:00:00` |
| `date_end` | `TIMESTAMP_MICROS` | `TIMESTAMP` | Yes | Dataset end | `2026-06-19 23:00:00` |
| `symbol` | `BYTE_ARRAY` | `VARCHAR` | No | Forex pair | `EURUSD` |
| `source` | `BYTE_ARRAY` | `VARCHAR` | No | Data source | `MT5` |
| `timeframe` | `BYTE_ARRAY` | `VARCHAR` | Yes | Bar frequency | `H1` |
| `file_path` | `BYTE_ARRAY` | `VARCHAR` | No | Relative warehouse path | `ticks/MT5/EURUSD/2024/06/data.parquet` |
| `file_size` | `INT64` | `BIGINT` | Yes | File size in bytes | `1048576` |
| `created_at` | `DATE` | `DATE` | No | Manifest creation date | `2026-06-22` |

**Partitioning**: `source`, `symbol`
**No further time partitioning** — manifest table is small and queried by symbol/source.

## 3. Partitioning Strategy

| Table | Partition Keys | Granularity | Rationale |
|---|---|---|---|
| `ticks` | `source`, `symbol`, `year`, `month` | Monthly | Tick volume is high; monthly keeps file sizes manageable (~100-500 MB) |
| `ohlcv` | `symbol`, `frequency`, `source`, `year`, `month` | Monthly | Bar data is smaller per partition; monthly is fine |
| `orders` | `symbol`, `broker`, `year`, `month` | Monthly | Low volume relative to ticks |
| `fill_samples` | `symbol`, `simulation_id`, `year`, `month` | Monthly | Simulations can be pruned by `simulation_id` |
| `manifests` | `source`, `symbol` | — | Small table; no time partition needed |

**Design notes**:
- Hive-style partitioning (`key=value`) is preferred for schema evolution and predicate pushdown.
- `year` and `month` are **derived** columns extracted from `time` on write.
- Partition columns are **not stored** as file columns (Parquet writer drops them); they are inferred from the directory path.
- DuckDB reads hive-partitioned data with `read_parquet('data/warehouse/ticks/**/*.parquet', hive_partitioning=true)`.

## 4. Compression

| Codec | Recommendation | Notes |
|---|---|---|
| **ZSTD** | **Default for all Parquet files** | Best compression ratio for float + integer columns; fast decompression |
| Snappy | Acceptable for temporary / staging files | Faster writes, lower compression |
| GZIP | Avoid | Slower decompression with marginal gain over ZSTD |
| Uncompressed | Never | Wasteful |

**PyArrow writer settings** (used by `convert_to_parquet.py`):

```python
pq.write_table(table, path, compression="zstd", compression_level=3)
```

- `compression_level=3` balances speed vs ratio for time-series float data.
- Use `compression_level=6` for `manifests` (small, archival) and archives.

## 5. Indexing

DuckDB does not use traditional B-tree indexes. Performance comes from:

### 5.1 Ordering (within Parquet files)

Define `ORDER BY` on write to enable min-max statistics pruning:

```python
table = table.sort_by([("time", "ascending")])
pq.write_table(table, path, compression="zstd", row_group_size=65536)
```

- **ticks**: `ORDER BY time`
- **ohlcv**: `ORDER BY time`
- **orders**: `ORDER BY time`
- **fill_samples**: `ORDER BY time`
- **manifests**: `ORDER BY symbol, date_start`

### 5.2 DuckDB Persistent Index

For the DuckDB catalog that references these Parquet files, create expression-based indexes on commonly filtered columns:

```sql
-- On the DuckDB-managed table, not on Parquet itself
CREATE INDEX idx_ticks_symbol_time ON ticks(symbol, time);
CREATE INDEX idx_ohlcv_freq_symbol_time ON ohlcv(frequency, symbol, time);
CREATE INDEX idx_orders_symbol_time ON orders(symbol, time);
CREATE INDEX idx_manifests_symbol ON manifests(symbol);
```

**Note**: DuckDB indexes only apply to data loaded into DuckDB tables (not directly on Parquet files). For pure Parquet reads, predicate pushdown leverages min-max statistics from the ordering column.

### 5.3 Row Group Size

```python
row_group_size = 65536  -- default; good for time-series
```

- Larger row groups (~262144) improve compression ratio for ticks.
- Smaller row groups (~16384) improve point-read performance for manifests.

## 6. Views

Useful DuckDB views that sit on top of the Parquet-backed tables.

### 6.1 `v_daily_ohlcv_from_ticks`

Aggregate ticks into daily bars:

```sql
CREATE OR REPLACE VIEW v_daily_ohlcv_from_ticks AS
SELECT
    symbol,
    CAST(DATE_TRUNC('day', time) AS TIMESTAMP) AS date,
    FIRST(bid)  AS open,
    MAX(bid)    AS high,
    MIN(bid)    AS low,
    LAST(bid)   AS close,
    COUNT(*)    AS tick_count,
    SUM(volume) AS volume
FROM ticks
WHERE source = 'MT5'
GROUP BY symbol, DATE_TRUNC('day', time)
ORDER BY symbol, date;
```

### 6.2 `v_daily_ohlcv_unified`

Union unified ticks and existing OHLCV, preferring aggregated ticks:

```sql
CREATE OR REPLACE VIEW v_daily_ohlcv_unified AS
SELECT symbol, date, open, high, low, close, tick_count AS volume, 'ticks' AS source
FROM v_daily_ohlcv_from_ticks
UNION ALL
SELECT symbol, time, open, high, low, close, volume, source
FROM ohlcv
WHERE frequency = 'D1'
ORDER BY symbol, date;
```

### 6.3 `v_spread_stats`

Spread analysis from ticks:

```sql
CREATE OR REPLACE VIEW v_spread_stats AS
SELECT
    symbol,
    DATE_TRUNC('hour', time) AS hour,
    COUNT(*)                  AS tick_count,
    AVG(ask - bid)            AS mean_spread,
    MIN(ask - bid)            AS min_spread,
    MAX(ask - bid)            AS max_spread,
    STDDEV(ask - bid)         AS std_spread
FROM ticks
GROUP BY symbol, DATE_TRUNC('hour', time)
ORDER BY symbol, hour;
```

### 6.4 `v_order_performance`

Order execution quality summary:

```sql
CREATE OR REPLACE VIEW v_order_performance AS
SELECT
    symbol,
    strategy_id,
    DATE_TRUNC('day', time) AS day,
    COUNT(*)                AS order_count,
    AVG(slippage_points)    AS avg_slippage,
    AVG(latency_ms)         AS avg_latency_ms,
    AVG(spread_at_entry)    AS avg_spread
FROM orders
GROUP BY symbol, strategy_id, DATE_TRUNC('day', time)
ORDER BY symbol, strategy_id, day;
```

### 6.5 `v_fill_sample_calibration`

Simulation vs live execution comparison:

```sql
CREATE OR REPLACE VIEW v_fill_sample_calibration AS
SELECT
    f.symbol,
    f.simulation_id,
    AVG(f.slippage_points)  AS sim_slippage,
    AVG(o.slippage_points)  AS live_slippage,
    COUNT(*)                 AS sample_count
FROM fill_samples f
INNER JOIN orders o
    ON f.symbol = o.symbol
    AND DATE_TRUNC('day', f.time) = DATE_TRUNC('day', o.time)
GROUP BY f.symbol, f.simulation_id;
```

## 7. Migration — CSV to Parquet + DuckDB

### 7.1 One-time bulk migration script

```python
# scripts/migrate_to_warehouse.py
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from pathlib import Path

WAREHOUSE = Path("data/warehouse")
CSV_SOURCES = {
    "ticks":   {"path": "artifacts/mega_data/ticks/*.csv",     "frequency": None},
    "ohlcv":   {"path": "data/EURUSD_*.csv",                   "frequency": "infer"},
}

def migrate_csv_to_parquet(csv_glob: str, table_type: str, frequency: str = None):
    for csv_path in sorted(Path().glob(csv_glob)):
        df = pd.read_csv(csv_path)

        if table_type == "ticks":
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df["source"] = "MT5"
            df["symbol"] = csv_path.stem.split("_")[0]  # e.g. EURUSD_bulk -> EURUSD
            df["year"] = df["time"].dt.year.astype(str)
            df["month"] = df["time"].dt.month.astype(str).str.zfill(2)
            partition_cols = ["source", "symbol", "year", "month"]

        elif table_type == "ohlcv":
            df.columns = [c.lower() for c in df.columns]
            df["time"] = pd.to_datetime(df["time"])
            df["frequency"] = frequency or csv_path.stem.split("_")[1]
            df["symbol"] = csv_path.stem.split("_")[0]
            df["source"] = "MT5"
            df["year"] = df["time"].dt.year.astype(str)
            df["month"] = df["time"].dt.month.astype(str).str.zfill(2)
            partition_cols = ["symbol", "frequency", "source", "year", "month"]

        table = pa.Table.from_pandas(df, preserve_index=False)
        table = table.sort_by([("time", "ascending")])

        base = WAREHOUSE / table_type
        pq.write_to_dataset(
            table,
            root_path=str(base),
            partition_cols=partition_cols,
            compression="zstd",
            row_group_size=65536,
        )
```

### 7.2 Step-by-step migration

| Step | Action | Command |
|---|---|---|
| 1 | Convert tick CSVs to Parquet | `python scripts/migrate_to_warehouse.py --type ticks` |
| 2 | Convert OHLCV CSVs to Parquet | `python scripts/migrate_to_warehouse.py --type ohlcv` |
| 3 | Generate manifests | `python scripts/generate_manifests.py` |
| 4 | Register with DuckDB | `python scripts/register_duckdb_catalog.py` |
| 5 | Validate row counts | Run `SELECT source, symbol, count(*) FROM ticks GROUP BY ALL` |
| 6 | Verify SHAs match original CSVs | Compare against `data/manifests/*.json` |

### 7.3 DuckDB catalog registration

```python
import duckdb

conn = duckdb.connect("data/warehouse/catalog.duckdb")

conn.execute("""
    CREATE OR REPLACE VIEW ticks AS
    SELECT * FROM read_parquet(
        'data/warehouse/ticks/**/*.parquet',
        hive_partitioning=true
    )
""")
```

### 7.4 Validation queries

```sql
-- Row count matches original CSV
SELECT source, symbol, count(*) FROM ticks GROUP BY ALL;

-- No null timestamps
SELECT count(*) FROM ticks WHERE time IS NULL;

-- Spread is always non-negative
SELECT count(*) FROM ticks WHERE ask <= bid;

-- OHLCV invariants
SELECT count(*) FROM ohlcv WHERE NOT (open <= high AND low <= close AND low <= open AND high >= close);
```
