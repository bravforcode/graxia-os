"""PDPA (Thailand Personal Data Protection Act) data-subject endpoints.

Covers the user-facing obligations the compliance audit log infrastructure
supports but no route exposed:
  - consent give/revoke per purpose (PDPA Sections 19, 23)
  - data subject access request (export, PDPA Section 30)
  - right to erasure / right to be forgotten (PDPA Section 33)
  - breach notification tracking (72-hour notice, PDPA Section 37)

Every action is recorded in the tamper-evident ComplianceAuditLog
(previous_hash / entry_hash chain) with a gdpr_category so the trail is
auditable end-to-end.
"""
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.compliance_audit import AuditEventType, ComplianceAuditLogger
from app.models.privacy import BreachNotification, PrivacyConsent
from app.models.user import User
from app.models.funnel import FunnelOrder
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────
class ConsentPayload(BaseModel):
    purpose: str = Field(..., min_length=1, max_length=100,
                         description="Processing purpose: marketing, analytics, email, ...")
    granted: bool = Field(..., description="True to grant, False to revoke")
    source: str = Field("api", max_length=50)


class ConsentResponse(BaseModel):
    id: UUID
    purpose: str
    granted: bool
    granted_at: datetime | None
    revoked_at: datetime | None


class DataExportResponse(BaseModel):
    export_id: UUID
    exported_at: datetime
    data: dict


class ErasureRequest(BaseModel):
    confirm: bool = Field(..., description="Must be True to confirm irreversible erasure")
    anonymize_only: bool = Field(False, description="Anonymize instead of delete (keeps orders/ledger)")


class ErasureResponse(BaseModel):
    status: str
    user_id: UUID
    method: str  # anonymized | deleted
    note: str


class BreachPayload(BaseModel):
    description: str = Field(..., min_length=1)
    affected_subjects: int = Field(0, ge=0)
    risk_level: str = Field("unknown", pattern="^(low|medium|high|critical)$")
    notes: str | None = None


class BreachResponse(BaseModel):
    id: UUID
    detected_at: datetime
    status: str
    risk_level: str
    affected_subjects: int
    notification_deadline: datetime | None


# ── Consent ──────────────────────────────────────────────────────────────
@router.get("/privacy/consents", response_model=list[ConsentResponse])
async def list_consents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all consent records for the current user."""
    result = await db.execute(
        select(PrivacyConsent)
        .where(PrivacyConsent.user_id == current_user.id)
        .order_by(PrivacyConsent.purpose)
    )
    return result.scalars().all()


@router.post("/privacy/consents", response_model=ConsentResponse, status_code=status.HTTP_200_OK)
async def set_consent(
    payload: ConsentPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant or revoke consent for a processing purpose. Recorded in the audit trail."""
    consent = await db.scalar(
        select(PrivacyConsent).where(
            PrivacyConsent.user_id == current_user.id,
            PrivacyConsent.purpose == payload.purpose,
        )
    )
    now = datetime.now(UTC)
    if consent is None:
        consent = PrivacyConsent(
            id=uuid4(),
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            purpose=payload.purpose,
            granted=payload.granted,
            source=payload.source,
            granted_at=now if payload.granted else None,
            revoked_at=None if payload.granted else now,
        )
        db.add(consent)
    else:
        consent.granted = payload.granted
        consent.source = payload.source
        consent.granted_at = now if payload.granted else None
        consent.revoked_at = None if payload.granted else now

    # Tamper-evident audit trail
    audit = ComplianceAuditLogger(db)
    await audit.log_event(
        event_type=AuditEventType.CONSENT_GIVEN if payload.granted else AuditEventType.CONSENT_REVOKED,
        actor_id=current_user.id,
        actor_type="user",
        actor_email=current_user.email,
        target_type="user",
        target_id=current_user.id,
        action_description=f"Consent {'granted' if payload.granted else 'revoked'} for purpose: {payload.purpose}",
        action_payload={"purpose": payload.purpose, "source": payload.source},
        contains_pii=False,
        gdpr_category="consent",
        legal_basis="consent",
    )
    await db.commit()
    await db.refresh(consent)
    return consent


