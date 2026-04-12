"""Redis-backed session management with an in-memory fallback for tests."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from app.config import settings
from app.core.monitoring import metrics_collector
from app.telegram_bot.bot import send_message


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    user_id: str
    device_id: str
    ip_address: str
    user_agent: str
    created_at: float
    last_seen: float
    refresh_jti: str | None = None
    revoked: bool = False


@dataclass(slots=True)
class LockoutStatus:
    is_locked: bool
    failures_in_window: int
    lockout_duration_seconds: int | None = None


_memory_lock = asyncio.Lock()
_memory_user_sessions: dict[str, list[str]] = defaultdict(list)
_memory_sessions: dict[str, SessionRecord] = {}
_memory_refresh_usage: dict[str, float] = {}
_memory_known_devices: dict[str, set[str]] = defaultdict(set)
_memory_failures: dict[str, list[float]] = defaultdict(list)
_memory_lockouts: dict[str, float] = {}
_memory_lockout_count: dict[str, int] = defaultdict(int)
_memory_login_history: dict[str, list[float]] = defaultdict(list)


def reset_session_service_state() -> None:
    _memory_user_sessions.clear()
    _memory_sessions.clear()
    _memory_refresh_usage.clear()
    _memory_known_devices.clear()
    _memory_failures.clear()
    _memory_lockouts.clear()
    _memory_lockout_count.clear()
    _memory_login_history.clear()


class RefreshTokenReuseDetected(RuntimeError):
    """Raised when a refresh token is replayed."""


class SessionService:
    FAILED_ATTEMPT_WINDOW_SECONDS = 600
    BASE_LOCKOUT_SECONDS = 900
    MAX_LOCKOUT_SECONDS = 86400
    MAX_FAILED_ATTEMPTS = 5

    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client

    async def create_session(self, *, user_id: str, device_id: str, ip_address: str, user_agent: str) -> SessionRecord:
        if self.redis:
            return await self._create_session_redis(
                user_id=user_id,
                device_id=device_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return await self._create_session_memory(
            user_id=user_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_session(self, session_id: str | None) -> SessionRecord | None:
        if not session_id:
            return None
        if self.redis:
            return await self._get_session_redis(session_id)
        async with _memory_lock:
            return _memory_sessions.get(session_id)

    async def is_session_active(self, session_id: str | None) -> bool:
        session = await self.get_session(session_id)
        return bool(session and not session.revoked)

    async def bind_refresh_jti(self, session_id: str, refresh_jti: str) -> None:
        if self.redis:
            await self.redis.hset(f"session:{session_id}", mapping={"refresh_jti": refresh_jti})
            return
        async with _memory_lock:
            session = _memory_sessions.get(session_id)
            if session:
                session.refresh_jti = refresh_jti

    async def rotate_refresh_token(self, *, old_jti: str, session_id: str, new_jti: str) -> None:
        if not old_jti:
            return
        if self.redis:
            used_key = f"refresh_jti:{old_jti}:used"
            if await self.redis.get(used_key):
                await self.invalidate_session(session_id, reason="refresh_token_reuse")
                metrics_collector.record_refresh_token_reuse()
                await self._send_security_alert(
                    f"CRITICAL refresh token reuse detected for session `{session_id}`."
                )
                raise RefreshTokenReuseDetected("Refresh token reuse detected")
            await self.redis.setex(
                used_key,
                settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                "1",
            )
            await self.bind_refresh_jti(session_id, new_jti)
            return

        async with _memory_lock:
            if old_jti in _memory_refresh_usage:
                await self.invalidate_session(session_id, reason="refresh_token_reuse")
                metrics_collector.record_refresh_token_reuse()
                raise RefreshTokenReuseDetected("Refresh token reuse detected")
            _memory_refresh_usage[old_jti] = time.time()
            session = _memory_sessions.get(session_id)
            if session:
                session.refresh_jti = new_jti

    async def invalidate_session(self, session_id: str, *, reason: str) -> None:
        if self.redis:
            session = await self._get_session_redis(session_id)
            if session is None:
                return
            await self.redis.hset(f"session:{session_id}", mapping={"revoked": "1", "revoke_reason": reason})
            return
        async with _memory_lock:
            session = _memory_sessions.get(session_id)
            if session:
                session.revoked = True

    async def invalidate_all_user_sessions(self, user_id: str, *, reason: str) -> None:
        if self.redis:
            session_ids = await self.redis.zrange(f"user:{user_id}:sessions", 0, -1)
            for session_id in session_ids:
                await self.invalidate_session(session_id, reason=reason)
            await self.redis.delete(f"user:{user_id}:sessions")
            return
        async with _memory_lock:
            for session_id in list(_memory_user_sessions.get(user_id, [])):
                session = _memory_sessions.get(session_id)
                if session:
                    session.revoked = True
            _memory_user_sessions[user_id] = []

    async def get_known_devices(self, user_id: str) -> set[str]:
        if self.redis:
            values = await self.redis.smembers(f"user:{user_id}:devices")
            return {value for value in values if value}
        async with _memory_lock:
            return set(_memory_known_devices.get(user_id, set()))

    async def recent_login_count(self, user_id: str, *, window_seconds: int = 3600) -> int:
        cutoff = time.time() - window_seconds
        if self.redis:
            key = f"user:{user_id}:login_history"
            await self.redis.zremrangebyscore(key, 0, cutoff)
            return int(await self.redis.zcard(key) or 0)
        async with _memory_lock:
            history = [entry for entry in _memory_login_history[user_id] if entry >= cutoff]
            _memory_login_history[user_id] = history
            return len(history)

    async def record_successful_login(self, *, user_id: str, identifier: str, device_id: str) -> None:
        now = time.time()
        if self.redis:
            pipe = self.redis.pipeline()
            pipe.delete(f"login_failures:{identifier}")
            pipe.sadd(f"user:{user_id}:devices", device_id)
            pipe.zadd(f"user:{user_id}:login_history", {str(now): now})
            pipe.expire(f"user:{user_id}:login_history", 3600)
            await pipe.execute()
            return
        async with _memory_lock:
            _memory_failures.pop(identifier, None)
            _memory_known_devices[user_id].add(device_id)
            _memory_login_history[user_id].append(now)

    async def record_failed_login(self, *, identifier: str, ip_address: str) -> LockoutStatus:
        now = time.time()
        if self.redis:
            failures_key = f"login_failures:{identifier}"
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(failures_key, 0, now - self.FAILED_ATTEMPT_WINDOW_SECONDS)
            pipe.zadd(failures_key, {f"{now}:{ip_address}": now})
            pipe.zcard(failures_key)
            pipe.expire(failures_key, self.FAILED_ATTEMPT_WINDOW_SECONDS)
            _, _, failures, _ = await pipe.execute()
            failures = int(failures or 0)
            if failures >= self.MAX_FAILED_ATTEMPTS:
                metrics_collector.record_account_lock()
                lockout_count = int(await self.redis.get(f"lockout_count:{identifier}") or 0)
                duration = min(
                    int(self.BASE_LOCKOUT_SECONDS * (2 ** lockout_count)),
                    self.MAX_LOCKOUT_SECONDS,
                )
                await self.redis.setex(f"lockout:{identifier}", duration, "1")
                await self.redis.incr(f"lockout_count:{identifier}")
                await self._send_security_alert(
                    f"HIGH account lockout triggered for `{identifier}` from IP `{ip_address}` for {duration}s."
                )
                return LockoutStatus(True, failures, duration)
            metrics_collector.record_failed_login("invalid_credentials")
            return LockoutStatus(False, failures, None)

        async with _memory_lock:
            attempts = [entry for entry in _memory_failures[identifier] if entry >= now - self.FAILED_ATTEMPT_WINDOW_SECONDS]
            attempts.append(now)
            _memory_failures[identifier] = attempts
            if len(attempts) >= self.MAX_FAILED_ATTEMPTS:
                metrics_collector.record_account_lock()
                lockout_count = _memory_lockout_count[identifier]
                duration = min(int(self.BASE_LOCKOUT_SECONDS * (2**lockout_count)), self.MAX_LOCKOUT_SECONDS)
                _memory_lockout_count[identifier] += 1
                _memory_lockouts[identifier] = now + duration
                return LockoutStatus(True, len(attempts), duration)
            metrics_collector.record_failed_login("invalid_credentials")
            return LockoutStatus(False, len(attempts), None)

    async def check_lockout(self, identifier: str) -> LockoutStatus:
        now = time.time()
        if self.redis:
            if await self.redis.get(f"lockout:{identifier}"):
                failures_key = f"login_failures:{identifier}"
                failures = int(await self.redis.zcard(failures_key) or 0)
                ttl = await self.redis.ttl(f"lockout:{identifier}")
                return LockoutStatus(True, failures, ttl if ttl and ttl > 0 else None)
            failures = int(await self.redis.zcard(f"login_failures:{identifier}") or 0)
            return LockoutStatus(False, failures, None)
        async with _memory_lock:
            locked_until = _memory_lockouts.get(identifier, 0)
            attempts = [entry for entry in _memory_failures[identifier] if entry >= now - self.FAILED_ATTEMPT_WINDOW_SECONDS]
            _memory_failures[identifier] = attempts
            if locked_until > now:
                return LockoutStatus(True, len(attempts), int(locked_until - now))
            return LockoutStatus(False, len(attempts), None)

    async def _create_session_memory(
        self, *, user_id: str, device_id: str, ip_address: str, user_agent: str
    ) -> SessionRecord:
        async with _memory_lock:
            user_sessions = _memory_user_sessions[user_id]
            if len(user_sessions) >= settings.SESSION_MAX_CONCURRENT:
                oldest = user_sessions.pop(0)
                if oldest in _memory_sessions:
                    _memory_sessions[oldest].revoked = True
            session = SessionRecord(
                session_id=str(uuid4()),
                user_id=user_id,
                device_id=device_id,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=time.time(),
                last_seen=time.time(),
            )
            _memory_sessions[session.session_id] = session
            user_sessions.append(session.session_id)
            _memory_known_devices[user_id].add(device_id)
            return session

    async def _create_session_redis(
        self, *, user_id: str, device_id: str, ip_address: str, user_agent: str
    ) -> SessionRecord:
        session_id = str(uuid4())
        now = time.time()
        key = f"user:{user_id}:sessions"
        session_ids = await self.redis.zrange(key, 0, -1)
        if len(session_ids) >= settings.SESSION_MAX_CONCURRENT:
            oldest = session_ids[0]
            await self.invalidate_session(oldest, reason="session_limit_eviction")
            await self.redis.zrem(key, oldest)
        session = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            last_seen=now,
        )
        pipe = self.redis.pipeline()
        pipe.hset(f"session:{session_id}", mapping={key: str(value) for key, value in asdict(session).items()})
        pipe.expire(f"session:{session_id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        pipe.zadd(key, {session_id: now})
        pipe.sadd(f"user:{user_id}:devices", device_id)
        await pipe.execute()
        return session

    async def _get_session_redis(self, session_id: str) -> SessionRecord | None:
        raw = await self.redis.hgetall(f"session:{session_id}")
        if not raw:
            return None
        return SessionRecord(
            session_id=raw["session_id"],
            user_id=raw["user_id"],
            device_id=raw.get("device_id", ""),
            ip_address=raw.get("ip_address", ""),
            user_agent=raw.get("user_agent", ""),
            created_at=float(raw.get("created_at", 0)),
            last_seen=float(raw.get("last_seen", 0)),
            refresh_jti=raw.get("refresh_jti"),
            revoked=raw.get("revoked", "False") in {"1", "True", "true"},
        )

    async def _send_security_alert(self, message: str) -> None:
        try:
            await send_message(message, parse_mode=None)
        except Exception:
            return
