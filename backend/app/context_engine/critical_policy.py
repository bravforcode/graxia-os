"""Critical context policy for correctness-first context packs."""
from __future__ import annotations

from pathlib import PurePosixPath

AGGRESSIVE_CONTENT_MODES = {"summary", "metadata_only"}
_CRITICAL_PATH_MARKERS = (
    "auth/",
    "security",
    "approval",
    "payment",
    "stripe",
    "delivery",
    "mcp/schemas",
    "mcp/tools",
    "alembic/",
    "migrations",
    "rate_limit",
    "readiness",
    "audit",
)
_CRITICAL_NAME_MARKERS = (
    "stacktrace",
    "traceback",
    "error",
    "migration",
    "schema",
)
_CRITICAL_TEXT_MARKERS = (
    "traceback",
    "assertionerror",
    "typeerror",
    "importerror",
    "delivery token",
    "allow_live_stripe",
    "database_url",
    "approval_required",
)


def normalize_path(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/"))).lower()


def get_critical_reason(path: str) -> str | None:
    normalized = normalize_path(path)
    name = PurePosixPath(normalized).name

    for marker in _CRITICAL_PATH_MARKERS:
        if marker in normalized:
            return f"path marker: {marker}"
    for marker in _CRITICAL_NAME_MARKERS:
        if marker in name:
            return f"name marker: {marker}"
    return None


def is_critical_path(path: str) -> bool:
    return get_critical_reason(path) is not None


def is_aggressive_content_mode(mode: str) -> bool:
    return mode in AGGRESSIVE_CONTENT_MODES


def contains_critical_text(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _CRITICAL_TEXT_MARKERS)
