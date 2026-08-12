"""Context cache — in-memory cache for context packs.

Uses in-memory dict storage by default. No filesystem writes unless safe.
Cache key must include root_path, task_type, goal, query, include_paths,
must_preserve, token_budget, project_index_hash, and policy_version.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.context_engine.schemas import ContextCacheEntry, ContextPack

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 300  # 5 minutes


class ContextCache:
    """In-memory context pack cache.

    Thread-safe for single-threaded async use.
    Supports TTL-based expiry and selective invalidation.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._cache: dict[str, ContextPack] = {}
        self._metadata: dict[str, ContextCacheEntry] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, cache_key: str) -> ContextPack | None:
        """Get a context pack from cache by cache_key.

        Returns None if not found or expired.
        """
        entry = self._metadata.get(cache_key)
        if entry is None:
            return None

        # Check expiry
        if entry.expires_at:
            try:
                expiry = datetime.fromisoformat(entry.expires_at)
                if expiry.replace(tzinfo=None) < datetime.now(UTC).replace(tzinfo=None):
                    self._remove(cache_key)
                    return None
            except (ValueError, TypeError):
                self._remove(cache_key)
                return None

        return self._cache.get(cache_key)

    def set(
        self,
        cache_key: str,
        pack: ContextPack,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a context pack in cache."""
        ttl = ttl_seconds or self._ttl_seconds
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat()

        input_hash = hashlib.sha256(
            json.dumps({
                "task_type": pack.task_type,
                "goal": pack.goal,
                "token_budget": pack.token_budget,
                "root_path": pack.root_path,
            }, sort_keys=True).encode()
        ).hexdigest()[:16]

        entry = ContextCacheEntry(
            cache_key=cache_key,
            context_pack_id=pack.context_pack_id,
            created_at=datetime.now(UTC).isoformat(),
            expires_at=expires_at,
            input_hash=input_hash,
            output_hash=pack.cache_key,
            metadata={
                "task_type": pack.task_type,
                "token_budget": pack.token_budget,
                "file_count": len(pack.included_files),
                "estimated_tokens": pack.estimated_tokens,
            },
        )

        self._cache[cache_key] = pack
        self._metadata[cache_key] = entry
        logger.debug("Context cache SET: key=%s pack=%s ttl=%ds", cache_key[:12], pack.context_pack_id, ttl)

    def invalidate(self, cache_key: str | None = None) -> None:
        """Invalidate cache entries.

        Args:
            cache_key: If provided, invalidate only that key.
                       If None, invalidate all entries.
        """
        if cache_key:
            self._remove(cache_key)
            logger.info("Context cache INVALIDATE: key=%s", cache_key[:12])
        else:
            key_count = len(self._cache)
            self._cache.clear()
            self._metadata.clear()
            logger.info("Context cache INVALIDATE ALL: %d entries cleared", key_count)

    def _remove(self, cache_key: str) -> None:
        """Remove a single cache entry."""
        self._cache.pop(cache_key, None)
        self._metadata.pop(cache_key, None)

    def get_entry(self, cache_key: str) -> ContextCacheEntry | None:
        """Get cache metadata entry."""
        entry = self._metadata.get(cache_key)
        if entry is None:
            return None
        if entry.expires_at:
            try:
                expiry = datetime.fromisoformat(entry.expires_at)
                if expiry.replace(tzinfo=None) < datetime.now(UTC).replace(tzinfo=None):
                    self._remove(cache_key)
                    return None
            except (ValueError, TypeError):
                self._remove(cache_key)
                return None
        return entry

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._metadata.clear()
        logger.info("Context cache CLEARED")

    @property
    def size(self) -> int:
        """Number of entries in cache."""
        return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self.size,
            "ttl_seconds": self._ttl_seconds,
            "keys": list(self._metadata.keys())[:10],
        }
