import asyncio
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import random

logger = logging.getLogger(__name__)

class ProviderConfig(BaseModel):
    name: str
    api_key: str
    base_url: Optional[str] = None
    max_retries: int = 3
    weight: int = 1

class ProviderError(Exception):
    """Base exception for provider errors."""
    pass

class ProviderRouter:
    """
    Enterprise-grade Provider Router with Load Balancing and Fallback capabilities.
    """
    def __init__(self, providers: List[ProviderConfig], strategy: str = "round_robin"):
        self.providers = providers
        self.strategy = strategy
        self._current_index = 0
        if not self.providers:
            raise ValueError("At least one provider must be configured.")

    def _get_next_provider(self) -> ProviderConfig:
        if self.strategy == "round_robin":
            provider = self.providers[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.providers)
            return provider
        elif self.strategy == "random":
            return random.choice(self.providers)
        elif self.strategy == "weighted":
            total_weight = sum(p.weight for p in self.providers)
            rand_val = random.uniform(0, total_weight)
            current = 0
            for p in self.providers:
                current += p.weight
                if rand_val <= current:
                    return p
            return self.providers[-1]
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    async def _call_provider(self, provider: ProviderConfig, prompt: str) -> str:
        # Mock async call to an LLM provider
        logger.debug(f"Calling provider: {provider.name}")
        await asyncio.sleep(0.1) # Simulate network latency
        
        # Simulate potential failure for fallback testing
        if random.random() < 0.1:
            raise ProviderError(f"Provider {provider.name} failed with 500 or RateLimit")
            
        return f"[{provider.name}] Response to: {prompt}"

    async def generate(self, prompt: str) -> str:
        """
        Attempt to generate a response, automatically falling back to other providers
        if the primary choice fails.
        """
        attempted_providers = set()
        
        for _ in range(len(self.providers)):
            provider = self._get_next_provider()
            if provider.name in attempted_providers:
                continue
                
            attempted_providers.add(provider.name)
            
            for attempt in range(provider.max_retries):
                try:
                    return await self._call_provider(provider, prompt)
                except ProviderError as e:
                    logger.warning(f"Attempt {attempt + 1}/{provider.max_retries} failed for {provider.name}: {e}")
                    await asyncio.sleep(2 ** attempt) # Exponential backoff
            
            logger.error(f"Provider {provider.name} exhausted all retries. Falling back to next provider.")
            
        raise ProviderError("All providers failed. Service unavailable.")
