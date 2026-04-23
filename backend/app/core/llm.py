"""
app/core/llm.py — LLM Client

Primary:  OpenClaw (Claude via OpenAI-compatible API)
Fallback: Google Gemini (free tier)

OpenClaw uses the OpenAI-compatible endpoint so we call it with httpx directly.
"""
import hashlib
import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.model_router import build_router_config, route_task
from app.core.redis_pool import get_redis
from app.core.redis_circuit_breaker import openclaw_circuit_breaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMClient:
    def __init__(self) -> None:
        # OpenClaw is primary — Claude via OpenAI-compatible API
        self.openclaw_key = settings.OPENCLAW_API_KEY if settings.HAS_REAL_OPENCLAW_KEY else ""
        self.openclaw_base_url = settings.OPENCLAW_BASE_URL
        self._openclaw_use_cli = (self.openclaw_key or "").strip().lower() == "local-gateway"
        # Gemini is fallback
        self.api_key = settings.GEMINI_API_KEY if settings.HAS_REAL_GEMINI_KEY else ""
        self.default_model = settings.OPENCLAW_DEFAULT_MODEL if self.openclaw_key else settings.DEFAULT_MODEL
        self.fast_model = settings.OPENCLAW_FAST_MODEL if self.openclaw_key else settings.FAST_MODEL
        self.daily_limit = settings.GEMINI_DAILY_REQUEST_LIMIT
        self.router_config = build_router_config(settings)
        self._redis = None
        self._degraded = False
        self._degraded_until = 0.0
        self._openclaw_disabled_until = 0.0

    def _using_openclaw(self) -> bool:
        return bool(self.openclaw_key) and time.time() >= self._openclaw_disabled_until

    async def _get_redis(self):
        """Get Redis client using connection pool with circuit breaker."""
        return await get_redis()

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
    async def _call_openclaw_protected(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> str:
        """Internal OpenClaw call with circuit breaker protection."""
        if self._openclaw_use_cli:
            try:
                return await self._call_openclaw_cli(system, user, model)
            except Exception as exc:
                if not self.openclaw_base_url:
                    raise
                logger.warning("OpenClaw CLI unavailable; falling back to HTTP gateway: %s", exc)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        last_error: str | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for url in self._openclaw_completion_urls():
                try:
                    for candidate_model in self._openclaw_model_candidates(model):
                        payload["model"] = candidate_model
                        resp = await client.post(url, json=payload, headers=self._openclaw_headers())
                        if resp.status_code == 404:
                            last_error = f"404 {url}"
                            break
                        if resp.status_code in {402, 429, 503}:
                            last_error = f"{resp.status_code} {url} model={candidate_model}"
                            continue
                        if resp.status_code == 400:
                            txt = (resp.text or "").lower()
                            if "insufficient" in txt or "quota" in txt or "rate limit" in txt:
                                last_error = f"400 quota {url} model={candidate_model}"
                                continue
                        resp.raise_for_status()
                        if "application/json" not in (resp.headers.get("content-type") or ""):
                            last_error = f"non_json_response {url} model={candidate_model}"
                            continue
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0]["message"]["content"].strip()
                        last_error = f"no_choices {url} model={candidate_model}"
                except Exception as exc:
                    last_error = str(exc)
                    continue
        if last_error and any(x in last_error for x in ["402", "429", "quota", "rate"]):
            self._openclaw_disabled_until = time.time() + 900
        else:
            self._openclaw_disabled_until = time.time() + 21600
        raise RuntimeError(f"OpenClaw gateway not compatible: {last_error}")

    async def _call_openclaw(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> str:
        """Call OpenClaw with circuit breaker protection."""
        try:
            return await openclaw_circuit_breaker.call(
                self._call_openclaw_protected,
                system, user, model, max_tokens, temperature
            )
        except CircuitBreakerOpen:
            logger.warning("OpenClaw circuit breaker is OPEN - using fallback")
            raise RuntimeError("OpenClaw unavailable (circuit breaker open)")

    async def _call_openclaw_cli(self, system: str, user: str, model: str) -> str:
        cmd = shutil.which("openclaw") or shutil.which("openclaw.cmd")
        if not cmd:
            home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
            candidate = home / ".openclaw" / "openclaw.cmd"
            if candidate.exists():
                cmd = str(candidate)
        if not cmd:
            raise RuntimeError("OpenClaw CLI not found on PATH or ~/.openclaw/openclaw.cmd")

        prompt = f"{system}\n\n{user}"
        base_args = [
            cmd,
            "infer",
            "model",
            "run",
            "--local",
            "--json",
            "--prompt",
            prompt,
        ]

        candidate_args = []
        if model:
            candidate_args.append(base_args + ["--model", model])
        candidate_args.append(base_args)

        last_error: str = ""
        for args in candidate_args:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                last_error = (stderr or stdout or b"").decode(errors="replace").strip()
                continue
            data = json.loads((stdout or b"{}").decode(errors="replace"))
            if not data.get("ok"):
                last_error = json.dumps(data, ensure_ascii=False)
                continue
            outputs = data.get("outputs") or []
            if not outputs:
                last_error = json.dumps(data, ensure_ascii=False)
                continue
            text = (outputs[0].get("text") or "").strip()
            if not text:
                last_error = json.dumps(data, ensure_ascii=False)
                continue
            return text

        raise RuntimeError(f"OpenClaw CLI inference failed: {last_error}")

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
            if resp.status_code == 429:
                self._degraded = True
                self._degraded_until = time.time() + 43200
                raise RuntimeError("Gemini quota exceeded")
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

    def _openclaw_completion_urls(self) -> list[str]:
        base = (self.openclaw_base_url or "").rstrip("/")
        if base.endswith("/v1") or base.endswith("/api/v1"):
            return [f"{base}/chat/completions"]
        return [
            f"{base}/v1/chat/completions",
            f"{base}/chat/completions",
        ]

    def _openclaw_model_candidates(self, model: str) -> list[str]:
        model_candidates: list[str] = []
        for m in [model, settings.OPENCLAW_FAST_MODEL, "openrouter/free"]:
            if m and m not in model_candidates:
                model_candidates.append(m)
        for m in (settings.OPENCLAW_FALLBACK_MODELS or "").split(","):
            m2 = m.strip()
            if m2 and m2 not in model_candidates:
                model_candidates.append(m2)
        return model_candidates

    def _openclaw_headers(self) -> dict[str, str]:
        base = (self.openclaw_base_url or "").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.openclaw_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in base:
            site = (settings.TRACKING_BASE_URL or settings.APP_BASE_URL or "").strip()
            if site:
                headers["HTTP-Referer"] = site
            headers["X-Title"] = "PersonalOS"
        return headers

    @staticmethod
    def _extract_openai_stream_text(payload: dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        message = choice.get("message") or {}
        return str(delta.get("content") or message.get("content") or "")

    @staticmethod
    def _extract_gemini_stream_text(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        content = (candidates[0] or {}).get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            return ""
        return str((parts[0] or {}).get("text") or "")

    async def _iter_sse_json(self, response: httpx.Response) -> AsyncIterator[dict]:
        async for line in response.aiter_lines():
            stripped = line.strip()
            if not stripped or stripped.startswith(":"):
                continue
            if not stripped.startswith("data:"):
                continue
            data = stripped.removeprefix("data:").strip()
            if data == "[DONE]":
                return
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                logger.debug("Ignoring malformed streaming payload: %s", data[:200])

    async def _call_openclaw_stream(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        last_error: str | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for url in self._openclaw_completion_urls():
                for candidate_model in self._openclaw_model_candidates(model):
                    payload["model"] = candidate_model
                    chunk_seen = False
                    try:
                        async with client.stream(
                            "POST",
                            url,
                            json=payload,
                            headers=self._openclaw_headers(),
                        ) as response:
                            if response.status_code == 404:
                                last_error = f"404 {url}"
                                break
                            if response.status_code in {402, 429, 503}:
                                last_error = f"{response.status_code} {url} model={candidate_model}"
                                continue
                            response.raise_for_status()
                            async for event in self._iter_sse_json(response):
                                text = self._extract_openai_stream_text(event)
                                if text:
                                    chunk_seen = True
                                    yield text
                            if chunk_seen:
                                return
                            last_error = f"empty_stream {url} model={candidate_model}"
                    except Exception as exc:
                        last_error = str(exc)
                        continue

        if last_error and any(x in last_error for x in ["402", "429", "quota", "rate"]):
            self._openclaw_disabled_until = time.time() + 900
        else:
            self._openclaw_disabled_until = time.time() + 21600
        raise RuntimeError(f"OpenClaw streaming unavailable: {last_error}")

    async def _call_gemini_stream(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        url = f"{GEMINI_API_BASE}/{model}:streamGenerateContent?alt=sse&key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }

        chunk_seen = False
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 429:
                    self._degraded = True
                    self._degraded_until = time.time() + 43200
                    raise RuntimeError("Gemini quota exceeded")
                response.raise_for_status()
                async for event in self._iter_sse_json(response):
                    text = self._extract_gemini_stream_text(event)
                    if text:
                        chunk_seen = True
                        yield text
        if not chunk_seen:
            raise RuntimeError("Gemini returned an empty stream")

    async def generate_stream(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = True,
        task_class: str = "analysis",
        complexity: int | None = None,
        budget_tag: str | None = None,
    ) -> AsyncIterator[str]:
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
                "LLM stream route for task=%s exceeded single-call budget (estimated=%s)",
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
            return
        if not self.openclaw_key and not self.api_key:
            logger.info("No LLM API key available for stream — staying in degraded mode")
            self._set_degraded()
            return
        if not await self._track_request():
            logger.warning("Daily request limit reached")
            from app.core.event_bus import event_bus

            await event_bus.emit(
                "ai.cost_limit_reached",
                {
                    "scope": "daily",
                    "amount_usd": 0.0,
                    "limit_usd": 0.0,
                    "reason": "daily_request_limit",
                },
            )
            return

        cache_key = self._cache_key(system, user, model)
        cached = await self._get_cache(cache_key)
        if cached:
            yield cached
            return

        if self.is_degraded() and not (allow_fallback and bool(self.api_key)):
            logger.warning("LLM in degraded mode — skipping stream")
            return

        chunks: list[str] = []

        async def emit_from(stream: AsyncIterator[str], used_model: str, was_fallback: bool) -> AsyncIterator[str]:
            async for chunk in stream:
                if not chunk:
                    continue
                chunks.append(chunk)
                yield chunk
            if chunks:
                result = "".join(chunks)
                await self._set_cache(cache_key, result)
                await self._log_call(
                    used_model,
                    user,
                    result,
                    was_fallback=was_fallback,
                    task_class=task_class,
                    budget_tag=budget_tag or routing.budget_tag,
                    estimated_max_cost_usd=routing.estimated_max_cost_usd,
                )

        if self._using_openclaw():
            try:
                async for chunk in emit_from(
                    self._call_openclaw_stream(system, user, model, max_tokens, temperature),
                    model,
                    False,
                ):
                    yield chunk
                if chunks:
                    return
            except Exception as exc:
                logger.warning("OpenClaw stream failed: %s", exc)

        if allow_fallback and self.api_key:
            fallback_model = (
                settings.CHEAP_MODEL
                if str(settings.CHEAP_MODEL or "").startswith("gemini")
                else "gemini-2.0-flash"
            )
            try:
                chunks.clear()
                async for chunk in emit_from(
                    self._call_gemini_stream(
                        system,
                        user,
                        fallback_model,
                        max_tokens=min(max_tokens, settings.MID_MODEL_MAX_TOKENS),
                        temperature=temperature,
                    ),
                    fallback_model,
                    True,
                ):
                    yield chunk
                if chunks:
                    return
            except Exception as exc:
                logger.warning("Gemini stream failed: %s", exc)

        result = await self.complete(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            allow_fallback=allow_fallback,
            task_class=task_class,
            complexity=complexity,
            budget_tag=budget_tag,
        )
        if result:
            yield result

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = True,
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
        if self.is_degraded() and not (allow_fallback and bool(self.api_key)):
            logger.warning("LLM in degraded mode — skipping call")
            return None
        try:
            if self._using_openclaw():
                try:
                    result = await self._call_openclaw(system, user, model, max_tokens, temperature)
                except Exception as exc:
                    if allow_fallback and self.api_key:
                        fallback_model = (
                            settings.CHEAP_MODEL
                            if str(settings.CHEAP_MODEL or "").startswith("gemini")
                            else "gemini-2.0-flash"
                        )
                        logger.warning("OpenClaw call failed; falling back to Gemini: %s", exc)
                        result = await self._call_gemini(
                            system,
                            user,
                            fallback_model,
                            max_tokens=min(max_tokens, settings.MID_MODEL_MAX_TOKENS),
                            temperature=temperature,
                        )
                        await self._set_cache(cache_key, result)
                        await self._log_call(
                            fallback_model,
                            user,
                            result,
                            was_fallback=True,
                            task_class=task_class,
                            budget_tag=budget_tag or routing.budget_tag,
                            estimated_max_cost_usd=routing.estimated_max_cost_usd,
                        )
                        return result
                    raise
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
            logger.error("LLM call failed: %s", e)
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
        rag_context: bool = False,
        rag_query: str | None = None,
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
            allow_fallback=True,
            rag_context=rag_context,
            rag_query=rag_query,
        )
        if result is None:
            return {}
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
