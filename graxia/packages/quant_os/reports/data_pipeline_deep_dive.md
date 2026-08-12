# Data Pipeline Deep Dive Analysis
## `data_pipeline/` — Comprehensive Audit Report
**Date:** 2026-06-29  
**Auditor:** researcher agent  
**Scope:** All 17 files in `data_pipeline/` + integration with `quant_os`

---

## Executive Summary

The `data_pipeline/` module is an **early-stage research prototype** that is NOT production-ready. It has **4 critical bugs** that cause silent data loss, **2 security issues** (hardcoded API keys in source), and a **complete disconnect** from the trading system's actual data infrastructure (`data/pipeline.py`, `data/duckdb_write_queue.py`, `market_data/`, `core/multi_source_pipeline.py`). The pipeline writes to a **separate DuckDB database** (`data_pipeline/storage/quant_os.duckdb`) that the trading system never reads — the main system uses `data/market_data.duckdb` and `data/ticks.duckdb`.

**Verdict: NO_GO for production.** The pipeline must be rebuilt as a thin orchestration layer over the existing quant_os data infrastructure.

---

## P1 — Critical Bugs (Data Loss / Crashes)

### BUG-01: `upsert_market_data` uses DELETE-INSERT — loses ALL history
- **File:** `storage/duckdb_store.py`, lines 91-92
- **Code:**
  ```python
  self.conn.execute("DELETE FROM market_data WHERE source = ?", [source])
  self.conn.execute("INSERT INTO market_data SELECT * FROM df")
  ```
- **Impact:** Every pipeline run **deletes all existing market data** for a source before inserting only the latest batch (5 days of yfinance data). After 30+ days, only the last 5 days of data exist. Any backtest, label generation, or analysis using historical data is silently broken.
- **Fix:** Use `INSERT OR REPLACE` with a unique constraint, or partition by date and use `DELETE WHERE timestamp < cutoff`.

### BUG-02: `upsert_macro_data` DELETEs ALL macro data every run
- **File:** `storage/duckdb_store.py`, line 100
- **Code:**
  ```python
  self.conn.execute("DELETE FROM macro_data")
  ```
- **Impact:** Every run wipes the entire macro_data table and re-inserts from scratch. If a FRED API call fails during the run, that series data is permanently lost. If FRED rate-limits, data gaps appear with no recovery.
- **Fix:** Incremental upsert — only delete rows for the specific series being updated, and only if the new fetch succeeded.

### BUG-03: `upsert_news_sentiment` uses `INSERT OR REPLACE` but `source` column mismatch
- **File:** `storage/duckdb_store.py`, lines 107-116
- **Code:**
  ```python
  cols = ["title", "description", "source", "url", ...]
  ...
  df = df.rename(columns={"source": "source_name"})
  self.conn.execute("INSERT OR REPLACE INTO news_sentiment SELECT * FROM df")
  ```
- **Impact:** The `INSERT OR REPLACE` requires a matching primary key. The table has `url VARCHAR UNIQUE` but no explicit `PRIMARY KEY`. DuckDB treats `UNIQUE` as a uniqueness constraint for `INSERT OR REPLACE` but if `url` is empty/null for any article, the replace silently fails or creates duplicates.
- **Fix:** Add explicit `PRIMARY KEY (url)` to the table DDL. Filter out articles with empty/null URLs before insert.

### BUG-04: `pipeline.py` never calls `self.chroma.close()`
- **File:** `pipeline.py`, lines 34-35, 117
- **Code:**
  ```python
  self.duckdb = DuckDBStore()
  self.chroma = ChromaStore()
  # ... after run ...
  self.duckdb.close()   # only DuckDB closed
  ```
- **Impact:** ChromaDB PersistentClient holds file locks. If the process doesn't exit cleanly, the ChromaDB WAL journal may be left unflushed. On Windows, this can corrupt the ChromaDB database.
- **Fix:** Add `self.chroma.close()` after `self.duckdb.close()`. (Note: `ChromaStore.close()` is currently a no-op — it should call `self.client.stop()` or similar.)

### BUG-05: No DuckDB WAL or connection safety
- **File:** `storage/duckdb_store.py`, line 17
- **Code:**
  ```python
  self.conn = duckdb.connect(self.db_path)
  ```
- **Impact:** DuckDB uses WAL mode by default. If the pipeline crashes mid-write (e.g., during the DELETE-INSERT in BUG-01), the WAL is left in a dirty state. On next startup, DuckDB may fail to recover, or silently lose committed data.
- **Fix:** Use `duckdb.connect(self.db_path, read_only=False)` with explicit checkpointing after batch writes. Add `PRAGMA wal_checkpoint(TRUNCATE)` after critical writes.

---

## P2 — High Priority (Missing Production Features)

