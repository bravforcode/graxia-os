import redis
import json
import hashlib
from typing import Optional, Dict, Any, Tuple
import numpy as np

# In a real production setup, use a real embedding model (like sentence-transformers or OpenAI)
# For the sake of this milestone implementation, we'll stub the embedding generator
def generate_embedding(text: str) -> np.ndarray:
    """
    Stub for generating a 1536-dimensional embedding.
    In prod, this calls OpenAI or a local model.
    """
    # Deterministic dummy embedding for testing cache hits
    h = hashlib.md5(text.encode()).digest()
    np.random.seed(int.from_bytes(h, 'little') % (2**32 - 1))
    return np.random.rand(1536)

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Computes cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

class SemanticCache:
    """
    Intercepts incoming LLM queries and returns cached responses if the 
    semantic similarity is above the threshold (e.g., 0.92).
    """
    def __init__(self, redis_url: str = "redis://localhost:6379/1", threshold: float = 0.92):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.threshold = threshold
        self.key_prefix = "semcache:"

    def _get_all_cached_entries(self) -> Dict[str, Tuple[np.ndarray, str]]:
        """
        Retrieves all cached embeddings and responses. 
        In production, use Qdrant or Redis Search (RediSearch) for vector similarity!
        This is a naive O(N) scan for demonstration purposes.
        """
        entries = {}
        for key in self.redis_client.scan_iter(f"{self.key_prefix}*"):
            data = self.redis_client.hgetall(key)
            if 'embedding' in data and 'response' in data:
                # Convert back to numpy array
                embedding = np.array(json.loads(data['embedding']))
                entries[key] = (embedding, data['response'])
        return entries

    def get_cached_response(self, query: str) -> Optional[str]:
        """
        Checks if a semantically similar query exists.
        Returns the cached response or None.
        """
        query_embedding = generate_embedding(query)
        entries = self._get_all_cached_entries()
        
        best_match = None
        highest_score = 0.0
        
        for key, (cached_embedding, response) in entries.items():
            score = cosine_similarity(query_embedding, cached_embedding)
            if score > highest_score:
                highest_score = score
                best_match = response
                
        if highest_score >= self.threshold:
            print(f"[Semantic Cache] Hit! Score: {highest_score:.4f}")
            return best_match
            
        print(f"[Semantic Cache] Miss. Highest score: {highest_score:.4f}")
        return None

    def set_cached_response(self, query: str, response: str):
        """
        Saves a new query and response to the semantic cache.
        """
        query_embedding = generate_embedding(query)
        
        # Create a unique hash for the key
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        key = f"{self.key_prefix}{query_hash}"
        
        self.redis_client.hset(key, mapping={
            "query": query,
            "embedding": json.dumps(query_embedding.tolist()),
            "response": response
        })
        # Set an expiry for the cache (e.g., 7 days)
        self.redis_client.expire(key, 604800)
        print(f"[Semantic Cache] Cached new response for query hash {query_hash[:8]}")

# Global Instance
semantic_cache = SemanticCache()
