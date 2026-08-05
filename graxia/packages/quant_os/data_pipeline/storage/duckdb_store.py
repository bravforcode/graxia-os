"""
storage/duckdb_store.py — DuckDB Storage Layer for Analytics
"""

import contextlib
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

try:
    from data_pipeline.config import BACKUP_DIR, DUCKDB_PATH
except ImportError:  # standalone tools: data_pipeline dir is on sys.path, so `config` = data_pipeline/config.py
    from config import (  # type: ignore[attr-defined]  # resolves to data_pipeline/config.py in standalone tool context; mypy can't follow that
        BACKUP_DIR,
        DUCKDB_PATH,
    )

# ── Task 6: tick query layer — whitelisted views + parameterized access ──
TICK_VIEW_WHITELIST = {
    "v_ticks",
    "v_backfill_binance_trade",
    "v_backfill_dukascopy",
    "v_backfill_mt5_history",
    "v_ticks_combined",
}
FUNDING_VIEW_WHITELIST = {"v_backfill_binance_funding"}

# Canonical tick projection — every tick view emits EXACTLY these columns so
# UNION ALL stays type-consistent (v_ticks.flags is VARCHAR, backfill flags
# are BIGINT — the projection excludes flags deliberately).
_TICK_PROJECTION = "time_msc, symbol, bid, ask, last, volume, source, data_quality"


def _tick_view_sql(glob: str) -> str:
    """SELECT projection over a parquet glob. union_by_name=true absorbs
    mixed-schema files (legacy daemon parquet without the delta fields vs
    canonical tick_store files) so view registration survives both.

    NOTE: never called with a zero-match glob — register_tick_views defers
    view creation until a glob actually matches (DuckDB read_parquet raises
    "No files found" on zero-match globs).
    """
    return f"SELECT {_TICK_PROJECTION} FROM read_parquet('{glob}', union_by_name=true)"


class DuckDBStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DUCKDB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._tick_views_created = False
        self._ticks_glob: str | None = None
        self._backfill_globs: dict[str, str] | None = None
        self._init_tables()
        self._init_llm_tables()

    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                symbol VARCHAR,
                timestamp TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                source VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_data (
                series_id VARCHAR,
                timestamp TIMESTAMP,
                value DOUBLE,
                fetched_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS news_sentiment (
                title VARCHAR,
                description VARCHAR,
                source_name VARCHAR,
                url VARCHAR UNIQUE,
                published_at TIMESTAMP,
                query VARCHAR,
                vader_compound DOUBLE,
                vader_pos DOUBLE,
                vader_neg DOUBLE,
                textblob_polarity DOUBLE,
                textblob_subjectivity DOUBLE,
                fetched_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR,
                side VARCHAR,
                entry_price DOUBLE,
                exit_price DOUBLE,
                pnl DOUBLE,
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                strategy VARCHAR
            )
        """)

    def upsert_market_data(self, df: pd.DataFrame):
        if len(df) == 0:
            return
        df = df.reset_index()
        rename_map = {}
        for col in df.columns:
            if col.lower() in ["open", "high", "low", "close", "volume", "symbol", "source", "timestamp"]:
                rename_map[col] = col.lower()
        df = df.rename(columns=rename_map)
        cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "source"]
        for col in cols:
            if col not in df.columns:
                df[col] = None
        df = df[cols]
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
        source = df["source"].iloc[0]
        self.conn.execute("DELETE FROM market_data WHERE source = ?", [source])
        self.conn.execute("INSERT INTO market_data SELECT * FROM df")
        print(f"  DuckDB: {len(df)} market rows inserted ({source})")

    def upsert_macro_data(self, df: pd.DataFrame):
        if len(df) == 0:
            return
        df = df[["series_id", "timestamp", "value", "fetched_at"]].copy()
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        self.conn.execute("DELETE FROM macro_data")
        self.conn.execute("INSERT INTO macro_data SELECT * FROM df")
        print(f"  DuckDB: {len(df)} macro rows inserted")

    def upsert_news_sentiment(self, df: pd.DataFrame):
        if len(df) == 0:
            return
        cols = [
            "title",
            "description",
            "source",
            "url",
            "published_at",
            "query",
            "vader_compound",
            "vader_pos",
            "vader_neg",
            "textblob_polarity",
            "textblob_subjectivity",
            "fetched_at",
        ]
        for col in cols:
            if col not in df.columns:
                df[col] = None
        df = df[cols].copy()
        df = df.rename(columns={"source": "source_name"})
        df = df.drop_duplicates(subset=["url"], keep="last")
        self.conn.execute("INSERT OR REPLACE INTO news_sentiment SELECT * FROM df")
        print(f"  DuckDB: {len(df)} news rows inserted")

    def query(self, sql: str) -> pd.DataFrame:
        return self.conn.execute(sql).fetchdf()

    def get_latest_price(self, symbol: str) -> dict:
        df = self.conn.execute(
            """
            SELECT symbol, close, timestamp
            FROM market_data
            WHERE symbol = ? AND close IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        """,
            [symbol],
        ).fetchdf()
        if len(df) > 0:
            return df.iloc[0].to_dict()
        return {}

    # === LLM News Sentiment Methods ===
    def _init_llm_tables(self):
        """Create LLM news sentiment tables if they don't exist."""
        # Create sequence first
        with contextlib.suppress(Exception):
            self.conn.execute("CREATE SEQUENCE IF NOT EXISTS llm_news_sentiment_seq START 1")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_news_sentiment (
                id INTEGER DEFAULT (nextval('llm_news_sentiment_seq')),
                url VARCHAR UNIQUE,
                title VARCHAR,
                source VARCHAR,
                published_at TIMESTAMP,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model VARCHAR DEFAULT 'qwen3.5:9b',
                tickers VARCHAR,
                sentiment VARCHAR,
                impact VARCHAR,
                categories VARCHAR,
                entities VARCHAR,
                summary VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS headline_embeddings (
                url VARCHAR PRIMARY KEY,
                embedding_id UBIGINT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def get_unembedded_headlines(self, limit: int = 500) -> pd.DataFrame:
        """Headlines with sentiment but no embedding yet (for incremental indexing)."""
        return self.conn.execute(
            """
            SELECT s.url, s.title
            FROM llm_news_sentiment s
            LEFT JOIN headline_embeddings e ON s.url = e.url
            WHERE e.url IS NULL AND s.title IS NOT NULL AND s.title != ''
            ORDER BY s.analyzed_at
            LIMIT ?
        """,
            [limit],
        ).fetchdf()

    def mark_embedded(self, url: str, embedding_id: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO headline_embeddings (url, embedding_id) VALUES (?, ?)",
            [url, embedding_id],
        )

    def upsert_llm_news_sentiment(self, articles: list, overall: dict | None = None, source: str = "") -> int:
        """Insert/update LLM-analyzed news articles. Returns count written.

        ``overall`` (optional) is a report-level summary dict merged into each
        article as fallback defaults (e.g. overall_sentiment -> sentiment).
        ``source`` (optional) is the default source for articles missing one.
        """
        if not articles:
            return 0
        overall = overall or {}
        written = 0
        for a in articles:
            try:
                row = dict(a)
                row.setdefault("sentiment", overall.get("overall_sentiment", "neutral"))
                if not row.get("summary") and overall.get("action_items_th"):
                    row["summary"] = "; ".join(str(x) for x in overall["action_items_th"])[:500]
                if not row.get("source") and source:
                    row["source"] = source
                self.conn.execute(
                    """
                    INSERT INTO llm_news_sentiment
                        (url, title, source, published_at, analyzed_at, model,
                         tickers, sentiment, impact, categories, entities, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (url) DO UPDATE SET
                        tickers = excluded.tickers,
                        sentiment = excluded.sentiment,
                        impact = excluded.impact,
                        summary = excluded.summary,
                        analyzed_at = excluded.analyzed_at
                """,
                    [
                        row.get("url", ""),
                        row.get("title", "")[:200],
                        row.get("source", ""),
                        row.get("published_at"),
                        row.get("analyzed_at", datetime.now().isoformat()),
                        row.get("model", "qwen3.5:9b"),
                        row.get("tickers", ""),
                        row.get("sentiment", "neutral"),
                        row.get("impact", "low"),
                        row.get("categories", ""),
                        row.get("entities", "[]"),
                        row.get("summary", "")[:500],
                    ],
                )
                written += 1
            except Exception as e:
                print(f"  DuckDB upsert error: {e}")
        return written

    def get_llm_sentiment_data(self, days: int = 30) -> pd.DataFrame:
        """Get LLM sentiment data for backtesting."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return self.conn.execute(
            """
            SELECT url, title, source, analyzed_at, tickers, sentiment, impact, summary
            FROM llm_news_sentiment
            WHERE analyzed_at > ?
            ORDER BY analyzed_at DESC
        """,
            [cutoff],
        ).fetchdf()

    def query_llm_sentiment(self, hours: int = 1) -> pd.DataFrame:
        """Get LLM sentiment rows analyzed within the last ``hours``."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return self.conn.execute(
            """
            SELECT url, title, source, analyzed_at, tickers, sentiment, impact, summary
            FROM llm_news_sentiment
            WHERE analyzed_at > ?
            ORDER BY analyzed_at DESC
        """,
            [cutoff],
        ).fetchdf()

    def get_sentiment_by_ticker(self, ticker: str, days: int = 30) -> pd.DataFrame:
        """Get sentiment data for a specific ticker."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return self.conn.execute(
            """
            SELECT analyzed_at, sentiment, impact, summary
            FROM llm_news_sentiment
            WHERE tickers LIKE '%' || ? || '%'
              AND analyzed_at > ?
            ORDER BY analyzed_at DESC
        """,
            [ticker, cutoff],
        ).fetchdf()

    def count_llm_sentiment_pairs(self) -> int:
        """Count rows with both sentiment and tickers (usable for backtest)."""
        result = self.conn.execute("""
            SELECT COUNT(*) FROM llm_news_sentiment
            WHERE tickers IS NOT NULL AND tickers != ''
              AND sentiment IN ('positive', 'negative', 'neutral')
        """).fetchone()
        return result[0] if result else 0

    def get_sentiment_summary(self, days: int = 7) -> pd.DataFrame:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return self.conn.execute(
            """
            SELECT
                query,
                COUNT(*) as articles,
                AVG(vader_compound) as avg_sentiment,
                AVG(textblob_polarity) as avg_polarity
            FROM news_sentiment
            WHERE fetched_at > ?
            GROUP BY query
            ORDER BY avg_sentiment DESC
        """,
            [cutoff],
        ).fetchdf()

    def backup(self):
        """Backup DuckDB to timestamped file"""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"quant_os_{ts}.duckdb"
        self.conn.execute(f"BACKUP DATABASE TO '{backup_path}'")
        print(f"  DuckDB backup: {backup_path}")
        return backup_path

    def close(self):
        self.conn.close()

    # ── Task 6: tick query layer ──────────────────────────────────────
    def register_tick_views(
        self,
        ticks_glob: str = "data/ticks/*.parquet",
        backfill_globs: dict[str, str] | None = None,
    ) -> None:
        """Register tick views + tick_coverage_summary table.

        Creates v_ticks, v_backfill_{source} (one per backfill_globs entry),
        v_ticks_combined (UNION ALL) and tick_coverage_summary (PK
        (symbol, date, source), transaction-wrapped). View creation is
        DEFERRED until a glob actually matches (DuckDB read_parquet raises on
        zero-match globs) — query_ticks/query_funding re-attempt on every call,
        so a view registered before the first daemon flush still sees the
        newly written parquet.

        ticks_glob/backfill_globs are controlled config values, never user
        input — the parameterized query_ticks is where injection is blocked.
        """
        self._ticks_glob = ticks_glob
        self._backfill_globs = backfill_globs
        with self.conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS tick_coverage_summary ("
                "symbol VARCHAR, date DATE, source VARCHAR, "
                "total_ticks BIGINT, valid_ticks BIGINT, stale_ticks BIGINT, "
                "gap_ticks BIGINT, out_of_order_ticks BIGINT, updated_at TIMESTAMP, "
                "PRIMARY KEY (symbol, date, source))"
            )
            cur.execute("COMMIT")
        self._ensure_tick_views()

    def _ensure_tick_views(self) -> None:
        """(Re)create views if any configured glob now matches files."""
        import glob as pyglob

        if self._ticks_glob is None:
            return
        parts: list[str] = []
        with self.conn.cursor() as cur:
            cur.execute("BEGIN")
            if pyglob.glob(self._ticks_glob):
                cur.execute(f"CREATE OR REPLACE VIEW v_ticks AS {_tick_view_sql(self._ticks_glob)}")
                parts.append("SELECT * FROM v_ticks")
            for src, glob in (self._backfill_globs or {}).items():
                if not pyglob.glob(glob):
                    continue
                view = f"v_backfill_{src}"
                if src == "binance_funding":
                    # Funding is NOT tick-shaped (no bid/ask) — its own view only.
                    cur.execute(
                        f"CREATE OR REPLACE VIEW {view} AS "
                        f"SELECT time_msc, timestamp_utc, symbol, funding_rate, mark_price, source "
                        f"FROM read_parquet('{glob}')"
                    )
                    continue
                cur.execute(f"CREATE OR REPLACE VIEW {view} AS {_tick_view_sql(glob)}")
                parts.append(f"SELECT * FROM {view}")
            if parts:
                cur.execute("CREATE OR REPLACE VIEW v_ticks_combined AS " + " UNION ALL ".join(parts))
                self._tick_views_created = True
            cur.execute("COMMIT")

    def query_ticks(
        self,
        symbol: str,
        start_msc: int,
        end_msc: int,
        view: str = "v_ticks_combined",
    ) -> pd.DataFrame:
        if view not in TICK_VIEW_WHITELIST:
            raise ValueError(f"view not in whitelist: {view}")
        self._ensure_tick_views()
        with self.conn.cursor() as cur:
            return cur.execute(
                f"SELECT time_msc, symbol, bid, ask, last, volume, source, data_quality "
                f"FROM {view} WHERE symbol = ? AND time_msc BETWEEN ? AND ? "
                f"ORDER BY time_msc ASC",
                [symbol, start_msc, end_msc],
            ).fetchdf()

    def query_funding(self, symbol: str, start_msc: int, end_msc: int) -> pd.DataFrame:
        """Funding rows are not tick-shaped — dedicated whitelisted accessor."""
        self._ensure_tick_views()
        with self.conn.cursor() as cur:
            return cur.execute(
                "SELECT timestamp_utc, symbol, funding_rate, mark_price, source "
                "FROM v_backfill_binance_funding "
                "WHERE symbol = ? AND time_msc BETWEEN ? AND ? ORDER BY timestamp_utc ASC",
                [symbol, start_msc, end_msc],
            ).fetchdf()

    def upsert_coverage_summary(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)  # noqa: F841 — referenced via DuckDB replacement scan (`FROM df`)
        with self.conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute(
                "DELETE FROM tick_coverage_summary "
                "WHERE (symbol, date, source) IN "
                "(SELECT symbol, date::DATE AS date, source FROM df)"
            )
            cur.execute("INSERT INTO tick_coverage_summary SELECT * FROM df")
            cur.execute("COMMIT")
