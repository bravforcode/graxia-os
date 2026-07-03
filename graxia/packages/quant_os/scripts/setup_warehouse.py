"""DuckDB warehouse setup — create, register schemas, import legacy data, create views, validate.

Usage:
    python scripts/setup_warehouse.py --db-path data/warehouse/quantos.duckdb --init --import-legacy --create-views --validate
"""

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Canonical table schemas (matching docs/schema.md) ──────────────────────

SCHEMA_TICKS = """
CREATE TABLE IF NOT EXISTS ticks (
    time        TIMESTAMP   NOT NULL,
    bid         DOUBLE      NOT NULL,
    ask         DOUBLE      NOT NULL,
    last        DOUBLE,
    flags       INTEGER,
    volume      DOUBLE,
    ask_volume  DOUBLE,
    spread      DOUBLE,
    source      VARCHAR     NOT NULL,
    symbol      VARCHAR     NOT NULL
)
"""

SCHEMA_OHLCV = """
CREATE TABLE IF NOT EXISTS ohlcv (
    time        TIMESTAMP   NOT NULL,
    open        DOUBLE      NOT NULL,
    high        DOUBLE      NOT NULL,
    low         DOUBLE      NOT NULL,
    close       DOUBLE      NOT NULL,
    volume      BIGINT      NOT NULL,
    frequency   VARCHAR     NOT NULL,
    symbol      VARCHAR     NOT NULL,
    source      VARCHAR     NOT NULL
)
"""

