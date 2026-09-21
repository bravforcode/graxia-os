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
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.compliance_audit import AuditEventType, ComplianceAuditLogger
from app.models.contact import Contact
from app.models.privacy import BreachNotification, PrivacyConsent
from app.models.user import User
from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DeliveryEmailEvent,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelRecommendation,
    LeadCapture,
)
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


def _metadata_references_subject(metadata: object, subject_values: set[str]) -> bool:
    """Match only explicit scalar subject references in JSON metadata."""
    if isinstance(metadata, dict):
        return any(_metadata_references_subject(value, subject_values) for value in metadata.values())
    if isinstance(metadata, (list, tuple)):
        return any(_metadata_references_subject(value, subject_values) for value in metadata)
    return isinstance(metadata, str) and metadata in subject_values


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
    method: str  # anonymized | scrubbed
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
        # Full erasure: retain the user row for FK/audit integrity, but scrub
        # every identifying, credential, MFA, and provider field. Orders and
        # the audit trail remain preserved by policy.
        original_email = current_user.email
        organization_id = current_user.organization_id
        user_subject_values = {str(current_user.id), original_email}

        contacts = (
            await db.execute(
                select(Contact).where(
                    Contact.organization_id == organization_id,
                    Contact.email == original_email,
                )
            )
        ).scalars().all()
        contact_ids = {contact.id for contact in contacts}

        orders = (
            await db.execute(
                select(FunnelOrder).where(
                    FunnelOrder.organization_id == organization_id,
                    or_(
                        FunnelOrder.user_id == current_user.id,
                        FunnelOrder.customer_email == original_email,
                    ),
                )
            )
        ).scalars().all()
        order_ids = {order.id for order in orders}
        contact_ids.update(order.contact_id for order in orders if order.contact_id)

        checkout_sessions = (
            await db.execute(
                select(FunnelCheckoutSession).where(
                    FunnelCheckoutSession.organization_id == organization_id,
                    or_(
                        FunnelCheckoutSession.user_id == current_user.id,
                        FunnelCheckoutSession.customer_email == original_email,
                    ),
                )
            )
        ).scalars().all()
        checkout_ids = {session.id for session in checkout_sessions}
        contact_ids.update(session.contact_id for session in checkout_sessions if session.contact_id)

        if contact_ids:
            contacts.extend(
                (
                    await db.execute(
                        select(Contact).where(
                            Contact.organization_id == organization_id,
                            Contact.id.in_(contact_ids),
                        )
                    )
                ).scalars().all()
            )

        for contact in {contact.id: contact for contact in contacts}.values():
            contact.name = f"Deleted Contact {contact.id}"
            contact.role = None
            contact.company = None
            contact.contact_type = None
            contact.linkedin_url = None
            contact.email = None
            contact.telegram_handle = None
            contact.github_handle = None
            contact.other_channels = None
            contact.marketing_consent = False
            contact.marketing_consent_at = None
            contact.consent_version = None
            contact.marketing_unsubscribed = False
            contact.marketing_unsubscribed_at = None
            contact.followup_reason = None
            contact.notes = None
            contact.conversation_summary = None
            contact.met_at = None
            contact.referred_by = None
            contact.status = "Deleted"
            contact.is_deleted = True
            contact.deleted_at = datetime.now(UTC)

        subject_values = user_subject_values | {str(value) for value in contact_ids}
        subject_values |= {str(value) for value in order_ids | checkout_ids}

        for session in checkout_sessions:
            if _metadata_references_subject(session.metadata_json, subject_values):
                checkout_ids.add(session.id)
            session.contact_id = None
            session.user_id = None
            session.customer_email = None
            session.stripe_session_id = None
            session.metadata_json = None

        if checkout_ids - {session.id for session in checkout_sessions}:
            extra_sessions = (
                await db.execute(
                    select(FunnelCheckoutSession).where(
                        FunnelCheckoutSession.organization_id == organization_id,
                        FunnelCheckoutSession.id.in_(checkout_ids),
                    )
                )
            ).scalars().all()
            for session in extra_sessions:
                session.contact_id = None
                session.user_id = None
                session.customer_email = None
                session.stripe_session_id = None
                session.metadata_json = None

        delivery_accesses = (
            await db.execute(
                select(DeliveryAccess).where(
                    DeliveryAccess.organization_id == organization_id,
                    or_(
                        DeliveryAccess.order_id.in_(order_ids) if order_ids else False,
                        DeliveryAccess.contact_id.in_(contact_ids) if contact_ids else False,
                    ),
                )
            )
        ).scalars().all()
        for access in delivery_accesses:
            access.contact_id = None
            access.access_token_hash = None
            access.metadata_json = None

        for order in orders:
            order.user_id = None
            order.contact_id = None
            order.checkout_session_id = None
            order.customer_email = None

        delivery_events = (
            await db.execute(
                select(DeliveryEmailEvent).where(
                    DeliveryEmailEvent.organization_id == organization_id,
                    or_(
                        DeliveryEmailEvent.order_id.in_(order_ids) if order_ids else False,
                        DeliveryEmailEvent.customer_email == original_email,
                    ),
                )
            )
        ).scalars().all()
        for event in delivery_events:
            event.customer_email = f"deleted-{event.id}@anonymized.local"
            event.delivery_access_id = None
            event.idempotency_key = f"deleted-{event.id}"
            event.metadata_json = None

        lead_captures = (
            await db.execute(
                select(LeadCapture).where(
                    LeadCapture.organization_id == organization_id,
                    LeadCapture.email == original_email,
                )
            )
        ).scalars().all()
        for capture in lead_captures:
            capture.email = f"deleted-{capture.id}@anonymized.local"
            capture.source = None
            capture.utm_source = None
            capture.utm_medium = None
            capture.utm_campaign = None
            capture.metadata_json = None

        conversion_events = (
            await db.execute(
                select(ConversionEvent).where(
                    ConversionEvent.organization_id == organization_id,
                )
            )
        ).scalars().all()
        for event in conversion_events:
            linked = (
                event.contact_id in contact_ids
                or event.order_id in order_ids
                or event.session_id in subject_values
                or _metadata_references_subject(event.metadata_json, subject_values)
            )
            if not linked:
                continue
            event.contact_id = None
            event.order_id = None
            event.session_id = None
            event.idempotency_key = None
            event.source = None
            event.medium = None
            event.campaign = None
            event.referrer = None
            event.first_touch_source = None
            event.first_touch_medium = None
            event.first_touch_campaign = None
            event.first_touch_referrer = None
            event.first_touch_path = None
            event.last_touch_source = None
            event.last_touch_medium = None
            event.last_touch_campaign = None
            event.last_touch_referrer = None
            event.last_touch_path = None
            event.landing_path = None
            event.content_id = None
            event.referral_code = None
            event.metadata_json = None

        recommendations = (
            await db.execute(
                select(FunnelRecommendation).where(
                    FunnelRecommendation.organization_id == organization_id,
                )
            )
        ).scalars().all()
        for recommendation in recommendations:
            if _metadata_references_subject(recommendation.metadata_json, subject_values):
                recommendation.metadata_json = None

        await db.execute(
            delete(PrivacyConsent)
            .where(PrivacyConsent.user_id == current_user.id)
        )
        current_user.email = f"deleted-{current_user.id}@anonymized.local"
        current_user.full_name = None
        current_user.hashed_password = "!deleted!"
        current_user.last_login_at = None
        current_user.totp_secret = None
        current_user.totp_enabled = False
        current_user.provider = None
        current_user.provider_id = None
        current_user.avatar_url = None
        current_user.onboarding_completed_at = None
        current_user.is_active = False
        method = "scrubbed"
        note = "User data scrubbed; order history and audit trail preserved"

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
