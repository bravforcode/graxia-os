"""
orchestration/flows.py — Prefect Workflows for Data Pipeline
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect import flow, task
from prefect.tasks import task_input_hash


@task(retries=3, retry_delay_seconds=60, cache_key_fn=task_input_hash, cache_expiration=3600)
def fetch_market_data_task():
    """Prefect task: Fetch market data"""
    from sources.market_data import fetch_all_market_data
    return fetch_all_market_data()


@task(retries=3, retry_delay_seconds=60)
def fetch_macro_data_task():
    """Prefect task: Fetch macro data"""
    from sources.macro_data import fetch_all_macro_data
    return fetch_all_macro_data()


@task(retries=3, retry_delay_seconds=60)
def fetch_news_sentiment_task():
    """Prefect task: Fetch news + sentiment"""
    from sources.news_sentiment import fetch_news_with_sentiment
    return fetch_news_with_sentiment()


@task
def store_to_duckdb_task(market_data: dict, macro_data, news_data):
    """Prefect task: Store to DuckDB"""
    from storage.duckdb_store import DuckDBStore
    store = DuckDBStore()
    for source_name, df in market_data.items():
        if len(df) > 0:
            store.upsert_market_data(df)
    if len(macro_data) > 0:
        store.upsert_macro_data(macro_data)
    if len(news_data) > 0:
        store.upsert_news_sentiment(news_data)
    store.close()


@task
def store_to_chromadb_task(news_data):
    """Prefect task: Store to ChromaDB"""
    from storage.chroma_store import ChromaStore
    store = ChromaStore()
    if len(news_data) > 0:
        store.add_news(news_data.to_dict("records"))


@flow(name="quant-os-full-pipeline")
def full_pipeline_flow():
    """Main Prefect flow — runs all tasks"""
    print(f"Pipeline started at {datetime.now()}")

    # Fetch data
    market_data = fetch_market_data_task()
    macro_data = fetch_macro_data_task()
    news_data = fetch_news_sentiment_task()

    # Store data
    store_to_duckdb_task(market_data, macro_data, news_data)
    store_to_chromadb_task(news_data)

    print(f"Pipeline completed at {datetime.now()}")


@flow(name="quant-os-market-data")
def market_data_flow():
    """Market data only flow"""
    market_data = fetch_market_data_task()
    from storage.duckdb_store import DuckDBStore
    store = DuckDBStore()
    for source_name, df in market_data.items():
        if len(df) > 0:
            store.upsert_market_data(df)
    store.close()


@flow(name="quant-os-news-sentiment")
def news_sentiment_flow():
    """News + sentiment only flow"""
    news_data = fetch_news_sentiment_task()
    from storage.duckdb_store import DuckDBStore
    from storage.chroma_store import ChromaStore
    duckdb = DuckDBStore()
    chroma = ChromaStore()
    if len(news_data) > 0:
        duckdb.upsert_news_sentiment(news_data)
        chroma.add_news(news_data.to_dict("records"))
    duckdb.close()


if __name__ == "__main__":
    full_pipeline_flow()
