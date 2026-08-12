# Parquet / ClickHouse Migration Plan

## 1. Current Data Volume Audit

| Metric | Value |
|---|---|
| Total CSV files | 36 |
| Total size | 37.27 MB |
| Total data rows | ~788,000 |
| Largest directory | `mega_data/ticks/` (18.1 MB, 3 bulk files) |
| Second largest | `data/` (18.07 MB, 10 OHLC files) |
| Training output | `mega_data/dataset/` + `mega_data/orders/` (small, <100 KB) |

**Breakdown by directory:**

| Directory | Files | Size | Rows |
|---|---|---|---|
| `artifacts/mega_data/ticks/` | 3 | 18.10 MB | ~459K (EURUSD, GBPUSD, XAUUSD bulk) |
| `data/` (OHLC D1/H1/M15) | 10 | 18.07 MB | ~328K |
| `artifacts/tick_data/` | 3 | 1.01 MB | tick snapshots |
| `artifacts/mega_data/dataset/` | 9 | 0.04 MB | training features |
| `artifacts/mega_data/orders/` | 11 | 0.04 MB | batch orders |
| **Total** | **36** | **37.27 MB** | **~788K rows** |

## 2. CSV vs Parquet

### Why Parquet is better

| Property | CSV | Parquet |
|---|---|---|
| Storage format | Row-based text | Columnar binary |
| Compression | None (plain text) | Snappy/Zstd, often ~95% smaller |
| Schema | Implicit (header row) | Explicit (embedded schema) |
| Read speed | Reads entire file | Reads only needed columns |
| Type safety | All strings | Native int/float/datetime |
| Splittable | No (full scan) | Yes (row group boundaries) |

Parquet stores data column-by-column instead of row-by-row. This means:
- Analytical queries read 1/10th the data (only the columns you need).
- Compression ratios of 10:1 to 20:1 vs CSV (Snappy is fast, Zstd is smaller).
- Schema is part of the file — no guessing types on load.

### Libraries

| Library | Status |
|---|---|
| **pyarrow** | ✅ **Installed** (v23.0.1) — production-ready, recommended |
| fastparquet | ❌ Not installed — lightweight alternative, no action needed |

pyarrow is already available. No new dependencies required for Step 1–3.

### Conversion pattern

```python
import pandas as pd

# CSV → Parquet (one-liner)
df = pd.read_csv("input.csv")
df.to_parquet("output.parquet", compression="snappy")

# Read back
df = pd.read_parquet("output.parquet")

# Memory-mapped read of single column (no full load)
import pyarrow.parquet as pq
table = pq.read_table("output.parquet", columns=["bid", "ask"])
```

## 3. ClickHouse Option

### What is ClickHouse

ClickHouse is an open-source **columnar DBMS** built for real-time analytics on large datasets. It is 100–1000× faster than querying CSVs for aggregations (GROUP BY, WHERE on time ranges).

### Installation

| Method | Viable? |
|---|---|
| **Docker** (recommended) | ✅ `docker run -d --name clickhouse-server -p 8123:8123 clickhouse/clickhouse-server` |
| Windows native | ⚠️ Limited — no official Windows build. Use WSL2 or Docker. |
| ClickHouse Cloud | ✅ Free tier available |

Python client: `pip install clickhouse-connect` (not currently installed).

### Is it worth it at current volume?

**Rule of thumb:** ClickHouse pays off at **10M+ rows** or **100+ GB**.

Current volume: **~788K rows, 37 MB** — well below the threshold.

| Factor | Verdict |
|---|---|
| Data volume | ❌ 37 MB — fits in memory, Pandas is faster for interactive work |
| Query complexity | ❌ Current usage is load-all + feature-engineering, not OLAP |
| Infrastructure cost | ❌ Adds Docker + maintenance overhead |
| Growth trajectory | ⏳ If data grows 10× in the next quarter, revisit |

**Conclusion:** Not worth it now. Revisit when data exceeds 10M rows or 100 GB.

## 4. Migration Path

### Step 1: Add Parquet output to `build_dataset.py` (NOW, low risk)

Current `build_dataset.py` writes only CSV. Adding a `--format parquet` flag:
- Requires only pyarrow (already installed).
- No breaking change — CSV output remains the default.
- Estimated effort: 30 minutes.

```python
# Add to scripts/build_dataset.py
import pyarrow as pa
import pyarrow.parquet as pq

if args.format == "parquet":
    table = pa.Table.from_pylist(features)
    parquet_path = csv_path.replace(".csv", ".parquet")
    pq.write_table(table, parquet_path, compression="snappy")
```

### Step 2: Batch convert existing CSV → Parquet (NOW, one-time)

All 36 CSVs in `artifacts/` and `data/` can be converted with a single script:

```bash
python scripts/convert_to_parquet.py --source artifacts/mega_data --recursive
```

Expected savings:
- 37 MB → ~2–4 MB on disk (Snappy compression)
- Feature reads become column-selective instead of full-scan

### Step 3: Add incremental append support (LATER, when streaming)

If data arrives continuously:
- Parquet is **not** append-friendly (files are immutable).
- Strategy: partition by date (`data/YYYY/MM/DD/ticks.parquet`) and write daily files.
- Use `pyarrow.parquet.write_to_dataset()` for partitioned writes.

### Step 4: ClickHouse (LATER, if >10M rows)

Trigger conditions:
- Dataset exceeds 10M rows OR 100 GB
- Query latency becomes a bottleneck (>30s for simple aggregations)
- Multiple consumers need concurrent access

Migration script would:
1. Convert all Parquet files to ClickHouse native format.
2. Set up Docker Compose with persistent volume.
3. Point `build_dataset.py` at ClickHouse via `clickhouse-connect`.

## 5. Recommendation

### Do NOW (this sprint)

| Action | Effort | Impact |
|---|---|---|
| Add `--format parquet` to `build_dataset.py` | 30 min | Future-proofs training output |
| One-time batch convert `data/` CSVs to Parquet | 15 min | Adds only 2 MB to disk, makes feature reads column-selective |

### Do LATER

| Action | Trigger | Notes |
|---|---|---|
| Incremental partitioned writes | Streaming data arrives | Use `write_to_dataset()` |
| ClickHouse | Data >10M rows or >100 GB | Add Docker Compose, revisit |
| Remove CSV fallback | No downstream depends on CSV | Keep for now — zero-risk default |

### Summary

**Today's data volume (37 MB, 788K rows) does not need ClickHouse. The highest-ROI move is adding Parquet output to `build_dataset.py` — pyarrow is already installed, the change is <50 lines, and it makes every future read faster without breaking anything.** Batch-convert the existing CSVs in `data/` and `artifacts/` as a one-off so all downstream scripts can opt into Parquet reads immediately.
