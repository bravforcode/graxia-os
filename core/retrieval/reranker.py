from typing import List, Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field

class SearchResult(BaseModel):
    id: str
    score: float
    text: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Reranker:
    """
    Reranker provides methods to refine search results using sophisticated models
    and diversity-promoting algorithms.
    """
    
    def cross_encode_rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """
        Placeholder for Cross-encoder reranking (e.g., Cohere, BGE-Reranker).
        Cross-encoders process query and document pairs simultaneously for higher accuracy.
        """
        # TODO: Integrate with external Reranking API or local model
        # Currently returns results sorted by their existing scores
        return sorted(results, key=lambda x: x.score, reverse=True)

    def mmr_rerank(
        self, 
        query_embedding: List[float], 
        results: List[SearchResult], 
        lambda_val: float = 0.5, 
        top_k: int = 10
    ) -> List[SearchResult]:
        """
        Maximal Marginal Relevance (MMR) for diversity-aware reranking.
        
        Formula: MMR = argmax [ λ * sim(q, d) - (1-λ) * max_sim(d, already_selected) ]
        
        Args:
            query_embedding: Vector representation of the user query.
            results: List of SearchResults (must include embeddings).
            lambda_val: Balance between relevance (1.0) and diversity (0.0). Default 0.5.
            top_k: Number of results to return.
        """
        if not results:
            return []
            
        # Filter results that have embeddings
        valid_results = [r for r in results if r.embedding is not None]
        if not valid_results:
            return results[:top_k]

        selected_indices: List[int] = []
        candidate_indices = list(range(len(valid_results)))
        
        query_vec = np.array(query_embedding)
        doc_vecs = [np.array(r.embedding) for r in valid_results]

        # Normalize vectors for cosine similarity
        query_vec = query_vec / np.linalg.norm(query_vec)
        doc_vecs = [v / np.linalg.norm(v) if np.linalg.norm(v) > 0 else v for v in doc_vecs]

        while len(selected_indices) < min(top_k, len(valid_results)):
            best_mmr = -1e9
            best_idx = -1

            for idx in candidate_indices:
                # Relevance: similarity to query
                relevance = np.dot(query_vec, doc_vecs[idx])
                
                # Diversity: max similarity to any already selected document
                if not selected_indices:
                    diversity = 0.0
                else:
                    diversity = max(np.dot(doc_vecs[idx], doc_vecs[s_idx]) for s_idx in selected_indices)
                
                mmr_score = lambda_val * relevance - (1 - lambda_val) * diversity
                
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx

            selected_indices.append(best_idx)
            candidate_indices.remove(best_idx)

        return [valid_results[i] for i in selected_indices]
