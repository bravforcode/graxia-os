"""Canonical business event emission service."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.runtime.adapters.funnel_event_adapter import funnel_action_to_business_event
from app.runtime.contracts import ActorType, BusinessEvent, RiskLevel
from app.runtime.events.repository import InMemoryBusinessEventRepository

_SECRET_MARKERS = ("token", "secret", "password", "cookie")


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                continue
            sanitized[key] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


class BusinessEventService:
    def __init__(self, repository: InMemoryBusinessEventRepository | None = None) -> None:
        self.repository = repository or InMemoryBusinessEventRepository()

    async def emit(
        self,
        *,
        organization_id: str,
        event_type: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any] | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
        actor_id: str | None = None,
        source: str = "graxia",
        risk_level: RiskLevel | str = RiskLevel.READ_ONLY,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> BusinessEvent:
        event = funnel_action_to_business_event(
            organization_id=organization_id,
            correlation_id=correlation_id or f"corr-{uuid4().hex[:12]}",
            event_type=event_type,
            subject_type=subject_type,
            subject_id=subject_id,
            payload=_sanitize_payload(payload or {}),
            actor_type=str(actor_type),
            actor_id=actor_id,
            risk_level=str(risk_level),
            source=source,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
        )
        return await self.repository.add(event)


business_event_repository = InMemoryBusinessEventRepository()
business_event_service = BusinessEventService(repository=business_event_repository)
