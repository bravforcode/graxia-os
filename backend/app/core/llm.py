"""
app/core/llm.py — LLM Client

Primary:  OpenClaw (Claude via OpenAI-compatible API)
Fallback: Google Gemini (free tier)

OpenClaw uses the OpenAI-compatible endpoint so we call it with httpx directly.
"""
import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import os
import secrets
import shutil
import socket
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.model_router import build_router_config, route_task
from app.core.redis_circuit_breaker import CircuitBreakerOpen, openclaw_circuit_breaker
from app.core.redis_pool import get_redis

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_API_BASE = "https://api.openai.com/v1"


class LLMClient:
    def __init__(self, app_settings=settings) -> None:
        self.settings = app_settings
        self.provider = (getattr(app_settings, "LLM_PROVIDER", "") or "").strip().lower()
        # A configured key does not select or verify a provider. Only the
        # explicitly selected adapter receives its provider credential.
        self.openclaw_key = (
            app_settings.OPENCLAW_API_KEY
            if self.provider == "openclaw" and app_settings.HAS_REAL_OPENCLAW_KEY
            else ""
        )
        self.openclaw_base_url = app_settings.OPENCLAW_BASE_URL
        self._openclaw_use_cli = (self.openclaw_key or "").strip().lower() == "local-gateway"
        # Gemini remains available only as the explicit OpenClaw fallback
        # controlled by allow_fallback; OpenAI never falls through to it.
        self.api_key = app_settings.GEMINI_API_KEY if app_settings.HAS_REAL_GEMINI_KEY else ""
        self.openai_key = (
            app_settings.OPENAI_API_KEY
            if self.provider == "openai" and app_settings.HAS_REAL_OPENAI_KEY
            else ""
        )
        if self.provider == "openai":
            self.default_model = (app_settings.OPENAI_CHAT_MODEL or "").strip()
            self.fast_model = self.default_model
        elif self.provider == "openclaw":
            self.default_model = app_settings.OPENCLAW_DEFAULT_MODEL
            self.fast_model = app_settings.OPENCLAW_FAST_MODEL
        elif self.provider == "gemini":
            self.default_model = app_settings.DEFAULT_MODEL
            self.fast_model = app_settings.FAST_MODEL
        else:
            self.default_model = ""
            self.fast_model = ""
        self.daily_limit = app_settings.GEMINI_DAILY_REQUEST_LIMIT
        self.router_config = build_router_config(app_settings)
        self._redis = None
        self._degraded = False
        self._degraded_until = 0.0
        self._openclaw_disabled_until = 0.0
        self._provider_verified = False
        self._provider_last_error: str | None = None
        self._cost_tracking_healthy = True

    def _using_openclaw(self) -> bool:
        return (
            self.provider == "openclaw"
            and bool(self.openclaw_key)
            and time.time() >= self._openclaw_disabled_until
        )

    def get_provider_readiness(self) -> dict[str, str | bool | None]:
        """Report configuration separately from observed provider health."""
        provider = self.provider if self.provider in {"openclaw", "gemini", "openai"} else ""
        model = self.default_model or None
        if provider == "openai":
            rates_configured = (
                math.isfinite(self.router_config.cheap.pricing.input_cost_per_1m)
                and math.isfinite(self.router_config.cheap.pricing.output_cost_per_1m)
                and self.router_config.cheap.pricing.input_cost_per_1m > 0
                and self.router_config.cheap.pricing.output_cost_per_1m > 0
            )
            try:
                self._validated_openai_base_url(
                    self.settings.OPENAI_BASE_URL,
                )
                base_url_configured = True
            except ValueError:
                base_url_configured = False
            configured = bool(self.openai_key and model and rates_configured and base_url_configured)
        elif provider == "openclaw":
            configured = bool(self.openclaw_key and model)
        elif provider == "gemini":
            configured = bool(self.api_key and model)
        else:
            configured = False

        ready = configured and self._provider_verified and self._cost_tracking_healthy
        if not provider:
            status = "unselected"
        elif not configured:
            status = "misconfigured"
        elif not self._cost_tracking_healthy:
            status = "cost_tracking_unavailable"
        elif not self._provider_verified:
            status = "unverified"
        else:
            status = "healthy"
        return {
            "provider": provider or None,
            "model": model,
            "configured": configured,
            "verified": self._provider_verified,
            "cost_tracking_healthy": self._cost_tracking_healthy,
            "ready": ready,
            "status": status,
            "last_error": self._provider_last_error,
        }

    def _mark_provider_verified(self) -> None:
        self._provider_verified = True
        self._provider_last_error = None
        self._sync_runtime_readiness()

    def _mark_provider_failed(self, reason: str) -> None:
        self._provider_verified = False
        self._provider_last_error = reason
        self._sync_runtime_readiness()

    def _sync_runtime_readiness(self) -> None:
        """Keep the shared runtime readiness aligned with observed provider health."""
        try:
            from app.core.runtime_state import get_runtime_state, set_runtime_state

            state = get_runtime_state()
            if not state.get("updated_at"):
                return
            had_provider_issue = any(
                str(issue).startswith("LLM provider:") for issue in state.get("issues", [])
            )
            issues = [
                issue
                for issue in state.get("issues", [])
                if not str(issue).startswith("LLM provider:")
            ]
            provider_status = self.get_provider_readiness()
            if not provider_status["ready"]:
                issues.append(f"LLM provider: selected provider status is {provider_status['status']}")
                mode = state.get("mode")
                if mode in {"booting", "full"}:
                    mode = "degraded"
                set_runtime_state(False, mode or "degraded", issues)
            else:
                ready = bool(state.get("is_ready") or (had_provider_issue and not issues))
                mode = state.get("mode")
                if ready and mode in {"booting", "blocked"}:
                    # Preserve uncertainty about any warnings omitted from the
                    # runtime state instead of upgrading directly to full.
                    mode = "degraded"
                set_runtime_state(ready, mode or "degraded", issues)
        except Exception:
            logger.debug("Could not synchronize LLM provider runtime readiness")

    @staticmethod
    def _validated_openai_base_url(base_url: str) -> SplitResult:
        try:
            parsed = urlsplit((base_url or "").strip())
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            raise ValueError("OpenAI base URL is invalid") from None
        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OpenAI base URL must use HTTPS without credentials, query, or fragment")
        if hostname.lower() != "api.openai.com":
            raise ValueError("OpenAI base URL must use the official api.openai.com host")
        if port not in (None, 443):
            raise ValueError("OpenAI base URL must use the official HTTPS port")
        if parsed.path.rstrip("/") not in {"", "/v1"}:
            raise ValueError("OpenAI base URL must use the official /v1 path")
        return parsed

    async def _validate_openai_target(self) -> SplitResult:
        parsed = self._validated_openai_base_url(self.settings.OPENAI_BASE_URL)
        port = parsed.port or 443
        addresses = await self._resolve_openai_host(parsed.hostname, port)
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise RuntimeError("OpenAI host resolved to a non-public address")
        return parsed

    async def _resolve_openai_host(self, hostname: str, port: int) -> set[str]:
        try:
            results = await asyncio.get_running_loop().getaddrinfo(
                hostname, port, type=socket.SOCK_STREAM
            )
        except OSError:
            raise RuntimeError("OpenAI host DNS resolution failed") from None
        return {entry[4][0] for entry in results}

    def _openai_completion_url(self) -> str:
        self._validated_openai_base_url(self.settings.OPENAI_BASE_URL)
        return f"{OPENAI_API_BASE}/chat/completions"

    @staticmethod
    def _openai_usage(data: dict) -> tuple[int, int]:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            raise RuntimeError("OpenAI response omitted token usage")
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        if (
            not isinstance(input_tokens, int)
            or isinstance(input_tokens, bool)
            or input_tokens < 0
            or not isinstance(output_tokens, int)
            or isinstance(output_tokens, bool)
            or output_tokens < 0
        ):
            raise RuntimeError("OpenAI response included invalid token usage")
        return input_tokens, output_tokens

    async def _track_openai_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        input_rate = Decimal(str(self.settings.OPENAI_INPUT_PRICE_USD_PER_1M))
        output_rate = Decimal(str(self.settings.OPENAI_OUTPUT_PRICE_USD_PER_1M))
        cost_usd = (
            Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
        ) / Decimal(1_000_000)
        from app.core.cost_tracker import cost_tracker

        tracked = await cost_tracker.track_openai_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        if not tracked:
            self._cost_tracking_healthy = False
            raise RuntimeError("OpenAI usage could not be persisted; further calls paused")

    async def _call_openai(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
        *,
        json_mode: bool = False,
    ) -> str:
        if self.provider != "openai" or not self.openai_key:
            raise RuntimeError("OpenAI is not explicitly selected and configured")
        if model != (self.settings.OPENAI_CHAT_MODEL or "").strip():
            raise RuntimeError("Requested OpenAI model has no configured price")

        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Chat models reject max_tokens and any temperature other than the default.
            "max_completion_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        try:
            await self._validate_openai_target()
            async with httpx.AsyncClient(
                timeout=self.settings.OPENAI_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(
                    self._openai_completion_url(), json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            self._mark_provider_failed("request_timeout")
            raise RuntimeError("OpenAI request timed out") from None
        except httpx.HTTPStatusError as exc:
            self._mark_provider_failed(f"http_{exc.response.status_code}")
            raise RuntimeError(f"OpenAI returned HTTP {exc.response.status_code}") from None
        except httpx.HTTPError:
            self._mark_provider_failed("request_error")
            raise RuntimeError("OpenAI request failed") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._mark_provider_failed("invalid_response")
            raise RuntimeError("OpenAI returned invalid JSON") from None

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            self._mark_provider_failed("missing_choices")
            raise RuntimeError("OpenAI response contained no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            self._mark_provider_failed("missing_content")
            raise RuntimeError("OpenAI response contained no text content")

        input_tokens, output_tokens = self._openai_usage(data)
        await self._track_openai_usage(model, input_tokens, output_tokens)
        self._mark_provider_verified()
        return content.strip()

    async def _get_redis(self):
        """Get Redis client using connection pool with circuit breaker."""
        return await get_redis()

    def _cache_key(self, system: str, user: str, model: str) -> str:
        raw = f"{model}|{system}|{user}"
        return "llm_cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cache(self, key: str) -> str | None:
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

    async def _track_request(self, provider: str | None = None) -> bool:
        provider = (provider or self.provider).strip().lower()
        if provider not in {"gemini", "openclaw", "openai"}:
            return False
        r = await self._get_redis()
        if not r:
            return True
        today_key = f"{provider}_requests:{time.strftime('%Y-%m-%d')}"
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

    async def _call_openai_stream(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        if self.provider != "openai" or not self.openai_key:
            raise RuntimeError("OpenAI is not explicitly selected and configured")
        if model != (self.settings.OPENAI_CHAT_MODEL or "").strip():
            raise RuntimeError("Requested OpenAI model has no configured price")

        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        usage: dict | None = None
        chunk_seen = False
        try:
            await self._validate_openai_target()
            async with httpx.AsyncClient(
                timeout=self.settings.OPENAI_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    self._openai_completion_url(),
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for event in self._iter_sse_json(response):
                        event_usage = event.get("usage")
                        if isinstance(event_usage, dict):
                            usage = event_usage
                        text = self._extract_openai_stream_text(event)
                        if text:
                            chunk_seen = True
                            yield text
        except httpx.TimeoutException:
            self._mark_provider_failed("stream_timeout")
            raise RuntimeError("OpenAI stream timed out") from None
        except httpx.HTTPStatusError as exc:
            self._mark_provider_failed(f"http_{exc.response.status_code}")
            raise RuntimeError(f"OpenAI returned HTTP {exc.response.status_code}") from None
        except httpx.HTTPError:
            self._mark_provider_failed("stream_error")
            raise RuntimeError("OpenAI stream failed") from None

        if not chunk_seen:
            self._mark_provider_failed("empty_stream")
            raise RuntimeError("OpenAI returned an empty stream")
        if usage is None:
            self._mark_provider_failed("stream_usage_missing")
            raise RuntimeError("OpenAI stream omitted token usage")
        try:
            input_tokens, output_tokens = self._openai_usage({"usage": usage})
        except RuntimeError:
            self._mark_provider_failed("invalid_stream_usage")
            raise
        await self._track_openai_usage(model, input_tokens, output_tokens)
        self._mark_provider_verified()

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
        model: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = True,
        task_class: str = "analysis",
        complexity: int | None = None,
        budget_tag: str | None = None,
    ) -> AsyncIterator[str]:
        estimated_input_tokens = len(f"{system}\n{user}".encode("utf-8"))
        routing = route_task(
            task_class=task_class,
            requested_max_tokens=max_tokens,
            complexity=complexity,
            router=self.router_config,
            estimated_input_tokens=estimated_input_tokens,
        )
        if model is None:
            model = routing.model
        max_tokens = min(max_tokens, routing.max_tokens)
        if not routing.pricing_configured:
            logger.warning("LLM stream disabled because the selected model has no configured rate")
            return
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
        if not self.get_provider_readiness()["configured"] or not self._cost_tracking_healthy:
            logger.info("Selected LLM provider is not configured for stream")
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

        if self.is_degraded() and not (
            self.provider == "openclaw" and allow_fallback and bool(self.api_key)
        ):
            logger.warning("LLM in degraded mode — skipping stream")
            return

        chunks: list[str] = []

        async def emit_from(
            stream: AsyncIterator[str],
            used_model: str,
            was_fallback: bool,
            used_provider: str,
        ) -> AsyncIterator[str]:
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
                    provider=used_provider,
                )

        if self.provider == "openai":
            try:
                async for chunk in emit_from(
                    self._call_openai_stream(system, user, model, max_tokens, temperature),
                    model,
                    False,
                    "openai",
                ):
                    yield chunk
                if chunks:
                    return
            except Exception as exc:
                if chunks:
                    self._mark_provider_failed("partial_stream")
                    raise
                self._mark_provider_failed("stream_failed")
                logger.warning("OpenAI stream failed before first chunk (%s)", type(exc).__name__)
                raise RuntimeError("OpenAI stream failed before the first chunk") from None
            return

        if self._using_openclaw():
            try:
                async for chunk in emit_from(
                    self._call_openclaw_stream(system, user, model, max_tokens, temperature),
                    model,
                    False,
                    "openclaw",
                ):
                    yield chunk
                if chunks:
                    return
            except Exception as exc:
                if chunks:
                    self._mark_provider_failed("partial_stream")
                    raise
                self._mark_provider_failed("stream_failed")
                logger.warning("OpenClaw stream failed (%s)", type(exc).__name__)

        if self.provider == "gemini" or (self.provider == "openclaw" and allow_fallback and self.api_key):
            if self.provider == "openclaw" and not await self._track_request("gemini"):
                logger.warning("Gemini fallback daily request limit reached")
                return
            fallback_model = (
                self.settings.CHEAP_MODEL
                if str(self.settings.CHEAP_MODEL or "").startswith("gemini")
                else "gemini-2.0-flash"
            )
            if self.provider == "gemini":
                fallback_model = model
            try:
                async for chunk in emit_from(
                    self._call_gemini_stream(
                        system,
                        user,
                        fallback_model,
                        max_tokens=min(max_tokens, self.settings.MID_MODEL_MAX_TOKENS),
                        temperature=temperature,
                    ),
                    fallback_model,
                    self.provider == "openclaw",
                    "gemini",
                ):
                    yield chunk
                if chunks:
                    return
            except Exception as exc:
                if chunks:
                    self._mark_provider_failed("partial_stream")
                    raise
                logger.warning("Gemini stream failed (%s)", type(exc).__name__)

        if self.provider not in {"openclaw", "gemini"}:
            logger.info("No explicitly selected LLM stream provider")
            return

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
        model: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        allow_fallback: bool = True,
        task_class: str = "analysis",
        complexity: int | None = None,
        budget_tag: str | None = None,
        json_mode: bool = False,
    ) -> str | None:
        estimated_input_tokens = len(f"{system}\n{user}".encode("utf-8"))
        routing = route_task(
            task_class=task_class,
            requested_max_tokens=max_tokens,
            complexity=complexity,
            router=self.router_config,
            estimated_input_tokens=estimated_input_tokens,
        )
        if model is None:
            model = routing.model
        max_tokens = min(max_tokens, routing.max_tokens)
        if not routing.pricing_configured:
            logger.warning("LLM disabled because the selected model has no configured rate")
            self._set_degraded()
            return None
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
        if not self.get_provider_readiness()["configured"] or not self._cost_tracking_healthy:
            logger.info("Selected LLM provider is not configured")
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
        if self.is_degraded() and not (
            self.provider == "openclaw" and allow_fallback and bool(self.api_key)
        ):
            logger.warning("LLM in degraded mode — skipping call")
            return None
        provider_used = self.provider
        model_used = model
        was_fallback = False
        try:
            if self.provider == "openai":
                result = await self._call_openai(
                    system,
                    user,
                    model,
                    max_tokens,
                    temperature,
                    json_mode=json_mode,
                )
            elif self.provider == "openclaw" and self._using_openclaw():
                try:
                    result = await self._call_openclaw(
                        system, user, model, max_tokens, temperature
                    )
                except Exception as exc:
                    self._mark_provider_failed("inference_failed")
                    if not (allow_fallback and self.api_key):
                        raise
                    logger.warning(
                        "OpenClaw call failed (%s); trying configured Gemini fallback",
                        type(exc).__name__,
                    )
                    fallback_model = (
                        self.settings.CHEAP_MODEL
                        if str(self.settings.CHEAP_MODEL or "").startswith("gemini")
                        else "gemini-2.0-flash"
                    )
                    if not await self._track_request("gemini"):
                        raise RuntimeError("Gemini fallback daily request limit reached") from None
                    provider_used = "gemini"
                    model_used = fallback_model
                    was_fallback = True
                    result = await self._call_gemini(
                        system,
                        user,
                        fallback_model,
                        max_tokens=min(max_tokens, self.settings.MID_MODEL_MAX_TOKENS),
                        temperature=temperature,
                    )
            elif self.provider == "openclaw" and allow_fallback and self.api_key:
                self._mark_provider_failed("openclaw_unavailable")
                fallback_model = (
                    self.settings.CHEAP_MODEL
                    if str(self.settings.CHEAP_MODEL or "").startswith("gemini")
                    else "gemini-2.0-flash"
                )
                if not await self._track_request("gemini"):
                    raise RuntimeError("Gemini fallback daily request limit reached") from None
                provider_used = "gemini"
                model_used = fallback_model
                was_fallback = True
                result = await self._call_gemini(
                    system,
                    user,
                    fallback_model,
                    max_tokens=min(max_tokens, self.settings.MID_MODEL_MAX_TOKENS),
                    temperature=temperature,
                )
            elif self.provider == "gemini":
                result = await self._call_gemini(system, user, model, max_tokens, temperature)
            else:
                raise RuntimeError("No supported LLM provider is explicitly selected")
            if provider_used == self.provider:
                self._mark_provider_verified()
            await self._set_cache(cache_key, result)
            await self._log_call(
                model_used,
                user,
                result,
                was_fallback=was_fallback,
                task_class=task_class,
                budget_tag=budget_tag or routing.budget_tag,
                estimated_max_cost_usd=routing.estimated_max_cost_usd,
                provider=provider_used,
            )
            return result
        except Exception as e:
            logger.error("LLM call failed via %s (%s)", provider_used, type(e).__name__)
            self._mark_provider_failed("inference_failed")
            self._set_degraded()
            try:
                from app.telegram_bot.bot import send_message
                await send_message("⚠️ AI ไม่พร้อม — ทำงานด้วย heuristic ชั่วคราว (30 นาที)")
            except Exception:
                pass
            await self._log_call(
                model_used,
                user,
                "",
                was_fallback=True,
                error=str(e),
                task_class=task_class,
                budget_tag=budget_tag or routing.budget_tag,
                estimated_max_cost_usd=routing.estimated_max_cost_usd,
                provider=provider_used,
            )
            return None

    async def verify_provider(self) -> bool:
        """Run one inference so this process reports the selected provider as verified.

        The nonce keeps the Redis response cache from answering the probe.
        """
        await self.complete(
            system="Reply with OK.",
            user=f"Health probe {secrets.token_hex(8)}",
            max_tokens=64,
        )
        return self.get_provider_readiness()["verified"]

    async def complete_json(
        self,
        system: str,
        user: str,
        model: str | None = None,
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
            json_mode=self.provider == "openai",
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
            raise ValueError(f"LLM provider returned invalid JSON: {e}\nRaw: {cleaned[:200]}")

    async def _log_call(
        self,
        model: str,
        user: str,
        result: str,
        was_fallback: bool = False,
        error: str | None = None,
        task_class: str | None = None,
        budget_tag: str | None = None,
        estimated_max_cost_usd: float | None = None,
        provider: str | None = None,
    ) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog
            async with AsyncSessionLocal() as db:
                log = AuditLog(
                    action="llm.call",
                    details={
                        "provider": provider or self.provider,
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
                    success=error is None,
                    error_message=error,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to log LLM call: {e}")

    async def get_cost_today_usd(self) -> float:
        from app.core.cost_tracker import cost_tracker

        return await cost_tracker.get_daily_cost()

    async def get_cost_month_usd(self) -> float:
        from app.core.cost_tracker import cost_tracker

        return await cost_tracker.get_monthly_cost()

    async def get_call_count_today(self, provider: str = "gemini") -> int:
        provider = provider.strip().lower()
        if provider not in {"gemini", "openclaw", "openai"}:
            return 0
        r = await self._get_redis()
        if not r:
            return 0
        try:
            val = await r.get(f"{provider}_requests:{time.strftime('%Y-%m-%d')}")
            return int(val) if val else 0
        except Exception:
            return 0

    async def get_total_call_count_today(self) -> int:
        r = await self._get_redis()
        if not r:
            return 0
        date = time.strftime("%Y-%m-%d")
        try:
            counts = await asyncio.gather(
                *(r.get(f"{provider}_requests:{date}") for provider in ("gemini", "openclaw", "openai"))
            )
            return sum(int(value) for value in counts if value)
        except Exception:
            return 0

    def is_cost_paused(self) -> bool:
        return not self._cost_tracking_healthy

    def get_router_summary(self) -> dict[str, float | bool]:
        return {
            "routing_enabled": self.router_config.routing_enabled,
            "max_single_call_cost_usd": self.router_config.max_single_call_cost_usd,
        }


llm_client = LLMClient()
