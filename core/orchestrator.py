import asyncio
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel

from core.providers.base import BaseLLMProvider, BaseEmbeddingProvider
from core.routing.query_intelligence import QueryRewriter, IntentRouter, RewrittenQuery, QueryIntent
from core.memory.semantic_cache import SemanticCache
from core.retrieval.hybrid_search import HybridSearcher, SearchResult
from core.retrieval.reranker import Reranker
from core.optimization.token_budget import TokenBudgetManager, SelectiveContextCompressor
from core.execution.self_consistency import SelfConsistencyRouter
from core.telemetry import TelemetrySystem
from core.logger import logger
from core.exceptions import RetrievalError, LLMProviderError, BudgetExceededError

class OrchestratorConfig(BaseModel):
    use_semantic_cache: bool = True
    use_self_consistency: bool = False
    similarity_threshold: float = 0.95
    top_k: int = 10
    rerank_top_n: int = 5

class IntelligenceOrchestrator:
    """
    The 'Brain' of Brav OS. Orchestrates Query Intelligence, Retrieval, 
    Optimization, and Execution layers with built-in telemetry.
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        embedding_provider: BaseEmbeddingProvider,
        config: Optional[OrchestratorConfig] = None
    ):
        self.llm = llm_provider
        self.embedding = embedding_provider
        self.config = config or OrchestratorConfig()
        
        # Initialize modules
        self.rewriter = QueryRewriter(self.llm)
        self.intent_router = IntentRouter(self.llm)
        self.cache = SemanticCache(similarity_threshold=self.config.similarity_threshold)
        self.hybrid_searcher = HybridSearcher()
        self.reranker = Reranker()
        self.token_manager = TokenBudgetManager()
        self.compressor = SelectiveContextCompressor()
        self.consistency_router = SelfConsistencyRouter()
        self.telemetry = TelemetrySystem()

    async def run(self, query: str, history: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the full intelligence pipeline for a given query.
        """
        try:
            # 1. Start Telemetry & Intelligence
            self.telemetry.latency_tracker.start("total")
            self.telemetry.latency_tracker.start("intelligence")
            
            # Parallel execution of Intent Routing and Query Rewriting
            intent_task = self.intent_router.route(query)
            rewrite_task = self.rewriter.rewrite(query, history)
            
            intent, rewritten_query = await asyncio.gather(intent_task, rewrite_task)
            self.telemetry.latency_tracker.stop("intelligence")
            
            # 2. Semantic Cache Lookup
            if self.config.use_semantic_cache:
                self.telemetry.latency_tracker.start("cache_lookup")
                query_embedding = await self.embedding.get_single_embedding(rewritten_query.standalone_query)
                cached_response = self.cache.get(query_embedding)
                self.telemetry.latency_tracker.stop("cache_lookup")
                
                if cached_response:
                    logger.info("Semantic cache hit.", extra={"query": query[:50]})
                    self.telemetry.token_auditor.add_usage(cached=100) # Mock cached savings
                    self.telemetry.latency_tracker.stop("total")
                    return {
                        "response": cached_response,
                        "intent": intent,
                        "metadata": {"source": "cache"},
                        "telemetry": self.telemetry.get_report()
                    }

            # 3. Retrieval (Hybrid Search + Reranking)
            self.telemetry.latency_tracker.start("retrieval")
            
            try:
                # Mocking retrieval from a source
                retrieval_tasks = [
                    self._mock_retrieval(q) for q in [rewritten_query.standalone_query] + rewritten_query.alternatives
                ]
                all_results = await asyncio.gather(*retrieval_tasks)
                flat_results = [res for sublist in all_results for res in sublist]
                
                # Hybrid Search
                hybrid_results = self.hybrid_searcher.search(flat_results, [])
                
                # Reranking
                reranked_results = self.reranker.cross_encode_rerank(query, hybrid_results)
                top_results = reranked_results[:self.config.top_k]
            except Exception as e:
                logger.error(f"Retrieval error: {str(e)}")
                raise RetrievalError(detail=str(e))
                
            self.telemetry.latency_tracker.stop("retrieval")

            # 4. Context Optimization
            self.telemetry.latency_tracker.start("optimization")
            context_text = "\n".join([r.text for r in top_results])
            compressed_context = self.compressor.compress(query, context_text)
            
            # Token Budget Validation
            current_usage = {"query": 100, "retrieved": len(compressed_context) // 4}
            limits_valid = self.token_manager.validate_limits(current_usage)
            if not all(limits_valid.values()):
                logger.warning(f"Budget exceeded: {limits_valid}")
                raise BudgetExceededError(detail=limits_valid)
                
            self.telemetry.latency_tracker.stop("optimization")

            # 5. Execution (LLM Generation)
            self.telemetry.latency_tracker.start("llm_generation")
            prompt = f"Context: {compressed_context}\n\nQuery: {query}\nAnswer:"
            
            try:
                if self.config.use_self_consistency:
                    consistency_result = await self.consistency_router.run_parallel_sampling(prompt, self.llm)
                    response_text = consistency_result.response
                    metadata = {"consistency": consistency_result.model_dump()}
                else:
                    llm_response = await self.llm.generate_response(prompt)
                    response_text = llm_response["content"]
                    self.telemetry.token_auditor.add_usage(
                        prompt=llm_response["usage"]["prompt_tokens"],
                        completion=llm_response["usage"]["completion_tokens"]
                    )
                    metadata = {"model": llm_response["model"]}
            except Exception as e:
                logger.error(f"LLM Provider error: {str(e)}")
                raise LLMProviderError(detail=str(e))

            self.telemetry.latency_tracker.stop("llm_generation")

            # 6. Finalize
            if self.config.use_semantic_cache:
                self.cache.set(rewritten_query.standalone_query, query_embedding, response_text)

            self.telemetry.latency_tracker.stop("total")
            
            return {
                "response": response_text,
                "intent": intent,
                "rewritten_query": rewritten_query,
                "metadata": metadata,
                "telemetry": self.telemetry.get_report()
            }

        except (RetrievalError, LLMProviderError, BudgetExceededError):
            # Re-raise domain exceptions to be handled by the API layer
            raise
        except Exception as e:
            logger.exception("Unexpected orchestration error")
            return {
                "error": str(e),
                "telemetry": self.telemetry.get_report()
            }

    async def _mock_retrieval(self, query: str) -> List[SearchResult]:
        """Simulates a retrieval call to a vector database."""
        await asyncio.sleep(0.1) # Simulate network latency
        return [
            SearchResult(id=f"doc_{i}", score=0.9 - (i*0.1), text=f"This is some retrieved content for {query} - part {i}")
            for i in range(3)
        ]