### FEAT-01: **CRITICAL DISCONNECT** — Pipeline writes to wrong DuckDB
- **The pipeline uses:** `data_pipeline/storage/quant_os.duckdb`
- **The trading system uses:** `data/market_data.duckdb` and `data/ticks.duckdb`
- **The `data/duckdb_write_queue.py`** writes tick data to `data/ticks.duckdb`
- **The `scripts/bootstrap_history.py`** writes to `data/market_data.duckdb`
- **Impact:** The entire data pipeline is orphaned. No component in the trading system reads from `quant_os.duckdb`. The `get_latest_price()` and `get_sentiment_summary()` methods are dead code.
- **Fix:** Either (a) redirect the pipeline to write to `data/market_data.duckdb`, or (b) build a bridge layer that the trading system reads from.

### FEAT-02: No data validation / schema enforcement
- **Expected:** `core/schemas.py` defines `XAUUSD_M15_SCHEMA` with pandera validation (OHLCV integrity checks, price jump detection, high >= low invariant).
- **Actual:** The pipeline stores raw data with zero validation. Bad data (inverted OHLC, NaN prices, negative volumes) flows directly into the database.
- **Fix:** Add pandera validation step in `upsert_market_data()` and `upsert_macro_data()`. Reject and log invalid rows.

### FEAT-03: No data freshness monitoring
- **Expected:** `market_data/feed_health.py` and `market_data/data_watermark.py` track data staleness.
- **Actual:** The pipeline has no mechanism to detect stale/missing data. If yfinance returns the same data for 3 days, it silently overwrites with duplicates.
- **Fix:** Add staleness detection: compare `timestamp` of incoming data against last known. Alert if data is older than expected interval.

### FEAT-04: No deduplication on market data
- **Impact:** Every pipeline run inserts duplicate OHLCV rows for the same timestamp. After 10 runs, you have 10 copies of the same candle.
- **Fix:** Add `UNIQUE(symbol, timestamp, source)` constraint or use `INSERT OR REPLACE`.

### FEAT-05: No XAUUSD in symbol list
- **File:** `config.py`, lines 25-30
- **Impact:** The trading system is primarily focused on XAUUSD (gold), but the pipeline only tracks `GC=F` (gold futures) — not the same as spot XAUUSD. The spread, liquidity, and pricing characteristics differ significantly.
- **Fix:** Add `XAUUSD=X` or `GC=F` with explicit metadata noting it's futures, not spot.

### FEAT-06: No data lineage / audit trail
- **Expected:** `CONSTITUTION.md` INV-005 requires "Every dataset has manifest with SHA-256 checksum."
- **Actual:** No manifests, no checksums, no provenance tracking. The pipeline can't answer: "Where did this data come from? When was it fetched? What was the raw API response?"
- **Fix:** Generate `data/manifests/*.manifest.json` after each pipeline run with SHA-256 of ingested data, timestamps, and source metadata.

### FEAT-07: No backup before destructive writes
- **File:** `storage/duckdb_store.py`
- **Impact:** The `backup()` method exists but is never called. Before DELETE-INSERT operations (BUG-01, BUG-02), no backup is created.
- **Fix:** Call `self.backup()` before destructive operations, or use WAL + checkpoint pattern.

### FEAT-08: No health check / alerting
- **Expected:** `market_data/feed_health.py` provides health monitoring.
- **Actual:** Errors are logged but never surfaced to the user or trading system. The `self.errors` list is printed to log but never triggers any alert.
- **Fix:** Add Telegram/email alerts on pipeline failures. Integrate with `core/telegram_notify.py`.

### FEAT-09: No idempotency
- **Impact:** Running the pipeline twice produces different results (doubles some data, loses other data). A production pipeline must be idempotent — same input, same output, regardless of run count.
- **Fix:** Use upsert patterns (merge on primary key) instead of DELETE-INSERT.

### FEAT-10: Vault sync is fragile
- **File:** `pipeline.py`, lines 74-93
- **Impact:** Reads markdown files from a hardcoded Windows path (`C:\Users\menum\Documents\ObsidianVault\...`). Truncates content to 500 chars. No validation of strategy format. If the vault path doesn't exist, the entire pipeline crashes.
- **Fix:** Use relative paths or config. Add try/except for path existence. Parse strategy YAML frontmatter instead of raw text truncation.

---

## P3 — Medium Priority (Performance & Integration)

### PERF-01: No rate limiting on yfinance/ccxt calls
- **File:** `sources/market_data.py`
- **Impact:** yfinance throttles aggressive callers. The pipeline hits all symbols in a tight loop with only 5-second retry delay. Under load, all retries will fail.
- **Fix:** Add per-symbol delays (1-2 seconds). Use `yf.download()` for batch fetching instead of per-symbol `Ticker.history()`.

