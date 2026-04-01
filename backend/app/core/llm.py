"""
app/core/llm.py — LLM Client (Google Gemini)

Models:
  DEFAULT_MODEL = gemini-2.0-flash        (drafts, strategy, analysis)
  FAST_MODEL    = gemini-2.0-flash-lite   (scoring, classification)

Free tier: 1,500 req/day per model. Cost = $0.
"""
import hashlib
import json
import logging
import time
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMClient:
    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.default_model = settings.DEFAULT_MODEL
        self.fast_model = settings.FAST_MODEL
        self.daily_limit = settings.GEMINI_DAILY_REQUEST_LIMIT
        self._redis = None
        self._degraded = False
        self._degraded_until = 0.0

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
    async def _call_gemini(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> str:
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates: {data}")
        return candidates[0]["content"]["parts"][0]["text"].strip()

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = False,
    ) -> Optional[str]:
        if model is None:
            model = self.default_model
        if not await self._track_request():
            logger.warning("Gemini daily request limit reached")
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
            result = await self._call_gemini(system, user, model, max_tokens, temperature)
            await self._set_cache(cache_key, result)
            await self._log_call(model, user, result, was_fallback=False)
            return result
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            self._set_degraded()
            try:
                from app.telegram_bot.bot import send_message
                await send_message("⚠️ AI ไม่พร้อม — ทำงานด้วย heuristic ชั่วคราว (30 นาที)")
            except Exception:
                pass
            await self._log_call(model, user, "", was_fallback=True, error=str(e))
            return None

    async def complete_json(self, system: str, user: str, model: Optional[str] = None, max_tokens: int = 800) -> dict:
        if model is None:
            model = self.fast_model
        json_system = system + "\n\nCRITICAL: Return ONLY valid JSON. No markdown, no backticks, no explanation."
        result = await self.complete(system=json_system, user=user, model=model, max_tokens=max_tokens, temperature=0.1)
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

    async def _log_call(self, model: str, user: str, result: str, was_fallback: bool = False, error: Optional[str] = None) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog
            async with AsyncSessionLocal() as db:
                log = AuditLog(
                    action="llm.call",
                    details={"model": model, "prompt_preview": user[:100], "response_preview": result[:100] if result else "", "error": error},
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


llm_client = LLMClient()
