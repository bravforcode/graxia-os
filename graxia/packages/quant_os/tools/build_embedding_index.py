"""
build_embedding_index.py — Embed headlines and index them for similarity search.

Reads llm_news_sentiment rows that haven't been embedded yet, embeds their
titles, and writes the vectors to both a turbovec IdMapIndex (fast local
similarity search) and the existing ChromaStore news collection (kept in
sync with the same vectors). Incremental: re-running only processes rows
added since the last run.

Usage:
    python tools/build_embedding_index.py              # embed all pending
    python tools/build_embedding_index.py --limit 100  # cap this run
    python tools/build_embedding_index.py --status     # show index size
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

import numpy as np
import turbovec

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
from embeddings import embed_texts, headline_id  # noqa: E402
from storage.chroma_store import ChromaStore  # noqa: E402
from storage.duckdb_store import DuckDBStore  # noqa: E402

INDEX_PATH = BASE_DIR / "data_pipeline" / "storage" / "headline_index.tvim"
EMBED_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2


def load_or_create_index() -> turbovec.IdMapIndex:
    if INDEX_PATH.exists():
        return turbovec.IdMapIndex.load(str(INDEX_PATH))
    return turbovec.IdMapIndex(dim=EMBED_DIM)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000, help="Max headlines to embed this run")
    parser.add_argument("--status", action="store_true", help="Show current index size")
    args = parser.parse_args()

    duck = DuckDBStore()

    if args.status:
        indexed = duck.conn.execute("SELECT COUNT(*) FROM headline_embeddings").fetchone()[0]
        pending = len(duck.get_unembedded_headlines(limit=1_000_000))
        print(f"Indexed headlines: {indexed}")
        print(f"Pending (not yet embedded): {pending}")
        if INDEX_PATH.exists():
            idx = turbovec.IdMapIndex.load(str(INDEX_PATH))
            print(f"turbovec index size: {len(idx)} vectors, dim={idx.dim}")
        else:
            print("turbovec index: not yet created")
        duck.close()
        return

    pending = duck.get_unembedded_headlines(limit=args.limit)
    if len(pending) == 0:
        print("Nothing to embed — all headlines already indexed.")
        duck.close()
        return

    print(f"Embedding {len(pending)} headlines...")
    t0 = time.time()
    vectors = embed_texts(pending["title"].tolist())
    elapsed = time.time() - t0
    print(f"  Embedded in {elapsed:.1f}s ({elapsed / len(pending):.3f}s/headline)")

    ids = np.array([headline_id(u) for u in pending["url"]], dtype=np.uint64)

    index = load_or_create_index()
    index.add_with_ids(vectors, ids)
    index.write(str(INDEX_PATH))
    print(f"  turbovec: {len(index)} vectors total, wrote {INDEX_PATH.name}")

    chroma = ChromaStore()
    articles = [{"title": t, "url": u} for t, u in zip(pending["title"], pending["url"], strict=True)]
    chroma.add_news(articles, embeddings=vectors.tolist())

    for url, eid in zip(pending["url"], ids.tolist(), strict=True):
        duck.mark_embedded(url, eid)

    total = duck.conn.execute("SELECT COUNT(*) FROM headline_embeddings").fetchone()[0]
    print(f"\nDone. {total} headlines indexed total.")
    duck.close()


if __name__ == "__main__":
    main()
