"""
pipeline.py — Main Data Pipeline
"""
import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from sources.market_data import fetch_all_market_data
from sources.macro_data import fetch_all_macro_data
from sources.news_sentiment import fetch_news_with_sentiment
from storage.duckdb_store import DuckDBStore
from storage.chroma_store import ChromaStore
from config import LOG_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"pipeline_{datetime.now():%Y%m%d}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pipeline")


class DataPipeline:
    def __init__(self):
        self.duckdb = DuckDBStore()
        self.chroma = ChromaStore()
        self.results = {}
        self.errors = []

    def run_market_data(self):
        log.info("[1/4] Market Data")
        try:
            data = fetch_all_market_data()
            for source_name, df in data.items():
                if len(df) > 0:
                    self.duckdb.upsert_market_data(df)
                    self.results[source_name] = len(df)
        except Exception as e:
            log.error(f"Market data failed: {e}")
            self.errors.append(("market_data", str(e)))

    def run_macro_data(self):
        log.info("[2/4] Macro Data")
        try:
            df = fetch_all_macro_data()
            if len(df) > 0:
                self.duckdb.upsert_macro_data(df)
                self.results["macro"] = len(df)
        except Exception as e:
            log.error(f"Macro data failed: {e}")
            self.errors.append(("macro_data", str(e)))

    def run_news_sentiment(self):
        log.info("[3/4] News + Sentiment")
        try:
            df = fetch_news_with_sentiment()
            if len(df) > 0:
                self.duckdb.upsert_news_sentiment(df)
                self.chroma.add_news(df.to_dict("records"))
                self.results["news"] = len(df)
        except Exception as e:
            log.error(f"News sentiment failed: {e}")
            self.errors.append(("news_sentiment", str(e)))

    def run_vault_sync(self):
        log.info("[4/4] Vault Strategy Sync")
        try:
            vault_path = Path(r"C:\Users\menum\Documents\ObsidianVault\Second Brain\skills\trading\strategies")
            strategies = []
            for f in vault_path.glob("*.md"):
                if f.name == "Index.md":
                    continue
                content = f.read_text(encoding="utf-8")
                strategies.append({
                    "name": f.stem,
                    "description": content[:500],
                    "category": "strategy",
                    "symbols": "all",
                })
            if strategies:
                self.chroma.add_strategy(strategies)
                self.results["strategies"] = len(strategies)
        except Exception as e:
            log.error(f"Vault sync failed: {e}")
            self.errors.append(("vault_sync", str(e)))

    def run_full_pipeline(self):
        start = datetime.now()
        log.info(f"{'='*60}")
        log.info(f"  DATA PIPELINE — {start:%Y-%m-%d %H:%M:%S}")
        log.info(f"{'='*60}")

        self.run_market_data()
        self.run_macro_data()
        self.run_news_sentiment()
        self.run_vault_sync()

        elapsed = (datetime.now() - start).total_seconds()
        status = "OK" if not self.errors else f"ERRORS: {len(self.errors)}"
        log.info(f"{'='*60}")
        log.info(f"  PIPELINE {status} — {elapsed:.1f}s")
        log.info(f"  Results: {self.results}")
        if self.errors:
            for name, err in self.errors:
                log.error(f"    {name}: {err}")
        log.info(f"{'='*60}")

        self.duckdb.close()
        return self.results


if __name__ == "__main__":
    pipeline = DataPipeline()
    pipeline.run_full_pipeline()
