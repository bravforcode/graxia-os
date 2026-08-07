"""Tests for research report ingestion into Chroma (pipeline-research-20260807).

Covers the new add_research / search_research methods on ChromaStore —
ingesting the XAUUSD research report so downstream code can retrieve it
semantically instead of reading a file directly.
"""

from __future__ import annotations

from data_pipeline.storage.chroma_store import ChromaStore


def _sample_reports():
    return [
        {
            "name": "research_xauusd_report.md",
            "content": "# XAUUSD Deep Research\n\nLiquidity sweep strategy uses stop-loss clusters.",
            "source": "test",
            "updated_at": "2026-08-07 00:00:00",
        },
        {
            "name": "researcher.md",
            "content": "# Research Summary\n\nRisk management rules for XAUUSD positions.",
            "source": "test",
            "updated_at": "2026-08-07 00:00:00",
        },
    ]


def test_add_research_upserts_into_research_collection(tmp_path):
    db_path = str(tmp_path / "chroma")
    store = ChromaStore(db_path=db_path)
    try:
        before = store.research_collection.count()
        store.add_research(_sample_reports())
        after = store.research_collection.count()
        assert after == before + 2
        # idempotent upsert: same names do not duplicate
        store.add_research(_sample_reports())
        assert store.research_collection.count() == after
    finally:
        store.close()


def test_search_research_returns_matching_documents(tmp_path):
    db_path = str(tmp_path / "chroma")
    store = ChromaStore(db_path=db_path)
    try:
        store.add_research(_sample_reports())
        hits = store.search_research("liquidity sweep", n_results=2)
        assert len(hits) > 0
        joined = " ".join(hits).lower()
        assert "liquidity" in joined
    finally:
        store.close()


def test_add_research_empty_noop(tmp_path):
    db_path = str(tmp_path / "chroma")
    store = ChromaStore(db_path=db_path)
    try:
        before = store.research_collection.count()
        store.add_research([])
        assert store.research_collection.count() == before
    finally:
        store.close()
