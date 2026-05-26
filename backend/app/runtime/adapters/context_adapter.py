from __future__ import annotations

from uuid import UUID

from app.context_engine.schemas import ContextPack
from app.runtime.contracts import ContextPacketRef


def context_pack_to_ref(
    pack: ContextPack,
    *,
    organization_id: UUID | str,
    correlation_id: str,
    compression_mode: str = "compact",
    quality_gate_status: str = "not_checked",
    policy_version: str = "2026-05-26",
    source: str = "context-engine",
) -> ContextPacketRef:
    return ContextPacketRef.model_validate(
        {
            "organizationId": str(organization_id),
            "correlationId": correlation_id,
            "source": source,
            "contextPacketId": pack.context_pack_id,
            "taskType": pack.task_type,
            "goal": pack.goal,
            "estimatedTokens": pack.estimated_tokens,
            "compressionMode": compression_mode,
            "qualityGateStatus": quality_gate_status,
            "fileHashes": {
                item.path: item.sha256
                for item in pack.included_files
                if item.path and item.sha256
            },
            "policyVersion": policy_version,
            "generatedAt": pack.generated_at,
        }
    )
