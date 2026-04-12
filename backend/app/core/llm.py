"""
app/core/llm.py — LLM Client

Primary:  OpenClaw (Claude via OpenAI-compatible API)
Fallback: Google Gemini (free tier)

OpenClaw uses the OpenAI-compatible endpoint so we call it with httpx directly.
"""
import hashlib
import json
import logging
import time
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.model_router import build_router_config, route_task

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMClient:
    def __init__(self) -> None:
        # OpenClaw is primary — Claude via OpenAI-compatible API
        self.openclaw_key = settings.OPENCLAW_API_KEY if settings.HAS_REAL_OPENCLAW_KEY else ""
        self.openclaw_base_url = settings.OPENCLAW_BASE_URL
        # Gemini is fallback
        self.api_key = settings.GEMINI_API_KEY if settings.HAS_REAL_GEMINI_KEY else ""
        self.default_model = settings.OPENCLAW_DEFAULT_MODEL if self.openclaw_key else settings.DEFAULT_MODEL
        self.fast_model = settings.OPENCLAW_FAST_MODEL if self.openclaw_key else settings.FAST_MODEL
        self.daily_limit = settings.GEMINI_DAILY_REQUEST_LIMIT
        self.router_config = build_router_config(settings)
        self._redis = None
        self._degraded = False
        self._degraded_until = 0.0

    def _using_openclaw(self) -> bool:
        return bool(self.openclaw_key)

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def _cache_key(self, system: str, user: str, model: str) -> str:
        raw = f"{model}|{system}|{user}"
        return "llm_cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cache(self, key: str) -> Optional[str]:
        r = await self._get_redis()
        if r:
            try:
                return await r.get(key)
            except Exception:
                return None
        return None

    async def _set_cache(self, key: str, value: str) -> None:
        r = await self._get_redis()
        if r:
            try:
                await r.setex(key, 86400, value)
            except Exception:
                pass

    async def _track_request(self) -> bool:
        r = await self._get_redis()
        if not r:
            return True
        today_key = f"gemini_requests:{time.strftime('%Y-%m-%d')}"
        try:
            count = await r.incr(today_key)
            if count == 1:
                await r.expire(today_key, 86400)
            return count <= self.daily_limit
        except Exception:
            return True

    def is_degraded(self) -> bool:
        if self._degraded and time.time() > self._degraded_until:
            self._degraded = False
        return self._degraded

    def _set_degraded(self) -> None:
        self._degraded = True
        self._degraded_until = time.time() + 1800

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _call_openclaw(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> str:
        """Call OpenClaw (OpenAI-compatible endpoint)."""
        url = f"{self.openclaw_base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.openclaw_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"OpenClaw returned no choices: {data}")
        return choices[0]["message"]["content"].strip()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _call_gemini(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> str:
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        
        # Estimate input tokens (rough: 1 token ≈ 0.75 words)
        input_tokens = int(len((system + user).split()) * 1.3)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates: {data}")
        
        result_text = candidates[0]["content"]["parts"][0]["text"].strip()
        
        # Estimate output tokens
        output_tokens = int(len(result_text.split()) * 1.3)
        
        # Calculate cost (Gemini pricing: $0.00025/1K input, $0.0005/1K output)
        input_cost = (input_tokens / 1000) * 0.00025
        output_cost = (output_tokens / 1000) * 0.0005
        total_cost = input_cost + output_cost
        
        # Track cost
        try:
            from app.core.cost_tracker import cost_tracker
            await cost_tracker.track_gemini_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=total_cost,
                prompt_preview=user[:100]
            )
        except Exception as e:
            logger.warning(f"Failed to track Gemini cost: {e}")
        
        return result_text

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = False,
        task_class: str = "analysis",
        complexity: int | None = None,
        budget_tag: str | None = None,
    ) -> Optional[str]:
        routing = route_task(
            task_class=task_class,
            requested_max_tokens=max_tokens,
            complexity=complexity,
            router=self.router_config,
        )
        if model is None:
            model = routing.model
            max_tokens = routing.max_tokens
        if routing.budget_exceeded:
            logger.warning(
                "LLM route for task=%s exceeded single-call budget (estimated=%s)",
                task_class,
                routing.estimated_max_cost_usd,
            )
            from app.core.event_bus import event_bus

            await event_bus.emit(
                "ai.cost_limit_reached",
                {
                    "scope": "single_call",
                    "amount_usd": routing.estimated_max_cost_usd,
                    "limit_usd": self.router_config.max_single_call_cost_usd,
                    "reason": "single_call_budget_limit",
                    "task_class": task_class,
                },
            )
            return None
        if not self.openclaw_key and not self.api_key:
            logger.info("No LLM API key available — staying in degraded mode")
            self._set_degraded()
            return None
        if not await self._track_request():
            logger.warning("Daily request limit reached")
            from app.core.event_bus import event_bus
            await event_bus.emit("ai.cost_limit_reached", {"scope": "daily", "amount_usd": 0.0, "limit_usd": 0.0, "reason": "daily_request_limit"})
            return None
        cache_key = self._cache_key(system, user, model)
        cached = await self._get_cache(cache_key)
        if cached:
            return cached
        if self.is_degraded():
            logger.warning("LLM in degraded mode — skipping call")
            return None
        try:
            # Try OpenClaw first, fall back to Gemini
            if self._using_openclaw():
                result = await self._call_openclaw(system, user, model, max_tokens, temperature)
            else:
                result = await self._call_gemini(system, user, model, max_tokens, temperature)
            await self._set_cache(cache_key, result)
            await self._log_call(
                model,
                user,
                result,
                was_fallback=False,
                task_class=task_class,
                budget_tag=budget_tag or routing.budget_tag,
                estimated_max_cost_usd=routing.estimated_max_cost_usd,
            )
            return result
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            self._set_degraded()
            try:
                from app.telegram_bot.bot import send_message
                await send_message("⚠️ AI ไม่พร้อม — ทำงานด้วย heuristic ชั่วคราว (30 นาที)")
            except Exception:
                pass
            await self._log_call(
                model,
                user,
                "",
                was_fallback=True,
                error=str(e),
                task_class=task_class,
                budget_tag=budget_tag or routing.budget_tag,
                estimated_max_cost_usd=routing.estimated_max_cost_usd,
            )
            return None

    async def complete_json(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 800,
        task_class: str = "classification",
        complexity: int | None = None,
    ) -> dict:
        json_system = system + "\n\nCRITICAL: Return ONLY valid JSON. No markdown, no backticks, no explanation."
        result = await self.complete(
            system=json_system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            temperature=0.1,
            task_class=task_class,
            complexity=complexity,
        )
        if result is None:
            raise ValueError("LLM returned None")
        cleaned = result.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini returned invalid JSON: {e}\nRaw: {cleaned[:200]}")

    async def _log_call(
        self,
        model: str,
        user: str,
        result: str,
        was_fallback: bool = False,
        error: Optional[str] = None,
        task_class: str | None = None,
        budget_tag: str | None = None,
        estimated_max_cost_usd: float | None = None,
    ) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog
            async with AsyncSessionLocal() as db:
                log = AuditLog(
                    action="llm.call",
                    details={
                        "model": model,
                        "task_class": task_class,
                        "budget_tag": budget_tag,
                        "estimated_max_cost_usd": estimated_max_cost_usd,
                        "prompt_preview": user[:100],
                        "response_preview": result[:100] if result else "",
                        "error": error,
                    },
                    ai_model_used=model,
                    was_fallback=was_fallback,
                    success=not was_fallback,
                    error_message=error,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to log LLM call: {e}")

    def get_cost_today_usd(self) -> float:
        return 0.0

    def get_cost_month_usd(self) -> float:
        return 0.0

    async def get_call_count_today(self) -> int:
        r = await self._get_redis()
        if not r:
            return 0
        try:
            val = await r.get(f"gemini_requests:{time.strftime('%Y-%m-%d')}")
            return int(val) if val else 0
        except Exception:
            return 0

    def is_cost_paused(self) -> bool:
        return False

    def get_router_summary(self) -> dict[str, float | bool]:
        return {
            "routing_enabled": self.router_config.routing_enabled,
            "max_single_call_cost_usd": self.router_config.max_single_call_cost_usd,
        }


llm_client = LLMClient()
