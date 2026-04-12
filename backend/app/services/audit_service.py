"""Audit helpers for auth and security events."""
from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.models.audit import AuditLog


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _build_checksum(previous_checksum: str, payload: dict[str, Any]) -> str:
    content = f"{previous_checksum}|{_stable_json(payload)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _maybe_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


@asynccontextmanager
async def _session_scope(app: Any | None = None, db: AsyncSession | None = None) -> AsyncGenerator[AsyncSession, None]:
    if db is not None:
        yield db
        return

    override = None
    if app is not None:
        override = app.dependency_overrides.get(get_db)

    if override is not None:
        generator = override()
        session = await generator.__anext__()
        try:
            yield session
        finally:
            await generator.aclose()
        return

    async with AsyncSessionLocal() as session:
        yield session


async def log_audit_event(
    *,
    app: Any | None = None,
    db: AsyncSession | None = None,
    action: str,
    event_type: str,
    event_category: str,
    severity: str = "INFO",
    outcome: str = "success",
    success: bool | None = None,
    metadata: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    triggered_by: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    error_message: str | None = None,
    was_fallback: bool | None = False,
) -> AuditLog:
    now = datetime.now(timezone.utc)
    metadata = metadata or {}
    details = details or metadata
    async with _session_scope(app=app, db=db) as session:
        previous_checksum = (
            await session.scalar(select(AuditLog.checksum).order_by(desc(AuditLog.created_at)).limit(1))
            or ""
        )
        payload = {
            "action": action,
            "event_type": event_type,
            "event_category": event_category,
            "severity": severity,
            "outcome": outcome,
            "metadata": metadata,
            "user_id": user_id,
            "session_id": session_id,
            "ip_address": ip_address,
            "request_path": request_path,
            "request_method": request_method,
            "created_at": now.isoformat(),
        }
        record = AuditLog(
            action=action,
            event_type=event_type,
            event_category=event_category,
            severity=severity,
            outcome=outcome,
            success=success if success is not None else outcome == "success",
            metadata_json=metadata,
            details=details,
            triggered_by=triggered_by,
            user_id=_maybe_uuid(user_id),
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method,
            entity_type=entity_type,
            entity_id=_maybe_uuid(entity_id),
            error_message=error_message,
            was_fallback=was_fallback,
            checksum=_build_checksum(previous_checksum, payload),
        )
        session.add(record)
        if db is None:
            await session.commit()
        else:
            await session.flush()
        return record
