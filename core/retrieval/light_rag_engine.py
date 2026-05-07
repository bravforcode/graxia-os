import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from lightrag import LightRAG, QueryParam
try:
    from lightrag.llm import google_generativeai_complete, google_generativeai_embedding
except ImportError:
    google_generativeai_complete = None
    google_generativeai_embedding = None
from pathlib import Path

logger = logging.getLogger(__name__)

class LightRAGEngine:
    """
    Priority 3: Graph RAG Engine using LightRAG.
    Provides real multi-hop graph traversal and relationship extraction.
    """
    def __init__(self, working_dir: str = "./graxia_knowledge"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found. LightRAG might fail to initialize.")

        # Initialize LightRAG with Gemini gracefully
        try:
            self.rag = LightRAG(
                working_dir=str(self.working_dir),
                llm_model_func=google_generativeai_complete,
                llm_model_name=self.model,
                embedding_func=google_generativeai_embedding
            )
        except Exception as e:
            logger.error(f"Failed to initialize LightRAG: {e}")
            self.rag = None
        # Ensure API key is in environment for the functions above
        os.environ["GOOGLE_API_KEY"] = self.api_key or ""
        
        logger.info(f"LightRAG initialized in {self.working_dir} using {self.model}")

    async def ingest(self, content: Union[str, List[str]]):
        """Ingests raw text into the knowledge graph."""
        if isinstance(content, str):
            content = [content]
            
        logger.info(f"Ingesting {len(content)} documents into LightRAG...")
        # LightRAG's insert is synchronous in some versions, or async in others.
        # We wrap in to_thread to be safe if it blocks.
        await asyncio.to_thread(self.rag.insert, content)
        logger.info("Ingestion complete.")

    async def query(self, query_text: str, mode: str = "hybrid") -> str:
        """
        Queries the knowledge graph.
        Modes: 'naive', 'local', 'global', 'hybrid'
        """
        logger.info(f"Querying LightRAG (mode: {mode}): {query_text[:50]}...")
        param = QueryParam(mode=mode)
        result = await asyncio.to_thread(self.rag.query, query_text, param)
        return str(result)

# Global singleton
light_rag = LightRAGEngine()