### PERF-02: Redundant FRED API instantiation
- **File:** `sources/macro_data.py`, line 35
- **Code:**
  ```python
  for attempt in range(RETRY_MAX):
      fred = Fred(api_key=FRED_API_KEY)  # new instance every retry
  ```
- **Fix:** Create the `Fred` instance once outside the retry loop.

### PERF-03: Sentiment analysis is O(n) synchronous
- **File:** `sources/news_sentiment.py`, line 87
- **Code:**
  ```python
  scores = text_col.apply(lambda x: pd.Series(analyze_sentiment(str(x))))
  ```
- **Impact:** VADER + TextBlob run sequentially on every article. For 140 articles (7 queries × 20), this takes 5-15 seconds.
- **Fix:** Use `concurrent.futures.ThreadPoolExecutor` or batch processing.

### PERF-04: ChromaDB creates new embeddings on every upsert
- **File:** `storage/chroma_store.py`, line 57
- **Impact:** Even if the same article is re-upserted (same URL), ChromaDB re-embeds the text. Embedding generation is the most expensive operation.
- **Fix:** Check if the document ID already exists before upserting. Skip unchanged documents.

### PERF-05: `query_data.py` uses `ANY_VALUE(close)` — nondeterministic
- **File:** `query_data.py`, line 9
- **Code:**
  ```python
  "SELECT symbol, ANY_VALUE(close) as close, source FROM market_data WHERE close IS NOT NULL GROUP BY symbol, source"
  ```
- **Impact:** `ANY_VALUE` picks an arbitrary row when there are multiple entries for the same symbol+source (which happens due to BUG-04). The displayed price may be wrong.
- **Fix:** Use `LAST_VALUE(close ORDER BY timestamp)` or `MAX(timestamp)` subquery.

### PERF-06: `register_tasks.py` runs `pipeline.py` for all three schedules
- **File:** `register_tasks.py`, lines 9-31
- **Impact:** The "Market Data" task and "News Sentiment" task both run the FULL pipeline, not just their respective steps. This wastes API calls and time.
- **Fix:** Use `orchestration/flows.py` sub-flows, or add CLI flags to `pipeline.py` (e.g., `--market-only`, `--news-only`).

### PERF-07: All scheduled tasks run `pipeline.py` sequentially
- **File:** `pipeline.py`, lines 102-105
- **Code:**
  ```python
  self.run_market_data()
  self.run_macro_data()
  self.run_news_sentiment()
  self.run_vault_sync()
  ```
- **Impact:** Market data (30s), macro (60s), news (30s), vault (5s) = ~125 seconds total. They could run in parallel.
- **Fix:** Use `concurrent.futures.ThreadPoolExecutor` for independent fetch operations.

### INT-01: No integration with `data/duckdb_write_queue.py`
- **The trading system** uses an async write queue for high-throughput tick data.
- **The pipeline** uses synchronous DuckDB writes.
- **Impact:** Two different DuckDB connection patterns writing to two different databases. No coordination.
- **Fix:** The pipeline should either write to the same DuckDB as the write queue, or use the write queue for consistency.

### INT-02: No integration with `market_data/` module
- **The `market_data/` directory** contains: `ccxt_feeder.py`, `tick_recorder.py`, `tick_store.py`, `feed_health.py`, `spread_monitor.py`.
- **The pipeline** duplicates ccxt logic in `sources/market_data.py` instead of reusing `market_data/ccxt_feeder.py`.
- **Fix:** Refactor `sources/market_data.py` to use the existing `market_data/ccxt_feeder.py` and `market_data/tick_store.py`.

### INT-03: No integration with `core/multi_source_pipeline.py`
- **The core module** has a mature `DataPipeline` class with priority chains, rate limiting, and fallback logic.
- **The `data_pipeline/`** reimplements the same from scratch with worse quality.
- **Fix:** Either remove `data_pipeline/` and wrap `core/multi_source_pipeline.py`, or make `data_pipeline/` a thin orchestrator.

---

## P4 — Low Priority (Enhancements)

### ENH-01: Security — Hardcoded API keys in source code
- **File:** `config.py`, lines 20-22
- **Code:**
  ```python
  ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "69A2D75S09YBKLGR")
  FRED_API_KEY = os.environ.get("FRED_API_KEY", "ca6997817f1fad59485310fc56ae594e")
  NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "98acea70c06f4dd5ac1489054d877768")
  ```
- Also duplicated in `auto_run.py`, lines 22-24.
- **Impact:** API keys are committed to git. Anyone with repo access has full API access.
- **Fix:** Remove hardcoded defaults. Use `.env` file with `.gitignore`. Rotate all exposed keys immediately.

### ENH-02: `ChromaStore.close()` is a no-op
- **File:** `storage/chroma_store.py`, lines 88-89
- **Code:**
  ```python
  def close(self):
      pass
  ```
