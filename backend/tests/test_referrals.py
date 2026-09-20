from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.funnel import FunnelOrder
from app.models.referral import (
    ReferralAttribution,
    ReferralConversion,
    ReferralPartner,
)
from app.services.referral_service import (
    ReferralEligibilityError,
    ReferralService,
    ReferralValidationError,
    hash_referral_code,
)


@pytest.mark.asyncio
async def test_issue_code_requires_captured_lead_and_keeps_code_opaque(
    db_session: AsyncSession, default_org
):
    contact = Contact(
        organization_id=default_org.id,
        name="Captured Lead",
        email="lead@example.com",
        contact_type="lead",
        relationship_strength=1,
        is_deleted=False,
    )
    db_session.add(contact)
    await db_session.commit()

    service = ReferralService(db_session)
    issued = await service.issue_code(
        organization_id=default_org.id,
        issuer_user_id=uuid4(),
        source_type="captured_lead",
        source_id=contact.id,
        redirect_path="/store",
        owner_identity="owner-1",
        bonus_asset_path="/free/referral-bonus",
    )

    assert issued.code
    assert issued.code != "/store"
    assert hash_referral_code(issued.code) == issued.record.code_hash
    assert issued.record.bonus_asset_path == "/free/referral-bonus"


@pytest.mark.asyncio
async def test_issue_code_rejects_unapproved_partner_and_external_redirect(
    db_session: AsyncSession, default_org
):
    partner = ReferralPartner(
        organization_id=default_org.id,
        display_name="Pending Partner",
        status="pending",
        commission_rate=Decimal("0.20"),
    )
    db_session.add(partner)
    await db_session.commit()

    service = ReferralService(db_session)
    with pytest.raises(ReferralEligibilityError):
        await service.issue_code(
            organization_id=default_org.id,
            issuer_user_id=uuid4(),
            source_type="approved_partner",
            source_id=partner.id,
            redirect_path="/store",
        )

    with pytest.raises(ReferralValidationError):
        await service.issue_code(
            organization_id=default_org.id,
            issuer_user_id=uuid4(),
            source_type="approved_partner",
            source_id=partner.id,
            redirect_path="https://evil.example/claim",
        )


@pytest.mark.asyncio
async def test_public_resolution_accepts_first_session_only_and_rejects_self_referral(
    db_session: AsyncSession,
    default_org,
    public_async_client: AsyncClient,
):
    contact = Contact(
        organization_id=default_org.id,
        name="Captured Lead",
        email="lead-2@example.com",
        contact_type="lead",
        relationship_strength=1,
        is_deleted=False,
    )
    db_session.add(contact)
    await db_session.commit()
    service = ReferralService(db_session)
    first = await service.issue_code(
        organization_id=default_org.id,
        issuer_user_id=uuid4(),
        source_type="captured_lead",
        source_id=contact.id,
        redirect_path="/store",
        owner_identity="owner-2",
    )
    second = await service.issue_code(
        organization_id=default_org.id,
        issuer_user_id=uuid4(),
        source_type="captured_lead",
        source_id=contact.id,
        redirect_path="/guides/automation",
        owner_identity="owner-3",
    )

    self_response = await public_async_client.get(
        f"/api/v1/public/referrals/{first.code}",
        params={"session_id": "self-session", "identity_key": "owner-2"},
    )
    assert self_response.status_code == 404

    first_response = await public_async_client.get(
        f"/api/v1/public/referrals/{first.code}",
        params={"session_id": "session-1"},
    )
    second_response = await public_async_client.get(
        f"/api/v1/public/referrals/{second.code}",
        params={"session_id": "session-1"},
    )
    assert first_response.status_code == 307
    assert first_response.headers["location"] == "/store"
    assert second_response.status_code == 307
    assert second_response.headers["location"] == "/guides/automation"

    attribution = await db_session.scalar(
        select(ReferralAttribution).where(
            ReferralAttribution.organization_id == default_org.id,
            ReferralAttribution.session_id == "session-1",
        )
    )
    assert attribution is not None
    assert attribution.referral_code_id == first.record.id


@pytest.mark.asyncio
async def test_partner_conversion_is_single_manual_held_commission(
    db_session: AsyncSession, default_org
):
    partner = ReferralPartner(
        organization_id=default_org.id,
        display_name="Approved Partner",
        status="approved",
        commission_rate=Decimal("0.20"),
    )
    db_session.add(partner)
    await db_session.commit()
    service = ReferralService(db_session)
    issued = await service.issue_code(
        organization_id=default_org.id,
        issuer_user_id=uuid4(),
        source_type="approved_partner",
        source_id=partner.id,
        redirect_path="/store",
    )
    await service.resolve_code(
        code=issued.code,
        organization_id=default_org.id,
        session_id="partner-session",
    )

    order = FunnelOrder(
        organization_id=default_org.id,
        status="paid",
        subtotal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        currency="THB",
        paid_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.commit()

    conversion = await service.record_conversion(
        organization_id=default_org.id,
        code_id=issued.record.id,
        session_id="partner-session",
        conversion_key="verified-order-1",
        verified_order_id=order.id,
        verified_amount=Decimal("100.00"),
    )
    assert conversion.reward_type == "partner_commission"
    assert conversion.commission_amount == Decimal("20.00")
    assert conversion.settlement_status == "manual_pending"
    hold_until = conversion.hold_until.replace(tzinfo=UTC)
    assert hold_until >= datetime.now(UTC) + timedelta(days=13)

    with pytest.raises(ReferralEligibilityError):
        await service.record_conversion(
            organization_id=default_org.id,
            code_id=issued.record.id,
            session_id="partner-session",
            conversion_key="verified-order-2",
            verified_order_id=order.id,
            verified_amount=Decimal("100.00"),
        )

    rows = (
        await db_session.execute(
            select(ReferralConversion).where(
                ReferralConversion.referral_code_id == issued.record.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_referral_analytics_is_tenant_scoped(db_session: AsyncSession, default_org):
    partner = ReferralPartner(
        organization_id=default_org.id,
        display_name="Analytics Partner",
        status="approved",
    )
    other_org_id = uuid4()
    db_session.add(partner)
    await db_session.commit()
    service = ReferralService(db_session)
    await service.issue_code(
        organization_id=default_org.id,
        issuer_user_id=uuid4(),
        source_type="approved_partner",
        source_id=partner.id,
        redirect_path="/store",
    )

    rows = await service.analytics(default_org.id)
    assert len(rows) == 1
    assert rows[0]["source_type"] == "approved_partner"
    assert await service.analytics(other_org_id) == []