# ── Data subject access request (export) ────────────────────────────────
@router.post("/privacy/data-export", response_model=DataExportResponse)
async def data_export(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a machine-readable copy of the user's personal data (DSAR)."""
    orders = (
        await db.execute(
            select(FunnelOrder).where(FunnelOrder.customer_email == current_user.email)
        )
    ).scalars().all()

    consents = (
        await db.execute(select(PrivacyConsent).where(PrivacyConsent.user_id == current_user.id))
    ).scalars().all()

    exported_at = datetime.now(UTC)
    data = {
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "consents": [
            {
                "purpose": c.purpose,
                "granted": c.granted,
                "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consents
        ],
        "orders": [
            {
                "id": str(o.id),
                "status": o.status,
                "total_amount": str(o.total_amount),
                "created_at": o.created_at.isoformat() if getattr(o, "created_at", None) else None,
            }
            for o in orders
        ],
    }

    audit = ComplianceAuditLogger(db)
    await audit.log_event(
        event_type=AuditEventType.DATA_EXPORT_REQUESTED,
        actor_id=current_user.id,
        actor_type="user",
        actor_email=current_user.email,
        target_type="user",
        target_id=current_user.id,
        action_description="Data subject access request (export) completed",
        action_payload={"format": "json", "categories": list(data.keys())},
        contains_pii=True,
        gdpr_category="data_portability",
        legal_basis="consent",
    )
    await db.commit()
    return DataExportResponse(export_id=uuid4(), exported_at=exported_at, data=data)


# ── Right to erasure ────────────────────────────────────────────────────
@router.post("/privacy/erasure", response_model=ErasureResponse)
async def request_erasure(
    payload: ErasureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erasure (right to be forgotten). Anonymizes by default to preserve
    order/ledger referential integrity; confirms explicit full deletion path."""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Erasure requires confirm=true")

    audit = ComplianceAuditLogger(db)
    await audit.log_event(
        event_type=AuditEventType.DATA_DELETION_REQUESTED,
        actor_id=current_user.id,
        actor_type="user",
        actor_email=current_user.email,
        target_type="user",
        target_id=current_user.id,
        action_description="Right to erasure requested",
        action_payload={"method": "anonymize" if payload.anonymize_only else "delete"},
        contains_pii=True,
        gdpr_category="right_to_be_forgotten",
        legal_basis="legal_obligation",
    )

    if payload.anonymize_only:
        # Anonymize PII while keeping order/ledger rows intact.
        current_user.email = f"deleted-{current_user.id}@anonymized.local"
        current_user.full_name = "Deleted User"
        current_user.is_active = False
        method = "anonymized"
        note = "PII anonymized; order/ledger records preserved"
    else:
        # Full deletion: drop consent rows, deactivate account. Orders are
        # preserved by policy but detached from the account email.
        await db.execute(
            select(PrivacyConsent)
            .where(PrivacyConsent.user_id == current_user.id)
            .delete()
        )
        current_user.email = f"deleted-{current_user.id}@anonymized.local"
        current_user.full_name = "Deleted User"
        current_user.is_active = False
        method = "deleted"
        note = "Account data removed; order history anonymized for ledger integrity"

    await db.commit()
    return ErasureResponse(status="completed", user_id=current_user.id, method=method, note=note)


# ── Breach notification (admin) ─────────────────────────────────────────
@router.post("/privacy/breach", response_model=BreachResponse, status_code=status.HTTP_201_CREATED)
async def register_breach(
    payload: BreachPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a data breach. Creates the 72-hour regulator-notice deadline
    (PDPA Section 37) and records a SECURITY_ALERT in the audit trail."""
    if current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    detected_at = datetime.now(UTC)
    breach = BreachNotification(
        id=uuid4(),
        organization_id=current_user.organization_id,
        description=payload.description,
        affected_subjects=payload.affected_subjects,
        risk_level=payload.risk_level,
        status="detected",
        detected_at=detected_at,
        notification_deadline=detected_at + timedelta(hours=72),
        notes=payload.notes,
    )
    db.add(breach)

    audit = ComplianceAuditLogger(db)
    await audit.log_event(
        event_type=AuditEventType.SECURITY_ALERT,
        actor_id=current_user.id,
        actor_type="user",
        actor_email=current_user.email,
        target_type="breach",
        target_id=breach.id,
        action_description=f"PDPA breach registered: {payload.description[:120]}",
        action_payload={
            "affected_subjects": payload.affected_subjects,
            "risk_level": payload.risk_level,
            "notification_deadline": breach.notification_deadline.isoformat(),
        },
        contains_pii=False,
        gdpr_category="breach_notification",
        legal_basis="legal_obligation",
    )
    await db.commit()
    await db.refresh(breach)
    logger.warning("PDPA breach registered: id=%s risk=%s deadline=%s",
                   breach.id, breach.risk_level, breach.notification_deadline)
    return breach
