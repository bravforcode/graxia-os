# Bridge State: Phase 3.1 Data Wiring Complete

**Date**: 2026-06-27
**Status**: All 4 tasks COMPLETE

## DuckDB Schema (market_data.duckdb)

| Table | Rows | Columns | Notes |
|-------|------|---------|-------|
| ohlcv | 10,000 | time, symbol, timeframe, open, high, low, close, volume, tick_count | XAUUSD 1h only, 2024-10 to 2026-06 |
| ticks | 37,006 | symbol, bid, ask, last, volume, timestamp, time_msc | EURUSD + XAUUSD, June 2026 only |
| shadow_trades | 10,000 | signal_id, symbol, direction, entry_price, exit_price, ... | All OPEN status |

## Data Source Comparison

| Source | XAUUSD H1 Rows | Date Range | Speed |
|--------|---------------|------------|-------|
| DuckDB (market_data) | 10,000 | 2024-10 to 2026-06 | ~5ms |
| Warehouse Parquet | 50,000 (deduped from 300K) | 2017-12 to 2026-06 | ~200ms |
| CSV | 50,000 | 2017-12 to 2026-06 | ~50ms |

## Wiring Results

- load_ohlcv() unified loader: WORKS (DuckDB -> Warehouse -> CSV fallback)
- Triple-Barrier labeling via load_ohlcv: WORKS (49,974 labeled bars)
- Warehouse deduplication: FIXED (6 shards/month had identical data)

## Decision: Primary Data Source

**RECOMMENDATION: Warehouse Parquet as primary**

Rationale:
1. 50K bars vs DuckDB's 10K (5x more data)
2. Hive-partitioned = scalable to any symbol/timeframe
3. Parquet = columnar, fast reads, compresses well
4. DuckDB = too small (10K rows), only XAUUSD 1h, locked by processes
5. CSV = fine but no partitioning, harder to scale

Fallback chain: Warehouse -> CSV -> DuckDB (smallest/last resort)
