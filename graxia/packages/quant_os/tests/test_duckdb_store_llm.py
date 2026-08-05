"""Regression tests for DuckDBStore LLM news-sentiment methods.

Covers the signature fix for ``upsert_llm_news_sentiment`` (now accepts
``overall`` and ``source`` kwargs to match tools/ callers) and the new
``query_llm_sentiment(hours=...)`` method used by tools/edge_analysis.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data_pipeline.storage.duckdb_store import DuckDBStore


@pytest.fixture()
def store(tmp_path) -> DuckDBStore:
    duck = DuckDBStore(db_path=str(tmp_path / "test.duckdb"))
    yield duck
    duck.close()


def test_upsert_one_arg_matches_realtime_daemon(store: DuckDBStore) -> None:
    """realtime_daemon calls with a single articles argument; must not break."""
    articles = [
        {
            "url": "https://example.com/1",
            "title": "Fed raises rates",
            "sentiment": "negative",
            "tickers": "SPY",
        }
    ]
    written = store.upsert_llm_news_sentiment(articles)
    assert written == 1
    df = store.query_llm_sentiment(hours=1)
    assert len(df) == 1
    assert df.iloc[0]["sentiment"] == "negative"


def test_upsert_three_args_matches_agent_loop(store: DuckDBStore) -> None:
    """agent_loop/edge_analysis pass (articles, overall, source); must not raise."""
    articles = [
        {"url": "https://example.com/2", "title": "Oil spikes"},
    ]
    overall = {"overall_sentiment": "positive", "action_items_th": ["Buy oil"]}
    written = store.upsert_llm_news_sentiment(articles, overall, "research")
    assert written == 1
    df = store.query_llm_sentiment(hours=1)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["sentiment"] == "positive"
    assert row["source"] == "research"
    assert "Buy oil" in row["summary"]


def test_upsert_article_fields_win_over_overall(store: DuckDBStore) -> None:
    """Per-article sentiment/source must not be overridden by overall kwargs."""
    articles = [
        {"url": "https://example.com/3", "title": "Mixed", "sentiment": "neutral", "source": "rss"},
    ]
    overall = {"overall_sentiment": "positive"}
    store.upsert_llm_news_sentiment(articles, overall, "research")
    df = store.query_llm_sentiment(hours=1)
    assert df.iloc[0]["sentiment"] == "neutral"
    assert df.iloc[0]["source"] == "rss"


def test_upsert_empty_articles_returns_zero(store: DuckDBStore) -> None:
    assert store.upsert_llm_news_sentiment([]) == 0
    assert store.upsert_llm_news_sentiment([], {"overall_sentiment": "x"}, "src") == 0


def test_upsert_idempotent_on_url_conflict(store: DuckDBStore) -> None:
    """Same URL twice -> one row, later sentiment wins (ON CONFLICT update)."""
    base = {"url": "https://example.com/4", "title": "Repeat", "sentiment": "negative"}
    store.upsert_llm_news_sentiment([base])
    base["sentiment"] = "positive"
    store.upsert_llm_news_sentiment([base])
    df = store.query_llm_sentiment(hours=1)
    assert len(df) == 1
    assert df.iloc[0]["sentiment"] == "positive"


def test_query_llm_sentiment_respects_hours_window(store: DuckDBStore) -> None:
    old_ts = (datetime.now() - timedelta(hours=6)).isoformat()
    store.upsert_llm_news_sentiment(
        [
            {"url": "https://example.com/new", "title": "Fresh", "analyzed_at": datetime.now().isoformat()},
            {"url": "https://example.com/old", "title": "Stale", "analyzed_at": old_ts},
        ]
    )
    recent = store.query_llm_sentiment(hours=1)
    assert len(recent) == 1
    assert recent.iloc[0]["title"] == "Fresh"
