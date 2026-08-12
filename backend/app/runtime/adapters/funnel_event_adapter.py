from __future__ import annotations

from typing import Any

from app.runtime.contracts import BusinessEvent


def funnel_action_to_business_event(
    *,
    organization_id: str,
    correlation_id: str,
    event_type: str,
    subject_type: str,
    subject_id: str,
    payload: dict[str, Any] | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    risk_level: str = "READ_ONLY",
    source: str = "graxia-api",
    causation_id: str | None = None,
    idempotency_key: str | None = None,
) -> BusinessEvent:
    return BusinessEvent.model_validate(
        {
            "organizationId": organization_id,
            "correlationId": correlation_id,
            "source": source,
            "eventType": event_type,
            "actorType": actor_type,
            "actorId": actor_id,
            "subjectType": subject_type,
            "subjectId": subject_id,
            "causationId": causation_id,
            "idempotencyKey": idempotency_key,
            "riskLevel": risk_level,
            "payload": payload or {},
        }
    )

