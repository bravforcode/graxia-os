from enum import Enum
from typing import List, Optional, Type, Dict
from pydantic import BaseModel, Field
from ..providers.base import BaseLLMProvider

class IntentType(str, Enum):
    FACTUAL = "factual"
    ANALYTICAL = "analytical"
    PROCEDURAL = "procedural"
    CREATIVE = "creative"
    AMBIGUOUS = "ambiguous"

class QueryIntent(BaseModel):
    """Structured output for intent routing."""
    intent: IntentType
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)

class RewrittenQuery(BaseModel):
    """Standalone, alternatives, and sub-queries for RAG."""
    standalone_query: str
    alternatives: List[str]
    sub_queries: List[str]
    is_complex: bool

class QueryRewriter:
    """
    Transforms user queries into RAG-friendly versions.
    Generates standalone queries, alternatives, and sub-queries.
    """
    
    REWRITE_PROMPT = """
    Given the following conversation history and user query:
    1. Resolve any pronouns to their entities.
    2. Generate a standalone query that can be understood in isolation.
    3. Provide 2 alternative phrasings of the standalone query.
    4. If the query is complex, break it down into smaller sub-queries.
    
    Return as a structured JSON object.
    """
    
    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm

    async def rewrite(self, query: str, history: Optional[str] = None) -> RewrittenQuery:
        """Call the LLM to rewrite the query."""
        prompt = f"{self.REWRITE_PROMPT}\nHistory: {history or 'None'}\nQuery: {query}"
        return await self.llm.generate_structured(prompt, RewrittenQuery)

class IntentRouter:
    """
    Classifies queries into specific intents to route to specialized agents or pipelines.
    """
    
    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm

    async def route(self, query: str) -> QueryIntent:
        """Analyze and classify the query intent."""
        prompt = f"Analyze the following query and determine its primary intent: {query}. " \
                 "Choose from: factual, analytical, procedural, creative, ambiguous."
        return await self.llm.generate_structured(prompt, QueryIntent)
