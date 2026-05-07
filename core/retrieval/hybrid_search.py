from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import math
from collections import Counter
import re

class SearchResult(BaseModel):
    """Represents a single search result with its source text and metadata."""
    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

def filter_by_metadata(results: List[SearchResult], metadata_filter: Optional[Dict[str, Any]]) -> List[SearchResult]:
    """Priority 3: Filter search results by exact metadata match before processing."""
    if not metadata_filter:
        return results
    filtered = []
    for res in results:
        match = True
        for k, v in metadata_filter.items():
            if res.metadata.get(k) != v:
                match = False
                break
        if match:
            filtered.append(res)
    return filtered

class BM25Searcher:
    """
    Priority 3: Simple BM25 implementation for sparse retrieval without external dependencies.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = []
        self.avgdl = 0
        self.docs = []
        
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\w+', text.lower())

    def fit(self, docs: List[SearchResult]):
        self.docs = docs
        self.doc_len = []
        self.doc_freqs = []
        df = Counter()
        
        for doc in docs:
            tokens = self._tokenize(doc.text)
            self.doc_len.append(len(tokens))
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            for token in freq.keys():
                df[token] += 1
                
        num_docs = len(docs)
        self.avgdl = sum(self.doc_len) / num_docs if num_docs else 0
        
        # Compute IDF
        for token, freq in df.items():
            self.idf[token] = math.log(1 + (num_docs - freq + 0.5) / (freq + 0.5))
            
    def search(self, query: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        query_tokens = self._tokenize(query)
        scores = []
        
        for idx, doc in enumerate(self.docs):
            if metadata_filter:
                match = all(doc.metadata.get(k) == v for k, v in metadata_filter.items())
                if not match:
                    continue
                    
            score = 0.0
            d_len = self.doc_len[idx]
            freqs = self.doc_freqs[idx]
            
            avgdl_safe = self.avgdl if self.avgdl > 0 else 1.0
            
            for token in query_tokens:
                if token not in freqs:
                    continue
                freq = freqs[token]
                num = freq * (self.k1 + 1)
                den = freq + self.k1 * (1 - self.b + self.b * d_len / avgdl_safe)
                score += self.idf.get(token, 0) * (num / den)
                
            if score > 0:
                scores.append(SearchResult(id=doc.id, score=score, text=doc.text, metadata=doc.metadata))
                
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores[:top_k]

class HybridSearcher:
    """
    Priority 3: HybridSearcher combines Vector (Dense) and BM25 (Sparse) search results
    using Reciprocal Rank Fusion (RRF) and pre-filters using Metadata.
    
    RRF Formula: Score_RRF(d) = Σ 1/(k + rank_i(d))
    """
    def __init__(self, k: int = 60, alpha: float = 0.7):
        """
        Initialize the HybridSearcher.
        
        Args:
            k: Smoothing constant for RRF (default 60).
            alpha: Weighting factor for vector results (default 0.7).
                   Score = alpha * RRF_vector + (1 - alpha) * RRF_bm25
        """
        self.k = k
        self.alpha = alpha

    def _calculate_rrf(self, rank: int) -> float:
        """Helper to calculate RRF component for a given rank."""
        return 1.0 / (self.k + rank)

    def search(
        self, 
        vector_results: List[SearchResult], 
        bm25_results: List[SearchResult],
        metadata_filter: Optional[Dict[str, Any]] = None,
        alpha: Optional[float] = None
    ) -> List[SearchResult]:
        """
        Merges results from two search engines using weighted RRF.
        Applies metadata filtering before fusing.
        
        Args:
            vector_results: Results from vector database.
            bm25_results: Results from keyword search.
            metadata_filter: Optional dict of metadata to filter by (e.g. {'project': 'A', 'file_type': 'pdf'})
            alpha: Optional override for the weighting parameter.
            
        Returns:
            Sorted list of SearchResult objects.
        """
        effective_alpha = alpha if alpha is not None else self.alpha
        
        # Apply metadata filtering first to reduce search space
        v_results = filter_by_metadata(vector_results, metadata_filter)
        b_results = filter_by_metadata(bm25_results, metadata_filter)

        doc_map: Dict[str, Dict[str, Any]] = {}

        # Process Vector Results
        for rank, res in enumerate(v_results, 1):
            if res.id not in doc_map:
                doc_map[res.id] = {"vector_rank": rank, "bm25_rank": None, "result": res}
            else:
                doc_map[res.id]["vector_rank"] = rank

        # Process BM25 Results
        for rank, res in enumerate(b_results, 1):
            if res.id not in doc_map:
                doc_map[res.id] = {"vector_rank": None, "bm25_rank": rank, "result": res}
            else:
                doc_map[res.id]["bm25_rank"] = rank

        hybrid_results = []
        for doc_id, data in doc_map.items():
            v_rank = data["vector_rank"]
            b_rank = data["bm25_rank"]
            
            # Calculate weighted RRF score
            v_rrf = self._calculate_rrf(v_rank) if v_rank is not None else 0.0
            b_rrf = self._calculate_rrf(b_rank) if b_rank is not None else 0.0
            
            combined_score = (effective_alpha * v_rrf) + ((1 - effective_alpha) * b_rrf)
            
            res = data["result"]
            hybrid_results.append(SearchResult(
                id=res.id,
                score=combined_score,
                text=res.text,
                metadata=res.metadata
            ))

        # Sort by score descending
        hybrid_results.sort(key=lambda x: x.score, reverse=True)
        return hybrid_results
