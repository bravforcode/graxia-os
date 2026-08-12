"""Funnel API routes — delivery, analytics, lead magnets, recommendations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, LocalDevAuthContext
from app.auth.dependencies import get_auth_context
from app.database import get_db
from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DeliveryAsset,
    DigitalProduct,
    FunnelOrder,
    FunnelOrderItem,
    FunnelRecommendation,
    LeadCapture,
    LeadMagnet,
)
from app.schemas.funnel import (
    ConversionEventCreate,
    ConversionEventRead,
    DeliveryAccessPublic,
    DeliveryAccessRead,
    DeliveryEmailEventCreate,
    DeliveryEmailEventRead,
    FunnelAnalyticsSummary,
    FunnelOrderRead,
    FunnelOrderItemRead,
    FunnelRecommendationCreate,
    FunnelRecommendationRead,
    LeadCaptureCreate,
    LeadCaptureRead,
    LeadMagnetCreate,
    LeadMagnetPublic,
    LeadMagnetRead,
    LeadMagnetUpdate,
)
from app.models.approval_request import ApprovalRequest
from app.services.funnel_service import (
    delivery_access_service,
    funnel_analytics_service,
    funnel_recommendation_service,
    funnel_webhook_handler,
    lead_magnet_service,
    mock_email_provider,
)
from app.runtime.events import business_event_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/funnel", tags=["funnel"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ═══════════════════════════════════════════════════════════════════════════════
# DELIVERY ACCESS API
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/orders/{order_id}/delivery-access", response_model=dict)
async def grant_delivery_access(
    order_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Grant delivery access for an order. Creates access record and mock email."""
    org_id = organization_id or auth.organization_id

    # Verify order exists
    order = await db.get(FunnelOrder, order_id)
    if order is None or order.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get product from order items
    items = await db.execute(
        select(FunnelOrderItem).where(
            FunnelOrderItem.order_id == order_id,
            FunnelOrderItem.organization_id == org_id,
        )
    )
    order_items = list(items.scalars().all())
    if not order_items:
        raise HTTPException(status_code=400, detail="Order has no items")

    product_id = order_items[0].product_id

    # Grant access
    access, raw_token = await delivery_access_service.grant_access(
        organization_id=org_id,
        order_id=order_id,
        product_id=product_id,
        db=db,
    )

    # Send mock email
    product = await db.get(DigitalProduct, product_id)
    product_name = product.name if product else "Digital Product"
    idempotency_key = f"delivery_email:{order_id}:{product_id}:admin"

    await mock_email_provider.send_delivery_email(
        customer_email=order.customer_email or "customer@test.com",
        delivery_token=raw_token,
        product_name=product_name,
        organization_id=org_id,
        order_id=order_id,
        delivery_access_id=access.id,
        idempotency_key=idempotency_key,
        db=db,
    )

    return {
        "access_id": str(access.id),
        "token_preview": raw_token[:16] + "...",
        "product_name": product_name,
    }