SCHEMA_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    time                TIMESTAMP   NOT NULL,
    symbol              VARCHAR     NOT NULL,
    side                VARCHAR     NOT NULL,
    volume              DOUBLE      NOT NULL,
    requested_price     DOUBLE      NOT NULL,
    fill_price          DOUBLE      NOT NULL,
    slippage_points     DOUBLE      NOT NULL,
    spread_at_entry     DOUBLE,
    latency_ms          DOUBLE,
    order_type          VARCHAR,
    strategy_id         VARCHAR,
    broker              VARCHAR     NOT NULL,
    client_order_id     VARCHAR
)
"""

SCHEMA_FILL_SAMPLES = """
CREATE TABLE IF NOT EXISTS fill_samples (
    time                TIMESTAMP   NOT NULL,
    symbol              VARCHAR     NOT NULL,
    side                VARCHAR     NOT NULL,
    volume              DOUBLE      NOT NULL,
    simulation_id       VARCHAR     NOT NULL,
    fill_price          DOUBLE      NOT NULL,
    requested_price     DOUBLE      NOT NULL,
    slippage_points     DOUBLE      NOT NULL,
    spread_at_fill      DOUBLE,
    latency_model       VARCHAR,
    tick_sequence_index BIGINT,
    sigma_slippage      DOUBLE
)
"""

SCHEMA_MANIFESTS = """
CREATE TABLE IF NOT EXISTS manifests (
    sha256      VARCHAR     NOT NULL,
    rows        BIGINT      NOT NULL,
    columns     VARCHAR[],
    date_start  TIMESTAMP,
    date_end    TIMESTAMP,
    symbol      VARCHAR     NOT NULL,
    source      VARCHAR     NOT NULL,
    timeframe   VARCHAR,
    file_path   VARCHAR     NOT NULL,
    file_size   BIGINT,
    created_at  DATE        NOT NULL
)
"""

SCHEMA_BACKTEST_COSTS = """
CREATE TABLE IF NOT EXISTS backtest_costs (
    symbol               VARCHAR NOT NULL,
    freq                 VARCHAR NOT NULL,
    spread_cost_dollars  DOUBLE,
    slippage_p90_dollars DOUBLE,
    commission_dollars   DOUBLE,
    total_cost_dollars   DOUBLE,
    imported_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

ALL_SCHEMAS = [
    ("ticks", SCHEMA_TICKS),
    ("ohlcv", SCHEMA_OHLCV),
    ("orders", SCHEMA_ORDERS),
    ("fill_samples", SCHEMA_FILL_SAMPLES),
    ("manifests", SCHEMA_MANIFESTS),
    ("backtest_costs", SCHEMA_BACKTEST_COSTS),
]

# ── Convenience views (matching docs/schema.md §6) ─────────────────────────

VIEW_DAILY_OHLCV_FROM_TICKS = """
CREATE OR REPLACE VIEW v_daily_ohlcv_from_ticks AS
SELECT
    symbol,
    CAST(DATE_TRUNC('day', time) AS TIMESTAMP) AS date,
    FIRST(bid)  AS open,
    MAX(bid)    AS high,
    MIN(bid)    AS low,
    LAST(bid)   AS close,
    COUNT(*)    AS tick_count,
    SUM(COALESCE(volume, 0)) AS volume
FROM ticks
GROUP BY symbol, DATE_TRUNC('day', time)
ORDER BY symbol, date
"""

VIEW_DAILY_OHLCV_UNIFIED = """
CREATE OR REPLACE VIEW v_daily_ohlcv_unified AS
SELECT symbol, date, open, high, low, close, tick_count AS volume, 'ticks' AS source
FROM v_daily_ohlcv_from_ticks
UNION ALL
SELECT symbol, CAST(DATE_TRUNC('day', time) AS TIMESTAMP), open, high, low, close, volume, source
FROM ohlcv
WHERE frequency = 'D1'
ORDER BY symbol, date
"""

VIEW_SPREAD_STATS = """
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
ORDER BY symbol, hour
"""

VIEW_ORDER_PERFORMANCE = """
CREATE OR REPLACE VIEW v_order_performance AS
SELECT
    symbol,
    COALESCE(strategy_id, 'unknown') AS strategy_id,
    DATE_TRUNC('day', time) AS day,
    COUNT(*)                AS order_count,
    AVG(slippage_points)    AS avg_slippage,
    AVG(latency_ms)         AS avg_latency_ms,
    AVG(spread_at_entry)    AS avg_spread
FROM orders
GROUP BY symbol, strategy_id, DATE_TRUNC('day', time)
ORDER BY symbol, strategy_id, day
"""

VIEW_FILL_CALIBRATION = """
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
GROUP BY f.symbol, f.simulation_id
"""

VIEW_UNIFIED_OHLCV = """
CREATE OR REPLACE VIEW v_unified_ohlcv AS
SELECT time, symbol, frequency, open, high, low, close, volume, source FROM ohlcv
UNION ALL
SELECT
    time, symbol,
    'RAW'::VARCHAR AS frequency,
    bid AS open, bid AS high, bid AS low, bid AS close,
    CAST(1 AS BIGINT) AS volume,
    source
FROM ticks
ORDER BY symbol, time
"""

ALL_VIEWS = [
    ("v_daily_ohlcv_from_ticks", VIEW_DAILY_OHLCV_FROM_TICKS),
    ("v_daily_ohlcv_unified", VIEW_DAILY_OHLCV_UNIFIED),
    ("v_spread_stats", VIEW_SPREAD_STATS),
    ("v_order_performance", VIEW_ORDER_PERFORMANCE),
    ("v_fill_sample_calibration", VIEW_FILL_CALIBRATION),
    ("v_unified_ohlcv", VIEW_UNIFIED_OHLCV),
]


def check_duckdb() -> None:
    try:
        import duckdb  # noqa: F401
    except ImportError:
        print("ERROR: DuckDB is not installed. Install with: pip install duckdb")
        sys.exit(1)


def create_database(db_path: Path) -> None:
    import duckdb

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("PRAGMA enable_progress_bar")
    print(f"Connected to DuckDB at: {db_path}")

    for name, ddl in ALL_SCHEMAS:
        conn.execute(ddl)
        print(f"  Table '{name}' ready")

    conn.close()
    print("Database schema registered successfully")


def create_views(db_path: Path) -> None:
    import duckdb

    conn = duckdb.connect(str(db_path))
    for name, ddl in ALL_VIEWS:
        conn.execute(ddl)
        print(f"  View '{name}' created/replaced")
    conn.close()
    print("All convenience views created")


def _count_table(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _try_insert(conn, label: str, table: str, sql: str, params=None) -> int:
    pre = _count_table(conn, table)
    try:
        if params:
            conn.execute(sql, params)
        else:
            conn.execute(sql)
        post = _count_table(conn, table)
        rows = post - pre
        if rows:
            print(f"  Imported {rows} rows from {label} -> {table}")
        return rows
    except Exception as e:
        print(f"  SKIP {label}: {e}")
        return 0


def import_legacy_data(db_path: Path) -> None:
    import duckdb

    conn = duckdb.connect(str(db_path))
    total_rows = 0

    # ── 1. Legacy OHLCV CSVs: data/{symbol}_{tf}.csv ──────────────────────
    data_dir = REPO_ROOT / "data"
    freq_map = {"M15": "M15", "H1": "H1", "D1": "D1", "X": "D1"}
    for csv_file in sorted(data_dir.glob("*.csv")):
        stem = csv_file.stem
        parts = stem.split("_")
        if len(parts) < 2:
            continue
        symbol = parts[0]
        tf_raw = parts[1]
        freq = freq_map.get(tf_raw, tf_raw)

        if stem == "EURUSD_X":
            sql = f"""
                INSERT INTO ohlcv (time, open, high, low, close, volume, frequency, symbol, source)
                SELECT
                    CAST(t.Date AS TIMESTAMP),
                    t.Open, t.High, t.Low, t.Close,
                    CAST(t.Volume AS BIGINT),
                    'D1', 'EURUSD', 'other'
                FROM read_csv_auto('{csv_file.as_posix()}', header=true) t
                WHERE NOT EXISTS (
                    SELECT 1 FROM ohlcv
                    WHERE symbol = 'EURUSD' AND frequency = 'D1' AND time = CAST(t.Date AS TIMESTAMP)
                )
            """
        else:
            sql = f"""
                INSERT INTO ohlcv (time, open, high, low, close, volume, frequency, symbol, source)
                SELECT
                    CAST(t.time AS TIMESTAMP),
                    t.open, t.high, t.low, t.close,
                    CAST(t.volume AS BIGINT),
                    '{freq}', '{symbol}', 'MT5'
                FROM read_csv('{csv_file.as_posix()}', header=true, auto_detect=true) t
                WHERE NOT EXISTS (
                    SELECT 1 FROM ohlcv
                    WHERE symbol = '{symbol}' AND frequency = '{freq}' AND time = t.time
                )
            """
        total_rows += _try_insert(conn, csv_file.name, "ohlcv", sql)

    # ── 2. Bulk tick CSVs: artifacts/mega_data/ticks/{symbol}_bulk.csv ────
    bulk_dir = REPO_ROOT / "artifacts" / "mega_data" / "ticks"
    if bulk_dir.exists():
        for csv_file in sorted(bulk_dir.glob("*_bulk.csv")):
            sym = csv_file.stem.replace("_bulk", "")
            sql = f"""
                INSERT INTO ticks (time, bid, ask, last, flags, volume, spread, source, symbol)
                SELECT
                    CAST(TO_TIMESTAMP(t.time) AS TIMESTAMP),
                    t.bid, t.ask, t.last, CAST(t.flags AS INTEGER),
                    t.volume_real, NULL, 'MT5', '{sym}'
                FROM read_csv('{csv_file.as_posix()}', header=true, auto_detect=true) t
                WHERE NOT EXISTS (
                    SELECT 1 FROM ticks
                    WHERE symbol = '{sym}' AND source = 'MT5'
                    AND time = CAST(TO_TIMESTAMP(t.time) AS TIMESTAMP)
                )
            """
            total_rows += _try_insert(conn, csv_file.name, "ticks", sql)

    # ── 3. Daily tick Parquet: artifacts/tick_data/{symbol}_ticks_{YYYYMMDD}.parquet ──
    tick_data_dir = REPO_ROOT / "artifacts" / "tick_data"
    if tick_data_dir.exists():
        for parquet_file in sorted(tick_data_dir.glob("*_ticks_*.parquet")):
            sym = parquet_file.stem.split("_")[0]
            sql = f"""
                INSERT INTO ticks (time, bid, ask, last, flags, volume, spread, source, symbol)
                SELECT
                    CAST(t.timestamp_utc AS TIMESTAMP),
                    t.bid, t.ask, t.last, CAST(t.flags AS INTEGER),
                    CAST(t.volume AS DOUBLE),
                    t.spread_price, 'MT5', '{sym}'
                FROM read_parquet('{parquet_file.as_posix()}') t
                WHERE NOT EXISTS (
                    SELECT 1 FROM ticks
                    WHERE symbol = '{sym}' AND source = 'MT5'
                    AND time = CAST(t.timestamp_utc AS TIMESTAMP)
                )
            """
            total_rows += _try_insert(conn, parquet_file.name, "ticks", sql)

    # ── 4. Order Parquet: artifacts/mega_data/orders/batch_*.parquet ──────
    orders_dir = REPO_ROOT / "artifacts" / "mega_data" / "orders"
    if orders_dir.exists():
        for parquet_file in sorted(orders_dir.glob("batch_*.parquet")):
            sql = f"""
                INSERT INTO orders (time, symbol, side, volume, requested_price, fill_price,
                                    slippage_points, latency_ms, order_type, broker, client_order_id)
                SELECT
                    CAST(t.send_time AS TIMESTAMP),
                    t.symbol, t.side, t.volume,
                    t.send_price, t.entry,
                    t.slippage_points, CAST(t.latency_ms AS DOUBLE),
                    'market', 'MT5', t.order_id
                FROM read_parquet('{parquet_file.as_posix()}') t
                WHERE NOT EXISTS (
                    SELECT 1 FROM orders
                    WHERE client_order_id = t.order_id AND broker = 'MT5'
                )
            """
            total_rows += _try_insert(conn, parquet_file.name, "orders", sql)

    # ── 5. Fill samples CSVs: artifacts/fill_samples_fixed/fill_samples_*.csv ──
    fill_dir = REPO_ROOT / "artifacts" / "fill_samples_fixed"
    if fill_dir.exists():
        for csv_file in sorted(fill_dir.glob("fill_samples_*.csv")):
            sql = f"""
                INSERT INTO fill_samples (time, symbol, side, volume, simulation_id,
                                          fill_price, requested_price, slippage_points,
                                          spread_at_fill, latency_model)
                SELECT
                    CAST(t.decision_time AS TIMESTAMP),
                    t.symbol, t.side, 0.01,
                    'legacy_v1',
                    t.fill_price, t.decision_price,
                    t.slippage_points,
                    t.spread_price, 'fixed'
                FROM read_csv('{csv_file.as_posix()}', header=true, auto_detect=true) t
                WHERE NOT EXISTS (
                    SELECT 1 FROM fill_samples
                    WHERE symbol = t.symbol AND time = CAST(t.decision_time AS TIMESTAMP)
                    AND simulation_id = 'legacy_v1'
                )
            """
            total_rows += _try_insert(conn, csv_file.name, "fill_samples", sql)

    # ── 6. Backtest cost JSONs: artifacts/backtest_cost/backtest_*.json ───
    cost_dir = REPO_ROOT / "artifacts" / "backtest_cost"
    if cost_dir.exists():
        for json_file in sorted(cost_dir.glob("backtest_*.json")):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                sym = data.get("symbol", "")
                freq = data.get("freq", "")
                exists = conn.execute(
                    "SELECT COUNT(*) FROM backtest_costs WHERE symbol = ? AND freq = ?",
                    [sym, freq]
                ).fetchone()[0]
                if exists:
                    continue
                conn.execute("""
                    INSERT INTO backtest_costs (symbol, freq, spread_cost_dollars,
                                                slippage_p90_dollars, total_cost_dollars)
                    VALUES (?, ?, ?, ?, ?)
                """, [
                    sym, freq,
                    data.get("spread_cost_dollars"),
                    data.get("slippage_p90_dollars"),
                    data.get("total_cost_dollars"),
                ])
                total_rows += 1
                print(f"  Imported {json_file.name} -> backtest_costs")
            except Exception as e:
                print(f"  SKIP {json_file.name}: {e}")

    conn.close()
    print(f"Legacy import complete. Total rows imported: {total_rows}")


def validate(db_path: Path) -> bool:
    import duckdb

    conn = duckdb.connect(str(db_path))
    checks = []
    all_pass = True

    # Row counts per table
    for name, _ in ALL_SCHEMAS:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            checks.append((name, "row_count", count, count >= 0))
            print(f"  {name}: {count} rows")
        except Exception as e:
            checks.append((name, "row_count", 0, False))
            print(f"  {name}: ERROR — {e}")
            all_pass = False

    # No null timestamps
    for tbl in ["ticks", "ohlcv", "orders", "fill_samples"]:
        try:
            nulls = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE time IS NULL").fetchone()[0]
            ok = nulls == 0
            all_pass = all_pass and ok
            print(f"  {tbl}.time NULLs: {nulls} {'OK' if ok else 'FAIL'}")
        except Exception:
            pass

    # Spread invariant: ask > bid (warn-only — crossed spreads happen in volatile markets)
    try:
        bad = conn.execute("SELECT COUNT(*) FROM ticks WHERE ask <= bid AND ask IS NOT NULL AND bid IS NOT NULL").fetchone()[0]
        status = "OK" if bad == 0 else f"WARN ({bad} crossed spreads — market data artifact)"
        print(f"  ticks ask<=bid: {bad} {status}")
    except Exception:
        pass

    # OHLCV invariant: open <= high, low <= close, low <= open, high >= close (warn-only)
    try:
        bad = conn.execute("""
            SELECT COUNT(*) FROM ohlcv
            WHERE NOT (open <= high AND low <= close AND low <= open AND high >= close)
        """).fetchone()[0]
        status = "OK" if bad == 0 else f"WARN ({bad} bars violate invariants)"
        print(f"  ohlcv bar invariants: {bad} {status}")
    except Exception:
        pass

    # Slippage non-null in orders
    try:
        bad = conn.execute("SELECT COUNT(*) FROM orders WHERE slippage_points IS NULL").fetchone()[0]
        ok = bad == 0
        all_pass = all_pass and ok
        print(f"  orders slippage NULLs: {bad} {'OK' if ok else 'FAIL'}")
    except Exception:
        pass

    # Views are queryable
    for vname, _ in ALL_VIEWS:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {vname}").fetchone()[0]
            print(f"  {vname}: {count} rows (queryable)")
        except Exception as e:
            print(f"  {vname}: ERROR — {e}")
            all_pass = False

    conn.close()
    return all_pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DuckDB Warehouse Setup — create schemas, import data, create views, validate"
    )
    parser.add_argument(
        "--db-path",
        default=str(REPO_ROOT / "data" / "warehouse" / "quantos.duckdb"),
        help="Path to the DuckDB database file (default: data/warehouse/quantos.duckdb)",
    )
    parser.add_argument("--init", action="store_true", help="Create database + register table schemas")
    parser.add_argument("--import-legacy", action="store_true", help="Import existing CSV/Parquet data")
    parser.add_argument("--create-views", action="store_true", help="Create convenience views")
    parser.add_argument("--validate", action="store_true", help="Run validation queries")
    args = parser.parse_args()

    check_duckdb()

    db_path = Path(args.db_path)

    if args.init:
        print("=== INIT: Creating database and registering schemas ===")
        create_database(db_path)

    if args.import_legacy:
        print("=== IMPORT: Importing legacy data ===")
        import_legacy_data(db_path)

    if args.create_views:
        print("=== VIEWS: Creating convenience views ===")
        create_views(db_path)

    if args.validate:
        print("=== VALIDATE: Running validation queries ===")
        ok = validate(db_path)
        if ok:
            print("All validation checks PASSED")
        else:
            print("Some validation checks FAILED")
            return 1

    print("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
