from typing import List, Optional, Any, Dict
import hashlib
import time
import numpy as np
from pydantic import BaseModel, Field

class CacheEntry(BaseModel):
    """Data stored in the semantic cache."""
    query: str
    query_embedding: List[float]
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ttl: int
    created_at: float = Field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl

class SemanticCache:
    """
    Implements semantic caching for query responses.
    Uses cosine similarity for matching similar queries.
    """
    
    def __init__(self, similarity_threshold: float = 0.95, default_ttl: int = 3600):
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl
        
        # In-memory storage placeholder. 
        # Production: Replace with Redis-OSS with Vector Search capability.
        self._storage: Dict[str, CacheEntry] = {}

    def _generate_hash(self, embedding: List[float]) -> str:
        """Helper to hash embeddings for indexing."""
        # Convert the float list to bytes for hashing
        embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
        return hashlib.sha256(embedding_bytes).hexdigest()

    def get(self, query_embedding: List[float]) -> Optional[str]:
        """
        Retrieves a cached response based on semantic similarity.
        Iterates over the cache (simplified for example).
        Production: Use HNSW or other indexing in a vector DB.
        """
        for entry in list(self._storage.values()):
            if entry.is_expired():
                # Lazy eviction
                continue
            
            sim = self._cosine_similarity(query_embedding, entry.query_embedding)
            if sim >= self.similarity_threshold:
                return entry.response
        
        return None

    def set(self, query: str, query_embedding: List[float], response: str, ttl: Optional[int] = None):
        """Stores a new entry in the semantic cache."""
        entry_ttl = ttl or self.default_ttl
        entry = CacheEntry(
            query=query,
            query_embedding=query_embedding,
            response=response,
            ttl=entry_ttl
        )
        
        # Simple hash-based storage, but 'get' performs the semantic search
        key = self._generate_hash(query_embedding)
        self._storage[key] = entry

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Helper to calculate similarity between two vectors."""
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        return float(dot_product / (norm_v1 * norm_v2))

    def clear_expired(self):
        """Explicitly clear expired entries."""
        keys_to_delete = [k for k, v in self._storage.items() if v.is_expired()]
        for k in keys_to_delete:
            del self._storage[k]
