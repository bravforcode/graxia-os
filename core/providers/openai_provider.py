import os
from typing import List, Dict, Any, Optional, Type, TypeVar
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel
from .base import BaseLLMProvider, BaseEmbeddingProvider

T = TypeVar("T", bound=BaseModel)

class OpenAIProvider(BaseLLMProvider):
    """OpenAI implementation of LLM provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided or set in environment variable OPENAI_API_KEY")
        self.client = instructor.patch(AsyncOpenAI(api_key=self.api_key))
        self.model = model

    async def generate_response(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate response using OpenAI's chat completion for a single prompt."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat_completion(messages, **kwargs)

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Chat completion using OpenAI's API."""
        response = await self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            **kwargs
        )
        # Handle cases where instructor might have different response format
        if hasattr(response, 'choices'):
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "model": response.model
            }
        else:
            # Handle if response is a pydantic model (unlikely if not calling generate_structured)
            return {"content": str(response)}

    async def generate_structured(self, prompt: str, schema: Type[T], **kwargs) -> T:
        """Generate structured data using instructor."""
        return await self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            response_model=schema,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )

class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI implementation of Embedding provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided or set in environment variable OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of strings using OpenAI API."""
        response = await self.client.embeddings.create(
            input=texts,
            model=self.model
        )
        return [data.embedding for data in response.data]

    async def get_single_embedding(self, text: str) -> List[float]:
        """Generate an embedding for a single string."""
        embeddings = await self.get_embeddings([text])
        return embeddings[0]
