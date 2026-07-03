"""
storage/duckdb_store.py — DuckDB Storage Layer for Analytics
"""
import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DUCKDB_PATH, BACKUP_DIR


class DuckDBStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DUCKDB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._init_tables()

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
        cols = ["title", "description", "source", "url", "published_at", "query",
                "vader_compound", "vader_pos", "vader_neg", "textblob_polarity",
                "textblob_subjectivity", "fetched_at"]
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
        df = self.conn.execute("""
            SELECT symbol, close, timestamp
            FROM market_data
            WHERE symbol = ? AND close IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        """, [symbol]).fetchdf()
        if len(df) > 0:
            return df.iloc[0].to_dict()
        return {}

    def get_sentiment_summary(self, days: int = 7) -> pd.DataFrame:
        return self.conn.execute(f"""
            SELECT
                query,
                COUNT(*) as articles,
                AVG(vader_compound) as avg_sentiment,
                AVG(textblob_polarity) as avg_polarity
            FROM news_sentiment
            WHERE fetched_at > CURRENT_TIMESTAMP - INTERVAL '{days} days'
            GROUP BY query
            ORDER BY avg_sentiment DESC
        """).fetchdf()

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
