"""
embeddings.py — Headline text embeddings for similarity search.

Lightweight sentence-transformers model, lazy-loaded once per process
(mirrors the lazy-load pattern in tools/finbert_validate.py).
"""

import hashlib

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def get_embedder():
    """Lazy-load and cache the embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts. Returns (n, 384) float32, L2-normalized (cosine-ready)."""
    model = get_embedder()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return vectors.astype(np.float32)


def headline_id(url: str) -> int:
    """Deterministic uint64 id for a headline URL (first 8 bytes of its md5 digest)."""
    return int(hashlib.md5(url.encode("utf-8")).hexdigest()[:16], 16)
