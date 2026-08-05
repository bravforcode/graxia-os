"""Tests for data_pipeline.embeddings — headline embedding + id helpers."""

from __future__ import annotations

import numpy as np
import pytest

from graxia.packages.quant_os.data_pipeline.embeddings import embed_texts, headline_id


class TestHeadlineId:
    def test_deterministic(self):
        url = "https://example.com/article-1"
        assert headline_id(url) == headline_id(url)

    def test_different_urls_differ(self):
        assert headline_id("https://example.com/a") != headline_id("https://example.com/b")

    def test_fits_uint64(self):
        eid = headline_id("https://example.com/article-1")
        assert 0 <= eid < 2**64


class TestEmbedTexts:
    def test_shape_and_dtype(self):
        vectors = embed_texts(["hello world", "another headline"])
        assert vectors.shape == (2, 384)
        assert vectors.dtype == np.float32

    def test_normalized(self):
        vectors = embed_texts(["Fed raises interest rates"])
        norm = np.linalg.norm(vectors[0])
        assert norm == pytest.approx(1.0, abs=1e-4)

    def test_similar_headlines_are_closer(self):
        vectors = embed_texts(
            [
                "Fed raises interest rates by 25 basis points",
                "Federal Reserve hikes rates a quarter point",
                "Local cat show draws record crowds",
            ]
        )
        # normalized vectors -> dot product is cosine similarity
        sim_related = float(np.dot(vectors[0], vectors[1]))
        sim_unrelated = float(np.dot(vectors[0], vectors[2]))
        assert sim_related > sim_unrelated
