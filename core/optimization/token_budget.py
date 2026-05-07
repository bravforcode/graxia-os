from typing import List, Dict, Any, Optional
import re
from pydantic import BaseModel, Field

class TokenBudget(BaseModel):
    """Context window allocation for a 128k model."""
    system: int = 800
    history: int = 8000
    retrieved: int = 12000
    query: int = 500
    response: int = 4000
    safety: int = 2700
    total_window: int = 128000

class TokenBudgetManager:
    """Manages and validates token allocation across the context window."""
    def __init__(self, budget: Optional[TokenBudget] = None):
        self.budget = budget or TokenBudget()

    def get_available_context(self, current_usage: Dict[str, int]) -> int:
        """Calculates remaining tokens in the total window."""
        used = sum(current_usage.values())
        return max(0, self.budget.total_window - used)

    def validate_limits(self, usage: Dict[str, int]) -> Dict[str, bool]:
        """Checks if usage is within predefined budget segments."""
        return {
            k: usage.get(k, 0) <= getattr(self.budget, k)
            for k in ["system", "history", "retrieved", "query", "response", "safety"]
        }

class SelectiveContextCompressor:
    """Technique 1: Context-aware sentence extraction."""
    def compress(self, query: str, context: str, threshold: float = 0.3) -> str:
        """
        Extracts only sentences from the context that are relevant to the query.
        Simple implementation using keyword overlap; can be upgraded to semantic similarity.
        """
        query_words = set(re.findall(r'\w+', query.lower()))
        if not query_words:
            return context

        sentences = re.split(r'(?<=[.!?]) +', context)
        relevant_sentences = []

        for sentence in sentences:
            sentence_words = set(re.findall(r'\w+', sentence.lower()))
            overlap = len(query_words.intersection(sentence_words))
            
            # Keep if any keyword matches or if it's a short context
            if overlap > 0:
                relevant_sentences.append(sentence)

        return " ".join(relevant_sentences) if relevant_sentences else context[:1000]

class StructuredCompressor:
    """Technique 4: Transforms prose into compact structured formats."""
    def compress(self, prose: str) -> str:
        """
        Transforms prose into a key-value or bulleted format to save tokens.
        In production, this would be a prompt-based transformation.
        """
        # Placeholder for heuristic-based or LLM-based structured compression
        # For now, we simulate by stripping filler words and using bullet points
        lines = prose.split('\n')
        compressed = []
        for line in lines:
            if len(line.strip()) > 10:
                # Mock transformation: Just cleanup for now
                compressed.append(f"- {line.strip()}")
        return "\n".join(compressed)
