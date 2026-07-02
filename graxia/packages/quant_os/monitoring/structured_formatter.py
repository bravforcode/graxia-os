"""
Custom structlog processors for structured logging.

Adds timestamp, level, module, function, line number, and correlation_id.
Provides both console (human-readable) and JSON (machine-readable) formatters.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import structlog

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def add_structured_fields(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add timestamp, level, module, function, line, and correlation_id."""
    now = datetime.now(UTC)

    # Caller info from stack
    frame = sys._getframe(3)  # type: ignore[attr-defined]
    event_dict["timestamp"] = now.isoformat()
    event_dict["module"] = os.path.basename(frame.f_code.co_filename).removesuffix(".py")
    event_dict["function"] = frame.f_code.co_name
    event_dict["line"] = frame.f_lineno
    event_dict["correlation_id"] = correlation_id_var.get("")

    return event_dict


def json_formatter(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> str:
    """Render event dict as compact JSON line."""
    return json.dumps(event_dict, default=str, separators=(",", ":"))


def console_formatter(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> str:
    """Render event dict as human-readable console line."""
    level = event_dict.get("level", "?").upper().ljust(8)
    ts = event_dict.get("timestamp", "")[:19]
    module = event_dict.get("module", "?")
    func = event_dict.get("function", "?")
    line = event_dict.get("line", "?")
    event = event_dict.get("event", "")
    corr = event_dict.get("correlation_id", "")
    msg = event_dict.get("message", event)

    base = f"{ts} {level} [{module}:{func}:{line}] {msg}"
    if corr:
        base += f" (cid={corr})"
    # Include extra keys
    skip = {"timestamp", "level", "module", "function", "line", "correlation_id", "event", "message"}
    extras = {k: v for k, v in event_dict.items() if k not in skip}
    if extras:
        base += " " + json.dumps(extras, default=str, separators=(",", ":"))
    return base


def setup_structured_logging(
    level: str = "INFO",
    fmt: str = "console",
    log_file: str = "",
) -> None:
    """
    Configure structlog with structured fields and chosen formatter.

    fmt: "console" for human-readable, "json" for machine-readable.
    """
    if fmt == "json":
        renderer = json_formatter
    else:
        renderer = console_formatter

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        add_structured_fields,
        renderer,
    ]

    if log_file:
        from monitoring.log_rotation import rotate_all

        log_path = os.path.dirname(log_file)
        if log_path:
            os.makedirs(log_path, exist_ok=True)
        rotate_all(log_path or "logs")

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
