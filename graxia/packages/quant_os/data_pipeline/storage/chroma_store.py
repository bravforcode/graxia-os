"""
storage/chroma_store.py — ChromaDB Storage Layer for Vectors
"""
import chromadb
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_PATH


def _make_id(prefix: str, text: str) -> str:
    """Deterministic ID from text (hashlib, not Python hash)"""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


class ChromaStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(CHROMA_PATH)
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.db_path)
        self._init_collections()

    def _init_collections(self):
        self.news_collection = self.client.get_or_create_collection(
            name="news_embeddings",
            metadata={"hnsw:space": "cosine"}
        )
        self.strategy_collection = self.client.get_or_create_collection(
            name="strategy_embeddings",
            metadata={"hnsw:space": "cosine"}
        )
        self.research_collection = self.client.get_or_create_collection(
            name="research_embeddings",
            metadata={"hnsw:space": "cosine"}
        )

    def add_news(self, articles: list[dict]):
        if not articles:
            return
        ids = []
        documents = []
        metadatas = []
        for a in articles:
            title = a.get("title", "")
            url = a.get("url", "")
            doc = f"{title} {a.get('description', '')}"
            ids.append(_make_id("news", url or title))
            documents.append(doc)
            metadatas.append({
                "source": str(a.get("source", a.get("source_name", ""))),
                "query": str(a.get("query", "")),
                "published_at": str(a.get("published_at", "")),
                "vader_compound": float(a.get("vader_compound", 0) or 0),
            })
        self.news_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  ChromaDB: {len(articles)} news articles upserted")

    def add_strategy(self, strategies: list[dict]):
        if not strategies:
            return
        ids = [_make_id("strat", s.get("name", "")) for s in strategies]
        documents = [f"{s.get('name', '')} {s.get('description', '')}" for s in strategies]
        metadatas = [{
            "name": str(s.get("name", "")),
            "category": str(s.get("category", "")),
            "symbols": str(s.get("symbols", "")),
        } for s in strategies]
        self.strategy_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  ChromaDB: {len(strategies)} strategies upserted")

    def search_news(self, query: str, n_results: int = 5) -> list[dict]:
        results = self.news_collection.query(query_texts=[query], n_results=n_results)
        return results.get("documents", [[]])[0]

    def search_strategies(self, query: str, n_results: int = 5) -> list[dict]:
        results = self.strategy_collection.query(query_texts=[query], n_results=n_results)
        return results.get("documents", [[]])[0]

    def get_collection_stats(self) -> dict:
        return {
            "news": self.news_collection.count(),
            "strategies": self.strategy_collection.count(),
            "research": self.research_collection.count(),
        }

    def close(self):
        pass
