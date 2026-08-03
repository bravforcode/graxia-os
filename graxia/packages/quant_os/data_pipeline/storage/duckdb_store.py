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


class DuckDBStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DUCKDB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
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
