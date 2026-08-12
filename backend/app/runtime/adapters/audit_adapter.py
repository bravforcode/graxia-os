from __future__ import annotations

from typing import Any

from app.runtime.contracts import AuditEvent, ReadinessCheck, ReadinessLevel, ReadinessStatus


def audit_log_to_event(
    audit_log: Any,
    *,
    correlation_id: str,
    organization_id: str | None = None,
    source: str = "audit-log",
) -> AuditEvent:
    resolved_org = organization_id or str(getattr(audit_log, "organization_id", "")) or "00000000-0000-0000-0000-000000000001"
    metadata = getattr(audit_log, "metadata_json", None) or {}
    details = getattr(audit_log, "details", None) or {}
    subject_type = getattr(audit_log, "entity_type", None) or metadata.get("subject_type") or "audit_record"
    subject_id = getattr(audit_log, "entity_id", None) or metadata.get("subject_id") or getattr(audit_log, "id", None)
    risk_level = metadata.get("risk_level") or _derive_risk_level(
        getattr(audit_log, "status", None),
        getattr(audit_log, "action", None),
    )

    payload = {
        "organizationId": resolved_org,
        "correlationId": correlation_id,
        "source": source,
        "auditEventId": getattr(audit_log, "event_id", None) or getattr(audit_log, "id", None),
        "eventType": getattr(audit_log, "event_type", None) or getattr(audit_log, "action", "audit.logged"),
        "actorType": metadata.get("actor_type", "system"),
        "actorId": metadata.get("actor_id") or getattr(audit_log, "triggered_by", None),
        "subjectType": subject_type,
        "subjectId": str(subject_id),
        "riskLevel": risk_level,
        "redactedPayload": {
            "details": _safe_payload(details if isinstance(details, dict) else {"details": details}),
            "metadata": _safe_payload(metadata if isinstance(metadata, dict) else {"metadata": metadata}),
        },
    }
    created_at = getattr(audit_log, "created_at", None)
    if created_at:
        payload["createdAt"] = created_at
    return AuditEvent.model_validate(payload)


def readiness_payload_to_status(
    payload: dict[str, Any],
    *,
    organization_id: str,
    correlation_id: str,
    source: str = "readiness-api",
) -> ReadinessStatus:
    readiness = payload.get("readiness")
    checks: list[ReadinessCheck] = []
    blockers: list[str] = []
    evidence: list[str] = []

    if isinstance(readiness, dict):
        for key, value in readiness.items():
            if isinstance(value, dict):
                ready = bool(value.get("ready", value.get("is_ready", False)))
                detail = value.get("detail") or value.get("status")
            else:
                ready = bool(value)
                detail = str(value)
            checks.append(ReadinessCheck(name=key, ready=ready, detail=detail))
            if not ready:
                blockers.append(key)
            evidence.append(f"{key}={detail}")

    ready = payload.get("status") == "ok" or not blockers
    level = ReadinessLevel.CONTRACT_READY if ready else ReadinessLevel.BASELINE_CLEAN

    return ReadinessStatus.model_validate(
        {
            "organizationId": organization_id,
            "correlationId": correlation_id,
            "source": source,
            "name": "runtime-readiness",
            "ready": ready,
            "level": level.value,
            "checks": [check.model_dump() for check in checks],
            "blockers": blockers,
            "evidence": evidence,
            "metadata": {"service": payload.get("service")},
        }
    )


def _derive_risk_level(status: str | None, action: str | None) -> str:
    normalized_action = (action or "").lower()
    if status == "blocked":
        return "DANGEROUS_BLOCKED"
    if "approval" in normalized_action or "resolve" in normalized_action:
        return "APPROVAL_REQUIRED"
    if any(term in normalized_action for term in ("write", "update", "send", "share")):
        return "LOW_WRITE"
    return "READ_ONLY"


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in {"secret", "token", "password", "credentials", "key"}:
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe
