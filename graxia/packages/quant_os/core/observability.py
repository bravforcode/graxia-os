"""
Observability — structlog → Loki/Grafana sink.

Configures structlog to send structured logs to:
  - Loki (via HTTP POST to /loki/api/v1/push)
  - Console (always)
  - File (optional)

Usage:
  from core.observability import setup_logging
  setup_logging()  # call once at startup
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog


class LokiSink:
    """Send structured logs to Grafana Loki via HTTP push."""

    def __init__(self, url: str = "", tenant_id: str = ""):
        self.url = url or os.getenv("LOKI_URL", "")
        self.tenant_id = tenant_id or os.getenv("LOKI_TENANT_ID", "")
        self._client = None
        self._buffer: list[list] = []
        self._flush_interval = 5.0  # seconds
        self._last_flush = time.monotonic()

    async def _ensure_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    def __call__(self, logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        """structlog processor — buffers log entry for Loki."""
        if not self.url:
            return event_dict

        # Convert to Loki line format
        ts_ns = str(int(datetime.now(UTC).timestamp() * 1e9))
        labels = {
            "level": event_dict.get("level", "info"),
            "logger": event_dict.get("logger", "unknown"),
        }
        line = json.dumps(event_dict, default=str)
        self._buffer.append([[ts_ns, line], labels])

        # Flush if interval exceeded
        now = time.monotonic()
        if now - self._last_flush >= self._flush_interval:
            self._flush_async()
            self._last_flush = now

        return event_dict

    def _flush_async(self):
        """Flush buffer to Loki (non-blocking)."""
        if not self._buffer:
            return
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._flush())
        except RuntimeError:
            pass

    async def _flush(self):
        """Send buffered logs to Loki."""
        if not self._buffer or not self.url:
            return
        batch = self._buffer[:]
        self._buffer.clear()

        try:
            client = await self._ensure_client()
            streams = {}
            for entry, labels in batch:
                key = json.dumps(labels, sort_keys=True)
                if key not in streams:
                    streams[key] = {"stream": labels, "values": []}
                streams[key]["values"].append(entry)

            payload = {"streams": list(streams.values())}
            headers = {"Content-Type": "application/json"}
            if self.tenant_id:
                headers["X-Scope-OrgID"] = self.tenant_id

            await client.post(f"{self.url}/loki/api/v1/push", json=payload, headers=headers)
        except Exception:
            pass  # Never crash on logging failure


class FileSink:
    """Write structured logs to a JSON file with rotation."""

    def __init__(self, path: str = "", max_bytes: int = 10*1024*1024, backup_count: int = 5):
        self.path = Path(path or os.getenv("LOG_FILE", "logs/quant_os.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._backup_count = backup_count

    def __call__(self, logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        try:
            # Check if rotation needed
            if self.path.exists() and self.path.stat().st_size > self._max_bytes:
                self._rotate()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_dict, default=str) + "\n")
        except Exception:
            pass
        return event_dict

    def _rotate(self):
        """Simple rotation: rename .jsonl.1 → .jsonl.2, etc."""
        for i in range(self._backup_count - 1, 0, -1):
            src = self.path.with_suffix(f".jsonl.{i}")
            dst = self.path.with_suffix(f".jsonl.{i+1}")
            if src.exists():
                src.rename(dst)
        if self.path.exists():
            self.path.rename(self.path.with_suffix(".jsonl.1"))


def setup_logging(
    loki_url: str = "",
    log_file: str = "",
    level: str = "INFO",
) -> None:
    """
    Configure structlog with:
      - Console renderer (always)
      - Loki sink (if URL provided)
      - File sink (if path provided)
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]

    # Add Loki sink
    if loki_url or os.getenv("LOKI_URL"):
        loki = LokiSink(loki_url)
        processors.insert(-1, loki)  # before console renderer

    # Add file sink
    if log_file or os.getenv("LOG_FILE"):
        file_sink = FileSink(log_file)
        processors.insert(-1, file_sink)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
