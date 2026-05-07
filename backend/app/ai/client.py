"""
AI Client - Multi-model orchestration client
Handles communication with OpenRouter, Gemini, OpenAI, Anthropic
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .models import ChatMessage, MessageRole


class AIClient:
    """Multi-provider AI client with smart routing"""

    # Ollama Pay Models (Primary - ThaiGQ Soft)
    OLLAMA_PAY_MODELS = {
        "kimi-k2.5:cloud": "kimi-k2.5:cloud",  # Default - General chat
        "deepseek-v4-pro:cloud": "deepseek-v4-pro:cloud",  # Code/Complex tasks
        "deepseek-v4-flash:cloud": "deepseek-v4-flash:cloud",  # Fast Q&A
        "qwen3.5:397b-cloud": "qwen3.5:397b-cloud",  # Heavy context
        "qwen3-coder-next:cloud": "qwen3-coder-next:cloud",  # Code generation
    }

    # OpenRouter free models (Fallback)
    OPENROUTER_MODELS = [
        "deepseek/deepseek-chat:free",
        "deepseek/deepseek-coder:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "qwen/qwen-2.5-coder:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-2.0-flash-thinking-exp:free",
    ]

    def __init__(self):
        # Primary: Ollama Pay (ThaiGQ Soft)
        self.ollama_pay_key = os.getenv("OLLAMA_PAY_API_KEY")
        self.ollama_pay_base = os.getenv(
            "OLLAMA_PAY_BASE_URL", "https://ollama-pay.thaigqsoft.com/api/v1"
        )

        # Fallback providers
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        self.http_client = httpx.AsyncClient(timeout=60.0)

        # Model routing rules - Ollama Pay as primary
        self.routing = {
            "code_generation": ["qwen3-coder-next:cloud", "deepseek-v4-pro:cloud"],
            "chat": ["kimi-k2.5:cloud", "deepseek-v4-flash:cloud"],
            "analysis": ["kimi-k2.5:cloud"],
            "reasoning": ["deepseek-v4-pro:cloud", "qwen3.5:397b-cloud"],
            "fast": ["deepseek-v4-flash:cloud"],
            "default": ["kimi-k2.5:cloud"],
        }

    def _get_model_for_task(self, task_type: str = "default") -> str:
        """Get appropriate model for task type"""
        return self.routing.get(task_type, self.routing["default"])[0]

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        task_type: str = "chat",
    ) -> dict[str, Any]:
        """Send chat request to AI"""

        # Determine model
        if model == "auto" or model is None:
            model = self._get_model_for_task(task_type)

        # Try providers in order - Ollama Pay as primary
        providers = [
            ("ollama_pay", self._ollama_pay_chat),
            ("openrouter", self._openrouter_chat),
            ("gemini", self._gemini_chat),
            ("openai", self._openai_chat),
            ("anthropic", self._anthropic_chat),
        ]

        last_error = None
        for provider_name, provider_func in providers:
            try:
                result = await provider_func(
                    messages=messages,
                    model=model if provider_name == "openrouter" else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                )
                result["provider"] = provider_name
                result["model_used"] = result.get("model", model)
                return result
            except Exception as e:
                last_error = e
                continue

        raise Exception(f"All providers failed. Last error: {last_error}")

    async def _openrouter_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Send request to OpenRouter"""

        if not self.openrouter_key:
            raise ValueError("OpenRouter API key not configured")

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://graxia.os",
            "X-Title": "Graxia OS",
        }

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = await self.http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", model),
            "tokens_used": data.get("usage", {}).get("total_tokens"),
        }

    async def _gemini_chat(
        self,
        messages: list[ChatMessage],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Send request to Gemini"""

        if not self.gemini_key:
            raise ValueError("Gemini API key not configured")

        # Convert to Gemini format
        gemini_model = model or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

        # Convert messages to Gemini format
        contents = []
        for m in messages:
            contents.append(
                {
                    "role": "user" if m.role == MessageRole.USER else "model",
                    "parts": [{"text": m.content}],
                }
            )

        payload = {"contents": contents, "generationConfig": {"temperature": temperature}}

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        params = {"key": self.gemini_key}
        response = await self.http_client.post(url, params=params, json=payload)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["candidates"][0]["content"]["parts"][0]["text"],
            "model": gemini_model,
            "tokens_used": data.get("usageMetadata", {}).get("totalTokenCount"),
        }

    async def _openai_chat(
        self,
        messages: list[ChatMessage],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Send request to OpenAI"""

        if not self.openai_key:
            raise ValueError("OpenAI API key not configured")

        url = "https://api.openai.com/v1/chat/completions"

        headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}

        openai_model = model or "gpt-4o-mini"

        payload = {
            "model": openai_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = await self.http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", openai_model),
            "tokens_used": data.get("usage", {}).get("total_tokens"),
        }

    async def _anthropic_chat(
        self,
        messages: list[ChatMessage],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Send request to Anthropic"""

        if not self.anthropic_key:
            raise ValueError("Anthropic API key not configured")

        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "x-api-key": self.anthropic_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Convert messages to Anthropic format
        system_msg = None
        anthropic_messages = []

        for m in messages:
            if m.role == MessageRole.SYSTEM:
                system_msg = m.content
            else:
                anthropic_messages.append(
                    {
                        "role": "user" if m.role == MessageRole.USER else "assistant",
                        "content": m.content,
                    }
                )

        anthropic_model = model or "claude-3-5-sonnet-20241022"

        payload = {
            "model": anthropic_model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_msg:
            payload["system"] = system_msg

        response = await self.http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["content"][0]["text"],
            "model": data.get("model", anthropic_model),
            "tokens_used": data.get("usage", {}).get("input_tokens", 0)
            + data.get("usage", {}).get("output_tokens", 0),
        }

    async def _ollama_pay_chat(
        self,
        messages: list[ChatMessage],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Send request to Ollama Pay (ThaiGQ Soft)"""

        if not self.ollama_pay_key:
            raise ValueError("Ollama Pay API key not configured")

        url = f"{self.ollama_pay_base}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.ollama_pay_key}",
            "Content-Type": "application/json",
        }

        # Use provided model or default
        ollama_model = model or "kimi-k2.5:cloud"

        payload = {
            "model": ollama_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = await self.http_client.post(url, headers=headers, json=payload, timeout=120.0)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", ollama_model),
            "tokens_used": data.get("usage", {}).get("total_tokens"),
        }

    async def generate_code(
        self,
        prompt: str,
        language: str,
        context: str | None = None,
        existing_code: str | None = None,
    ) -> dict[str, Any]:
        """Generate code with appropriate model"""

        system_prompt = f"""You are an expert {language} developer.
Write clean, well-documented, production-ready code.
Include error handling and follow best practices."""

        user_prompt = prompt

        if existing_code:
            user_prompt = f"""Existing code:
```{language}
{existing_code}
```

{user_prompt}"""

        if context:
            user_prompt = f"Context: {context}\n\n{user_prompt}"

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        result = await self.chat(messages=messages, task_type="code_generation", temperature=0.3)

        return {"code": result["content"], "model_used": result["model_used"], "language": language}

    async def stream_chat(
        self, messages: list[ChatMessage], model: str | None = None, temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """Stream chat response"""

        # For now, just yield the full response
        # Can be enhanced with actual streaming
        result = await self.chat(messages, model, temperature, stream=False)
        yield result["content"]

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Singleton instance
_ai_client: AIClient | None = None


async def get_ai_client() -> AIClient:
    """Get or create AI client"""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
