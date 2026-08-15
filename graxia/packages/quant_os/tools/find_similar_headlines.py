"""
find_similar_headlines.py — Query the turbovec headline index for similar headlines.

Also doubles as the end-to-end verification for build_embedding_index.py:
if results look topically unrelated, the embedding pipeline (not just the
plumbing) needs a closer look.

Usage:
    python tools/find_similar_headlines.py "Fed raises interest rates"
    python tools/find_similar_headlines.py --url https://example.com/article  --k 10
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import turbovec

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
from embeddings import embed_texts  # noqa: E402
from storage.duckdb_store import DuckDBStore  # noqa: E402

INDEX_PATH = BASE_DIR / "data_pipeline" / "storage" / "headline_index.tvim"


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="Headline text to search for")
    parser.add_argument("--url", help="Use an already-indexed headline's URL as the query instead")
    parser.add_argument("--k", type=int, default=5, help="Number of results")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        print(f"No index found at {INDEX_PATH}. Run tools/build_embedding_index.py first.")
        return

    duck = DuckDBStore()

    if args.url:
        row = duck.conn.execute("SELECT title FROM llm_news_sentiment WHERE url = ?", [args.url]).fetchone()
        if row is None:
            print(f"URL not found in llm_news_sentiment: {args.url}")
            duck.close()
            return
        query_text = row[0]
    elif args.query:
        query_text = args.query
    else:
        print("Provide a query string or --url. See --help.")
        duck.close()
        return

    print(f"Query: {query_text!r}\n")

    vector = embed_texts([query_text])
    index = turbovec.IdMapIndex.load(str(INDEX_PATH))
    scores, ids = index.search(vector, k=args.k)

    for rank, (score, eid) in enumerate(zip(scores[0], ids[0], strict=True), start=1):
        row = duck.conn.execute(
            """
            SELECT s.title, s.source, s.published_at, s.sentiment
            FROM llm_news_sentiment s
            JOIN headline_embeddings e ON s.url = e.url
            WHERE e.embedding_id = ?
        """,
            [int(eid)],
        ).fetchone()
        if row is None:
            continue
        title, source, published_at, sentiment = row
        print(f"{rank}. [{score:.3f}] ({sentiment}, {source}, {published_at})")
        print(f"   {title}")

    duck.close()


if __name__ == "__main__":
    main()
