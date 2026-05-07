import os
import json
import httpx
import logging
import asyncio
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    raw_response: Dict[str, Any]
    cached: bool = False

class TokenBudgetGate:
    def __init__(self, max_tokens: int = 1000000):
        self.max_tokens = max_tokens
        self.used_tokens = 0
        self.lock = asyncio.Lock()
        
    async def check_and_add(self, estimated_tokens: int) -> bool:
        async with self.lock:
            if self.used_tokens + estimated_tokens > self.max_tokens:
                logger.error(f"Token budget exceeded! Used: {self.used_tokens}, Requested: {estimated_tokens}, Max: {self.max_tokens}")
                return False
            self.used_tokens += estimated_tokens
            return True
            
    async def refund(self, tokens: int):
        async with self.lock:
            self.used_tokens = max(0, self.used_tokens - tokens)

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 120):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker tripped! State: {self.state}")
            
    def record_success(self):
        if self.state != "CLOSED":
            logger.info("Circuit breaker reset to CLOSED.")
        self.failures = 0
        self.state = "CLOSED"
        
    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker transitioning to HALF_OPEN to test connection.")
                return True
            return False
        return True # HALF_OPEN

import sqlite3
from datetime import datetime, timedelta

class SemanticCacheLayer:
    """
    Enterprise SQLite-based cache layer.
    Supports TTL, concurrency, and structured retrieval.
    """
    def __init__(self, cache_db: str = ".cache/llm_cache.db", ttl_days: int = 30):
        self.cache_db = Path(cache_db)
        self.ttl_days = ttl_days
        self._init_db()
        
    def _get_connection(self):
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.cache_db)
        
    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key TEXT PRIMARY KEY,
                    prompt_hash TEXT,
                    response_json TEXT,
                    model TEXT,
                    created_at TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON llm_cache(expires_at)")

    def _generate_key(self, messages: List[Dict[str, Any]], model: str, tools: Optional[List[Dict[str, Any]]] = None) -> str:
        cache_data = {
            "messages": messages,
            "model": model,
            "tools": tools or []
        }
        return hashlib.sha256(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        
    def get(self, messages: List[Dict[str, Any]], model: str, tools: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        key = self._generate_key(messages, model, tools)
        now = datetime.now()
        
        with self._get_connection() as conn:
            # Automatic cleanup of expired entries
            conn.execute("DELETE FROM llm_cache WHERE expires_at < ?", (now,))
            
            cursor = conn.execute(
                "SELECT response_json FROM llm_cache WHERE key = ? AND expires_at > ?", 
                (key, now)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None
        
    def set(self, messages: List[Dict[str, Any]], model: str, response: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None):
        key = self._generate_key(messages, model, tools)
        now = datetime.now()
        expires = now + timedelta(days=self.ttl_days)
        
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, response_json, model, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (key, json.dumps(response), model, now, expires)
            )

from core.monitoring import TOKEN_USAGE, LLM_LATENCY, CACHE_HITS

import re

class SecretScrubber:
    """
    Middleware to detect and mask PII and Secrets before they leave the system.
    """
    PATTERNS = {
        "stripe_key": r"sk_(?:live|test)_[a-zA-Z0-9]+",
        "bank_account": r"\b\d{10,12}\b", # Common bank account format
        "generic_secret": r"(?:api_key|secret|password|token)[\s:=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?"
    }

    @classmethod
    def scrub(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        scrubbed = text
        for name, pattern in cls.PATTERNS.items():
            scrubbed = re.sub(pattern, f"[MASKED_{name.upper()}]", scrubbed)
        return scrubbed

class LLMClient:
    """
    Gateway-First LLM Client for Graxia OS with Enterprise Patterns.
    Routes all requests through Hermes Gateway with mandatory Secret Scrubbing.
    """
    def __init__(self):
        # Default to Hermes Gateway
        self.gateway_url = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8644/v1")
        self.gateway_token = os.getenv("HERMES_GATEWAY_TOKEN", "18637e1fa296ada0b358ce7f8f9e5cab1900c6d07c6fe41e")
        
        # Fallbacks (Internal use or when Gateway specifies)
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.default_model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        
        # Enterprise Patterns
        self.budget_gate = TokenBudgetGate(max_tokens=int(os.getenv("MAX_BUDGET_TOKENS", "1000000")))
        self.gateway_circuit_breaker = CircuitBreaker(failure_threshold=3, reset_timeout=120)
        self.cache_layer = SemanticCacheLayer()

    def _estimate_complexity(self, messages: List[Dict[str, Any]]) -> int:
        """Heuristic to evaluate prompt complexity (0-10)"""
        text = " ".join([m.get("content", "") for m in messages if isinstance(m.get("content"), str)])
        length = len(text)
        keywords = ["analyze", "architect", "synthesize", "evaluate", "compare", "complex", "system", "framework", "refactor", "optimize"]
        keyword_count = sum(1 for k in keywords if k in text.lower())
        
        score = min(10, (length // 1000) + (keyword_count * 2))
        return score
        
    def _route_model(self, complexity: int, requested_model: Optional[str] = None) -> str:
        """Tiered model routing based on complexity (Updated for 2026 models)"""
        if requested_model:
            return requested_model
        if complexity < 4:
            return "gemini-2.0-flash-lite"
        elif complexity < 8:
            return "gemini-2.0-flash"
        else:
            return "gemini-2.5-pro"

    async def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """
        Primary entry point. Integrates Budgeting, Caching, Tiered Routing, and Circuit Breaking.
        Includes Secret Scrubbing for security.
        """
        # 0. Secret Scrubbing (Priority: Security)
        for msg in messages:
            if "content" in msg and isinstance(msg["content"], str):
                msg["content"] = SecretScrubber.scrub(msg["content"])
        
        agent_name = kwargs.pop("agent_name", "unknown")
        # Extract model from kwargs if present to avoid multiple values error
        requested_model = kwargs.pop("model", None)
        
        complexity = self._estimate_complexity(messages)
        model_to_use = self._route_model(complexity, requested_model)
        logger.info(f"Routed to {model_to_use} based on complexity score: {complexity}")

        # Check Cache
        cached_resp = self.cache_layer.get(messages, model_to_use, tools)
        if cached_resp:
            logger.info("Semantic cache hit!")
            CACHE_HITS.labels(status="hit").inc()
            return LLMResponse(**cached_resp)
        
        CACHE_HITS.labels(status="miss").inc()

        # Estimate tokens (naive: 1 char ~= 0.25 tokens)
        text_length = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))
        estimated_tokens = int(text_length * 0.25) + 500 # Add buffer for output
        
        if not await self.budget_gate.check_and_add(estimated_tokens):
            raise RuntimeError("Token budget exceeded limit. Request denied by TokenBudgetGate.")

        try:
            start_time = time.time()
            # 1. Primary: Hermes Gateway
            if self.gateway_circuit_breaker.can_execute():
                try:
                    response = await self._call_api(self.gateway_url, self.gateway_token, messages, tools, model=model_to_use, **kwargs)
                    self.gateway_circuit_breaker.record_success()
                    
                    latency = time.time() - start_time
                    LLM_LATENCY.labels(model=model_to_use, provider="hermes").observe(latency)
                    TOKEN_USAGE.labels(agent_name=agent_name, model=model_to_use, type="prompt").inc(estimated_tokens - 500)
                    
                    # Cache the result
                    resp_dict = response.model_dump()
                    resp_dict["cached"] = True
                    self.cache_layer.set(messages, model_to_use, resp_dict, tools)
                    return response
                except Exception as e:
                    logger.error(f"Hermes Gateway Error: {e}")
                    self.gateway_circuit_breaker.record_failure()
            else:
                logger.warning("Gateway circuit is OPEN. Skipping primary gateway.")
                
            # 2. Safety Fallback: Local Ollama
            logger.warning("Falling back to local Ollama...")
            try:
                start_time = time.time()
                # Use a specific local model for fallback
                fallback_model = "llama3.1"
                response = await self._call_api(self.ollama_url, "ollama", messages, tools, model=fallback_model, **kwargs)
                
                latency = time.time() - start_time
                LLM_LATENCY.labels(model=fallback_model, provider="ollama").observe(latency)
                TOKEN_USAGE.labels(agent_name=agent_name, model=fallback_model, type="prompt").inc(estimated_tokens - 500)

                # Cache the result
                resp_dict = response.model_dump()
                resp_dict["cached"] = True
                self.cache_layer.set(messages, fallback_model, resp_dict, tools)
                return response
            except Exception as fallback_e:
                gateway_err = locals().get('e', 'Circuit OPEN or skipped')
                raise RuntimeError(f"Both Gateway and Fallback failed. Gateway: {gateway_err}, Fallback: {fallback_e}")
                
        except Exception as final_e:
            await self.budget_gate.refund(estimated_tokens) # Refund on total failure
            raise final_e

    async def _call_api(self, url: str, token: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, model: Optional[str] = None, **kwargs) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model or kwargs.get("model") or self.default_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7)
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Accommodate potential differences in response format between Gateway and Ollama
            if "choices" in data and len(data["choices"]) > 0:
                message = data["choices"][0].get("message", {})
                return LLMResponse(
                    content=message.get("content"),
                    tool_calls=message.get("tool_calls", []),
                    raw_response=data
                )
            elif "message" in data:
                # Ollama chat API standard format
                message = data["message"]
                return LLMResponse(
                    content=message.get("content"),
                    tool_calls=message.get("tool_calls", []),
                    raw_response=data
                )
            else:
                return LLMResponse(
                    content=str(data),
                    tool_calls=[],
                    raw_response=data
                )

    async def generate_completion(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        resp = await self.chat(messages, **kwargs)
        return resp.content or ""

llm_client = LLMClient()