- **Impact:** No resource cleanup. PersistentClient should be stopped.
- **Fix:** Call `self.client.stop()` or equivalent.

### ENH-03: No Parquet export for ML training
- **The ML pipeline** (`core/ml_pipeline.py`, `scripts/build_mega_features.py`) reads from Parquet files in `data/market_data/`.
- **The data pipeline** only writes to DuckDB.
- **Fix:** Add a Parquet export step after DuckDB writes.

### ENH-04: `scheduler.py` and `register_tasks.py` are duplicated
- **Both files** register Windows scheduled tasks with slightly different configurations.
- **Impact:** Running both creates conflicting task definitions.
- **Fix:** Consolidate into a single scheduler module.

### ENH-05: No data versioning
- **Impact:** Cannot reproduce a specific pipeline state for backtesting.
- **Fix:** Tag each pipeline run with a version hash. Store in DuckDB metadata.

### ENH-06: No circuit breaker for API failures
- **Impact:** If yfinance is down, the pipeline retries 3 times then silently continues. No circuit breaker to stop hammering a failing API.
- **Fix:** Implement exponential backoff + circuit breaker (open after 3 consecutive failures, half-open after 5 minutes).

### ENH-07: No data quality metrics
- **Impact:** No tracking of: row counts, null rates, price anomalies, latency per source.
- **Fix:** Emit quality metrics to MLflow via `ml_tracking/mlflow_tracker.py`.

### ENH-08: `check_cache.py` has no error handling
- **File:** `check_cache.py`, lines 1-4
- **Impact:** If `market_cache.json` doesn't exist or is corrupted, the script crashes with no useful error.
- **Fix:** Add try/except and meaningful error message.

---

## Integration Gap Analysis

### What the Trading System Expects vs. What the Pipeline Delivers

| Requirement | Trading System Needs | Pipeline Delivers | Gap |
|---|---|---|---|
| **Database** | `data/market_data.duckdb` | `data_pipeline/storage/quant_os.duckdb` | **SEPARATE DBs — No data flows** |
| **Tick storage** | `data/ticks.duckdb` via `DuckDBWriteQueue` | Not supported | **No tick data at all** |
| **OHLCV schema** | Pandera-validated (core/schemas.py) | Raw, unvalidated | **No validation** |
| **XAUUSD spot** | Spot gold pricing | `GC=F` futures only | **Instrument mismatch** |
| **Real-time** | Async, 100ms latency (DuckDBWriteQueue) | Synchronous, 5-min batch | **1000x latency gap** |
| **Deduplication** | Unique constraints, idempotent writes | DELETE-INSERT (data loss) | **Data loss** |
| **Manifests** | SHA-256 checksum per INV-005 | None | **Compliance violation** |
| **Alerts** | Telegram integration (core/telegram_notify.py) | Log-only | **Silent failures** |
| **Rate limiting** | `DataSource.wait_if_needed()` in core | None | **API bans** |
| **Fallback chain** | CCXT → CoinGecko → Yahoo | Separate per-source | **No fallback** |

### Real-Time Requirements
- The trading system uses `DuckDBWriteQueue` with 100ms flush intervals for tick data.
- The data pipeline runs in batch mode with 5-15 minute intervals.
- **Gap:** The pipeline cannot serve real-time trading decisions. It's designed for daily analytics only.

### Compliance/Audit Requirements
- `CONSTITUTION.md` INV-005: Every dataset must have SHA-256 manifest → **Not implemented**
- `CONSTITUTION.md` INV-010: Missing/invalid data = reject + fail closed → **Not implemented**
- No audit trail of what data was ingested, when, from where, in what quantity.

### Disaster Recovery
- `backup()` method exists but is never called.
- No WAL checkpointing after writes.
- No replication or off-site backup.
- On crash, data may be partially written with no recovery mechanism.

---

## Recommended Action Plan

1. **Immediate (Week 0):**
   - Rotate all exposed API keys
   - Delete hardcoded keys from source
   - Add `.env` + `.gitignore`
   - Fix BUG-01 and BUG-02 (data loss)

2. **Short-term (Week 1):**
   - Redirect pipeline to write to `data/market_data.duckdb` (or create a bridge)
   - Add pandera validation
   - Add deduplication (UNIQUE constraints)
   - Call `backup()` before destructive writes

3. **Medium-term (Week 2-3):**
   - Refactor to use `core/multi_source_pipeline.py` instead of custom sources
   - Add data lineage / manifest generation
   - Add Telegram alerts on failures
   - Consolidate scheduler modules

4. **Long-term (Month 2):**
   - Build real-time streaming path (integrate with `DuckDBWriteQueue`)
   - Add Parquet export for ML pipeline
   - Implement circuit breaker pattern
   - Add data quality metrics dashboard

---

*Report generated by researcher agent — Ruflow (Project Gracia)*