@router.get("/delivery-access/{access_id}", response_model=DeliveryAccessRead)
async def get_delivery_access(
    access_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get delivery access details (admin)."""
    org_id = organization_id or auth.organization_id
    access = await delivery_access_service.get_access_by_id(access_id, org_id, db=db)
    if access is None:
        raise HTTPException(status_code=404, detail="Delivery access not found")
    return access


@router.post("/delivery-access/{access_id}/revoke", response_model=dict)
async def revoke_delivery_access(
    access_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Revoke delivery access."""
    org_id = organization_id or auth.organization_id
    access = await delivery_access_service.revoke_access(access_id, org_id, db=db)
    if access is None:
        raise HTTPException(status_code=404, detail="Delivery access not found")
    return {"status": "revoked", "access_id": str(access_id)}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC DELIVERY ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/delivery/{access_token}", response_model=DeliveryAccessPublic)
async def open_delivery(
    access_token: str,
    db: DbSession = None,
):
    """Public endpoint: open a delivery using the access token."""
    access = await delivery_access_service.verify_access(access_token, db=db)
    if access is None:
        raise HTTPException(status_code=404, detail="Delivery not found or expired")

    # Record the open
    access = await delivery_access_service.record_open(access.id, db=db)

    # Track conversion event
    event = ConversionEvent(
        id=uuid4(),
        organization_id=access.organization_id,
        event_type="delivery_opened",
        product_id=access.product_id,
        order_id=access.order_id,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()

    # Safe public response
    product = await db.get(DigitalProduct, access.product_id)
    asset = None
    if access.delivery_asset_id:
        asset = await db.get(DeliveryAsset, access.delivery_asset_id)

    return DeliveryAccessPublic(
        product_name=product.name if product else "Digital Product",
        asset_title=asset.title if asset else None,
        status=access.status,
        is_opened=access.first_opened_at is not None,
        opened_at=access.first_opened_at,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WEBHOOK SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/webhook/checkout-completed", response_model=dict)
async def simulate_checkout_webhook(
    checkout_session_id: UUID,
    customer_email: str,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Simulate a Stripe checkout.completed webhook.

    Creates order, order items, delivery access, and mock email.
    Idempotent — re-running with same checkout_session_id returns existing order.
    """
    org_id = organization_id or auth.organization_id
    try:
        result = await funnel_webhook_handler.handle_checkout_completed(
            organization_id=org_id,
            checkout_session_id=checkout_session_id,
            customer_email=customer_email,
            db=db,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS API
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/analytics/summary", response_model=FunnelAnalyticsSummary)
async def get_analytics_summary(
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get overall funnel analytics summary."""
    org_id = organization_id or auth.organization_id
    data = await funnel_analytics_service.get_summary(org_id, db=db)
    return FunnelAnalyticsSummary(**data)


@router.get("/products/{product_id}/analytics", response_model=dict)
async def get_product_analytics(
    product_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get analytics for a specific product."""
    org_id = organization_id or auth.organization_id
    data = await funnel_analytics_service.get_product_analytics(product_id, org_id, db=db)
    if not data:
        raise HTTPException(status_code=404, detail="Product not found")
    return data


@router.get("/products/{product_id}/conversion", response_model=dict)
async def get_product_conversion(
    product_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get conversion metrics for a specific product."""
    org_id = organization_id or auth.organization_id
    data = await funnel_analytics_service.get_product_analytics(product_id, org_id, db=db)
    if not data:
        raise HTTPException(status_code=404, detail="Product not found")
    views = data.get("total_views", 0)
    checkouts = data.get("total_checkouts", 0)
    purchases = data.get("total_purchases", 0)
    rate = data.get("conversion_rate", 0.0)
    return {
        "product_id": str(product_id),
        "total_views": views,
        "total_checkouts": checkouts,
        "total_purchases": purchases,
        "checkout_conversion_rate": round((checkouts / views * 100) if views > 0 else 0, 2),
        "purchase_conversion_rate": rate,
    }


@router.get("/products/{product_id}/delivery-open-rate", response_model=dict)
async def get_product_delivery_open_rate(
    product_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get delivery open rate for a specific product."""
    org_id = organization_id or auth.organization_id
    data = await funnel_analytics_service.get_product_analytics(product_id, org_id, db=db)
    if not data:
        raise HTTPException(status_code=404, detail="Product not found")
    return {
        "product_id": str(product_id),
        "delivery_opens": data.get("delivery_opens", 0),
        "total_orders": data.get("total_orders", 0),
        "delivery_open_rate": round(
            (data.get("delivery_opens", 0) / data.get("total_orders", 1) * 100)
            if data.get("total_orders", 0) > 0 else 0, 2
        ),
    }


@router.post("/events/product-view", response_model=dict)
async def track_product_view(
    product_id: UUID,
    session_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Track a product view event."""
    org_id = organization_id or auth.organization_id
    event = ConversionEvent(
        id=uuid4(),
        organization_id=org_id,
        event_type="page_view",
        product_id=product_id,
        session_id=session_id,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    return {"status": "tracked", "event_type": "page_view"}


@router.post("/events/delivery-opened", response_model=dict)
async def track_delivery_opened(
    access_token: str,
    db: DbSession = None,
):
    """Track a delivery opened event externally."""
    access = await delivery_access_service.verify_access(access_token, db=db)
    if access is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    access = await delivery_access_service.record_open(access.id, db=db)
    return {"status": "tracked", "access_id": str(access.id)}


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD MAGNET API
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/lead-magnets/{slug}", response_model=LeadMagnetPublic)
async def get_lead_magnet_public(
    slug: str,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Public: get lead magnet by slug."""
    org_id = organization_id or auth.organization_id
    magnet = await lead_magnet_service.get_by_slug(slug, org_id, db=db)
    if magnet is None:
        raise HTTPException(status_code=404, detail="Lead magnet not found")
    return LeadMagnetPublic(slug=magnet.slug, title=magnet.title, description=magnet.description)


@router.post("/lead-magnets/{slug}/capture", response_model=dict)
async def capture_lead(
    slug: str,
    email: str,
    source: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Public: capture a lead from a lead magnet."""
    org_id = organization_id or auth.organization_id
    magnet = await lead_magnet_service.get_by_slug(slug, org_id, db=db)
    if magnet is None:
        raise HTTPException(status_code=404, detail="Lead magnet not found")

    capture = await lead_magnet_service.capture(
        lead_magnet_id=magnet.id,
        organization_id=org_id,
        email=email,
        source=source,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        db=db,
    )

    # Track lead capture event
    event = ConversionEvent(
        id=uuid4(),
        organization_id=org_id,
        event_type="lead_capture",
        product_id=magnet.product_id,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()

    return {"status": "captured", "duplicate": capture is None}


@router.post("/lead-magnets/{slug}/deliver", response_model=dict)
async def deliver_lead_magnet_asset(
    slug: str,
    email: str,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Mock delivery of a free lead magnet asset after capture."""
    org_id = organization_id or auth.organization_id
    magnet = await lead_magnet_service.get_by_slug(slug, org_id, db=db)
    if magnet is None:
        raise HTTPException(status_code=404, detail="Lead magnet not found")

    # Ensure lead is captured
    await lead_magnet_service.capture(
        lead_magnet_id=magnet.id,
        organization_id=org_id,
        email=email,
        source="delivery",
        db=db,
    )

    # Get asset info if linked
    asset_title = None
    delivery_url = None
    if magnet.asset_id:
        asset = await db.get(DeliveryAsset, magnet.asset_id)
        if asset:
            asset_title = asset.title
            delivery_url = asset.external_url or f"/assets/{asset.id}"

    return {
        "status": "delivered",
        "email": email,
        "asset_title": asset_title or magnet.title,
        "delivery_url": delivery_url or "/delivery/free-asset",
        "simulated": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION API
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/products/{product_id}/recommendations", response_model=FunnelRecommendationRead)
async def create_recommendation(
    product_id: UUID,
    rec_data: FunnelRecommendationCreate,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Create a recommendation for a product."""
    org_id = organization_id or auth.organization_id
    rec = await funnel_recommendation_service.create(
        organization_id=org_id,
        product_id=product_id,
        recommendation_type=rec_data.recommendation_type,
        recommended_action=rec_data.recommended_action,
        bottleneck=rec_data.bottleneck,
        expected_impact=rec_data.expected_impact,
        confidence=rec_data.confidence,
        effort=rec_data.effort,
        risk=rec_data.risk,
        reasoning=rec_data.reasoning,
        draft_content=rec_data.draft_content,
        metadata_json=rec_data.metadata_json,
        db=db,
    )
    # Map to read schema
    return FunnelRecommendationRead(
        id=rec.id,
        product_id=rec.product_id,
        organization_id=rec.organization_id,
        recommendation_type=rec.recommendation_type,
        bottleneck=rec.bottleneck,
        recommended_action=rec.recommended_action,
        expected_impact=rec.expected_impact,
        confidence=rec.confidence,
        effort=rec.effort,
        risk=rec.risk,
        reasoning=rec.reasoning,
        draft_content=rec.draft_content,
        rollback_note=rec.rollback_note,
        approval_request_id=rec.approval_request_id,
        status=rec.status,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


@router.get("/recommendations", response_model=list[FunnelRecommendationRead])
async def list_recommendations(
    product_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """List funnel recommendations."""
    org_id = organization_id or auth.organization_id
    recs = await funnel_recommendation_service.list(
        organization_id=org_id,
        product_id=product_id,
        status=status,
        limit=limit,
        db=db,
    )
    return [
        FunnelRecommendationRead(
            id=r.id,
            product_id=r.product_id,
            organization_id=r.organization_id,
            recommendation_type=r.recommendation_type,
            bottleneck=r.bottleneck,
            recommended_action=r.recommended_action,
            expected_impact=r.expected_impact,
            confidence=r.confidence,
            effort=r.effort,
            risk=r.risk,
            reasoning=r.reasoning,
            draft_content=r.draft_content,
            rollback_note=r.rollback_note,
            approval_request_id=r.approval_request_id,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in recs
    ]


@router.get("/recommendations/{rec_id}", response_model=FunnelRecommendationRead)
async def get_recommendation(
    rec_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Get a single recommendation."""
    org_id = organization_id or auth.organization_id
    rec = await funnel_recommendation_service.get(rec_id, org_id, db=db)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return FunnelRecommendationRead(
        id=rec.id,
        product_id=rec.product_id,
        organization_id=rec.organization_id,
        recommendation_type=rec.recommendation_type,
        bottleneck=rec.bottleneck,
        recommended_action=rec.recommended_action,
        expected_impact=rec.expected_impact,
        confidence=rec.confidence,
        effort=rec.effort,
        risk=rec.risk,
        reasoning=rec.reasoning,
        draft_content=rec.draft_content,
        rollback_note=rec.rollback_note,
        approval_request_id=rec.approval_request_id,
        status=rec.status,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


@router.post("/recommendations/{rec_id}/submit-for-approval", response_model=dict)
async def submit_recommendation_for_approval(
    rec_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    organization_id: UUID | None = None,
    db: DbSession = None,
):
    """Submit a recommendation for human approval.
    Creates an ApprovalRequest linked to the recommendation.
    """
    org_id = organization_id or auth.organization_id
    rec = await funnel_recommendation_service.get(rec_id, org_id, db=db)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Create approval request
    from app.auth.context import LOCAL_DEV_ORGANIZATION_ID
    approval = ApprovalRequest(
        id=uuid4(),
        organization_id=org_id,
        title=f"Recommendation: {rec.recommendation_type} - {rec.recommended_action[:100]}",
        action_type="funnel_recommendation",
        subject_type="funnel_recommendation",
        subject_id=rec.id,
        status="pending",
        policy_class="recommendation_approval",
        requested_by="funnel_system",
        details={
            "recommendation_id": str(rec.id),
            "recommendation_type": rec.recommendation_type,
            "recommended_action": rec.recommended_action,
            "bottleneck": rec.bottleneck,
            "expected_impact": rec.expected_impact,
            "confidence": rec.confidence,
            "effort": rec.effort,
            "risk": rec.risk,
            "reasoning": rec.reasoning,
        },
        preview={
            "summary": f"{rec.recommendation_type}: {rec.recommended_action[:200]}",
            "impact": rec.expected_impact,
            "confidence": rec.confidence,
        },
    )
    db.add(approval)
    await db.flush()

    # Update recommendation status
    rec.status = "pending_approval"
    rec.approval_request_id = approval.id
    await db.commit()

    await business_event_service.emit(
        organization_id=str(org_id),
        event_type="approval.requested",
        subject_type="approval_request",
        subject_id=str(approval.id),
        payload={
            "action_type": approval.action_type,
            "recommendation_id": str(rec.id),
            "policy_class": approval.policy_class,
        },
        actor_type=auth.actor_type,
        actor_id=auth.actor_id,
        source="funnel-api",
        risk_level="APPROVAL_REQUIRED",
        correlation_id=f"approval-request:{approval.id}",
        idempotency_key=f"approval-request:{approval.id}",
    )

    return {
        "status": "submitted",
        "recommendation_id": str(rec.id),
        "approval_request_id": str(approval.id),
    }
