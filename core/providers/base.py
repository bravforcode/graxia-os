from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class BaseLLMProvider(ABC):
    """Base class for LLM providers to ensure provider-agnostic interactions."""

    @abstractmethod
    async def generate_response(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a response from the LLM based on the given prompt."""
        pass

    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Chat completion for multi-turn conversations."""
        pass

    @abstractmethod
    async def generate_structured(self, prompt: str, schema: Type[T], **kwargs) -> T:
        """Generate structured data based on a Pydantic schema."""
        pass

class BaseEmbeddingProvider(ABC):
    """Base class for Embedding providers."""

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of strings."""
        pass

    @abstractmethod
    async def get_single_embedding(self, text: str) -> List[float]:
        """Generate an embedding for a single string."""
        pass
