"""MCP funnel read tools — product, order, analytics queries (read-only)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPAuthContext
from app.mcp.auth import validate_org_context, safe_org_not_found
from app.models.funnel import (
    DigitalProduct,
    DeliveryAsset,
    FunnelOrder,
    FunnelOrderItem,
    DeliveryAccess,
    ConversionEvent,
    LeadMagnet,
    LeadCapture,
    FunnelRecommendation,
)
from app.models.approval_request import ApprovalRequest
from app.models.opportunity import Opportunity
from app.models.outcome_pattern import OutcomePattern


async def _get_db() -> AsyncSession:
    """Get a database session."""
    return AsyncSessionLocal()


TOOL_INPUT_ORG = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_INPUT_ORG_PRODUCT = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
        "product_id": {"type": "string", "description": "UUID of the product"},
    },
    "required": ["organization_id", "product_id"],
    "additionalProperties": False,
}

TOOL_INPUT_ORG_LIMIT = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
        "limit": {"type": "integer", "description": "Max results", "default": 20},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_INPUT_ORG_LIMIT_THRESHOLD = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
        "limit": {"type": "integer", "description": "Max results", "default": 15},
        "threshold": {"type": "number", "description": "Minimum total score", "default": 7.0},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_OUTPUT_LIST = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object"}},
        "total": {"type": "integer"},
    },
    "additionalProperties": False,
}

TOOL_OUTPUT_OUTCOME_SUMMARY = {
    "type": "object",
    "properties": {
        "total_patterns": {"type": "integer"},
        "positive_count": {"type": "integer"},
        "negative_count": {"type": "integer"},
        "neutral_count": {"type": "integer"},
        "avg_actual_value_thb": {"type": "string"},
        "top_lost_reasons": {"type": "array", "items": {"type": "object"}},
        "recent_patterns": {"type": "array", "items": {"type": "object"}},
    },
    "additionalProperties": False,
}


# ── Product Tools ────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="list_products",
    description="List all digital products for an organization.",
    input_schema=TOOL_INPUT_ORG_LIMIT,
    output_schema=TOOL_OUTPUT_LIST,
    risk_level="READ_ONLY",
)
async def handle_list_products(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 20,
) -> MCPResponse:
    """List digital products."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        stmt = (
            select(DigitalProduct)
            .where(DigitalProduct.organization_id == org_uuid, DigitalProduct.is_deleted == False)
            .order_by(DigitalProduct.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        products = result.scalars().all()

        return MCPResponse.ok_response(
            data={
                "items": [
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "slug": p.slug,
                        "status": p.status,
                        "price_amount": str(p.price_amount),
                        "currency": p.currency,
                        "product_type": p.product_type,
                        "published_at": p.published_at.isoformat() if p.published_at else None,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in products
                ],
                "total": len(products),
            },
            organization_id=organization_id,
            estimated_tokens=max(30, len(products) * 10),
        )


@mcp_registry.register(
    name="get_product",
    description="Get a single digital product by ID.",
    input_schema=TOOL_INPUT_ORG_PRODUCT,
    output_schema={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "slug": {"type": "string"},
            "status": {"type": "string"},
            "description": {"type": "string"},
            "price_amount": {"type": "string"},
            "currency": {"type": "string"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_product(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    product_id: str = "",
) -> MCPResponse:
    """Get a single product."""
    try:
        org_uuid = UUID(organization_id)
        prod_uuid = UUID(product_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id or product_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        product = await db.get(DigitalProduct, prod_uuid)
        if product is None or product.organization_id != org_uuid:
            return MCPResponse.error_response(
                code="NOT_FOUND",
                message="Product not found.",
                request_id=auth.request_id if auth else "",
                organization_id=organization_id,
            )

        return MCPResponse.ok_response(
            data={
                "id": str(product.id),
                "name": product.name,
                "slug": product.slug,
                "status": product.status,
                "description": product.description,
                "short_description": product.short_description,
                "price_amount": str(product.price_amount),
                "currency": product.currency,
                "product_type": product.product_type,
                "published_at": product.published_at.isoformat() if product.published_at else None,
                "created_at": product.created_at.isoformat() if product.created_at else None,
            },
            organization_id=organization_id,
            estimated_tokens=80,
        )


# ── Delivery Asset Tools ──────────────────────────────────────────────────────


@mcp_registry.register(
    name="list_delivery_assets",
    description="List all delivery assets for an organization.",
    input_schema=TOOL_INPUT_ORG_LIMIT,
    output_schema=TOOL_OUTPUT_LIST,
    risk_level="READ_ONLY",
)
async def handle_list_delivery_assets(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 20,
) -> MCPResponse:
    """List delivery assets."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        stmt = (
            select(DeliveryAsset)
            .where(DeliveryAsset.organization_id == org_uuid)
            .order_by(DeliveryAsset.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        assets = result.scalars().all()

        return MCPResponse.ok_response(
            data={
                "items": [
                    {
                        "id": str(a.id),
                        "product_id": str(a.product_id),
                        "asset_type": a.asset_type,
                        "title": a.title,
                        "is_active": a.is_active,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in assets
                ],
                "total": len(assets),
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(assets) * 8),
        )


# ── Order Tools ────────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="get_orders_summary",
    description="Get a summary of orders for an organization.",
    input_schema=TOOL_INPUT_ORG,
    output_schema={
        "type": "object",
        "properties": {
            "total_orders": {"type": "integer"},
            "paid_orders": {"type": "integer"},
            "total_revenue": {"type": "string"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_orders_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get orders summary."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        total = await db.scalar(
            select(func.count(FunnelOrder.id)).where(FunnelOrder.organization_id == org_uuid)
        ) or 0
        paid = await db.scalar(
            select(func.count(FunnelOrder.id)).where(
                FunnelOrder.organization_id == org_uuid,
                FunnelOrder.status == "paid",
            )
        ) or 0
        revenue = await db.scalar(
            select(func.coalesce(func.sum(FunnelOrder.total_amount), 0)).where(
                FunnelOrder.organization_id == org_uuid,
                FunnelOrder.status == "paid",
            )
        ) or 0

        return MCPResponse.ok_response(
            data={
                "total_orders": int(total),
                "paid_orders": int(paid),
                "total_revenue": str(revenue),
            },
            organization_id=organization_id,
            estimated_tokens=20,
        )


@mcp_registry.register(
    name="get_recent_orders",
    description="Get recent orders for an organization.",
    input_schema=TOOL_INPUT_ORG_LIMIT,
    output_schema=TOOL_OUTPUT_LIST,
    risk_level="READ_ONLY",
)
async def handle_get_recent_orders(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 10,
) -> MCPResponse:
    """Get recent orders."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        stmt = (
            select(FunnelOrder)
            .where(FunnelOrder.organization_id == org_uuid)
            .order_by(FunnelOrder.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        orders = result.scalars().all()

        return MCPResponse.ok_response(
            data={
                "items": [
                    {
                        "id": str(o.id),
                        "status": o.status,
                        "total_amount": str(o.total_amount),
                        "currency": o.currency,
                        "customer_email_preview": (o.customer_email or "")[:20],
                        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                        "created_at": o.created_at.isoformat() if o.created_at else None,
                    }
                    for o in orders
                ],
                "total": len(orders),
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(orders) * 10),
        )


# ── Revenue / Analytics Tools ────────────────────────────────────────────────────


@mcp_registry.register(
    name="get_revenue_summary",
    description="Get revenue summary for an organization.",
    input_schema=TOOL_INPUT_ORG,
    output_schema={
        "type": "object",
        "properties": {
            "total_revenue": {"type": "string"},
            "paid_orders": {"type": "integer"},
            "currency": {"type": "string"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_revenue_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get revenue summary."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        revenue = await db.scalar(
            select(func.coalesce(func.sum(FunnelOrder.total_amount), 0)).where(
                FunnelOrder.organization_id == org_uuid,
                FunnelOrder.status == "paid",
            )
        ) or 0
        paid = await db.scalar(
            select(func.count(FunnelOrder.id)).where(
                FunnelOrder.organization_id == org_uuid,
                FunnelOrder.status == "paid",
            )
        ) or 0

        return MCPResponse.ok_response(
            data={
                "total_revenue": str(revenue),
                "paid_orders": int(paid),
                "currency": "THB",
            },
            organization_id=organization_id,
            estimated_tokens=20,
        )


@mcp_registry.register(
    name="get_high_score_opportunities",
    description="List the highest-scoring opportunities for an organization. Surfaces top candidates only, never mutates state.",
    input_schema=TOOL_INPUT_ORG_LIMIT_THRESHOLD,
    output_schema=TOOL_OUTPUT_LIST,
    risk_level="READ_ONLY",
)
async def handle_get_high_score_opportunities(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 15,
    threshold: float = 7.0,
) -> MCPResponse:
    """Return top-scoring opportunities for revenue-ops review."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    safe_limit = min(max(limit, 1), 25)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(Opportunity)
            .where(
                Opportunity.organization_id == org_uuid,
                Opportunity.is_deleted.is_(False),
                Opportunity.total_score.is_not(None),
                Opportunity.total_score >= threshold,
            )
            .order_by(Opportunity.total_score.desc(), Opportunity.found_at.desc())
            .limit(safe_limit)
        )
        result = await db.execute(stmt)
        opportunities = result.scalars().all()

        return MCPResponse.ok_response(
            data={
                "items": [
                    {
                        "id": str(item.id),
                        "title": item.title,
                        "type": item.type,
                        "total_score": str(item.total_score) if item.total_score is not None else None,
                        "status": item.status,
                        "decision": item.decision,
                        "action_priority": item.action_priority,
                        "source_platform": item.source_platform,
                        "found_at": item.found_at.isoformat() if item.found_at else None,
                    }
                    for item in opportunities
                ],
                "total": len(opportunities),
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(opportunities) * 18),
        )


@mcp_registry.register(
    name="get_outcome_patterns_summary",
    description="Summarize historical outcome patterns for an organization. Supports failure analysis and experiment planning without exposing raw secrets.",
    input_schema=TOOL_INPUT_ORG_LIMIT,
    output_schema=TOOL_OUTPUT_OUTCOME_SUMMARY,
    risk_level="READ_ONLY",
)
async def handle_get_outcome_patterns_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 10,
) -> MCPResponse:
    """Return recent outcome-pattern summaries scoped through organization opportunities."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    safe_limit = min(max(limit, 1), 25)

    async with AsyncSessionLocal() as db:
        recent_stmt = (
            select(OutcomePattern, Opportunity)
            .join(Opportunity, Opportunity.id == OutcomePattern.opportunity_id)
            .where(
                Opportunity.organization_id == org_uuid,
                Opportunity.is_deleted.is_(False),
            )
            .order_by(OutcomePattern.created_at.desc())
            .limit(safe_limit)
        )
        recent_rows = (await db.execute(recent_stmt)).all()

        counts_stmt = (
            select(OutcomePattern.outcome, func.count(OutcomePattern.id))
            .join(Opportunity, Opportunity.id == OutcomePattern.opportunity_id)
            .where(
                Opportunity.organization_id == org_uuid,
                Opportunity.is_deleted.is_(False),
            )
            .group_by(OutcomePattern.outcome)
        )
        counts_rows = (await db.execute(counts_stmt)).all()
        counts = {str(outcome or "unknown"): int(count) for outcome, count in counts_rows}

        avg_value = await db.scalar(
            select(func.coalesce(func.avg(OutcomePattern.actual_value_thb), 0))
            .join(Opportunity, Opportunity.id == OutcomePattern.opportunity_id)
            .where(
                Opportunity.organization_id == org_uuid,
                Opportunity.is_deleted.is_(False),
            )
        ) or 0

        lost_stmt = (
            select(OutcomePattern.lost_reason, func.count(OutcomePattern.id))
            .join(Opportunity, Opportunity.id == OutcomePattern.opportunity_id)
            .where(
                Opportunity.organization_id == org_uuid,
                Opportunity.is_deleted.is_(False),
                OutcomePattern.lost_reason.is_not(None),
                OutcomePattern.lost_reason != "",
            )
            .group_by(OutcomePattern.lost_reason)
            .order_by(func.count(OutcomePattern.id).desc(), OutcomePattern.lost_reason.asc())
            .limit(5)
        )
        lost_rows = (await db.execute(lost_stmt)).all()

        return MCPResponse.ok_response(
            data={
                "total_patterns": sum(counts.values()),
                "positive_count": counts.get("positive", 0),
                "negative_count": counts.get("negative", 0),
                "neutral_count": counts.get("neutral", 0),
                "avg_actual_value_thb": str(avg_value),
                "top_lost_reasons": [
                    {"reason": str(reason), "count": int(count)}
                    for reason, count in lost_rows
                ],
                "recent_patterns": [
                    {
                        "id": str(pattern.id),
                        "opportunity_id": str(pattern.opportunity_id) if pattern.opportunity_id else None,
                        "opportunity_title": opportunity.title,
                        "opportunity_type": pattern.opportunity_type,
                        "outcome": pattern.outcome,
                        "lost_reason": pattern.lost_reason,
                        "actual_value_thb": str(pattern.actual_value_thb or 0),
                        "total_score": str(pattern.total_score) if pattern.total_score is not None else None,
                        "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
                    }
                    for pattern, opportunity in recent_rows
                ],
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(recent_rows) * 20),
        )


@mcp_registry.register(
    name="get_conversion_summary",
    description="Get conversion summary for an organization — views, checkouts, purchases, conversion rate.",
    input_schema=TOOL_INPUT_ORG,
    output_schema={
        "type": "object",
        "properties": {
            "total_views": {"type": "integer"},
            "total_checkouts": {"type": "integer"},
            "total_purchases": {"type": "integer"},
            "conversion_rate": {"type": "number"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_conversion_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get conversion summary."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        views = await db.scalar(
            select(func.count(ConversionEvent.id)).where(
                ConversionEvent.organization_id == org_uuid,
                ConversionEvent.event_type == "page_view",
            )
        ) or 0
        checkouts = await db.scalar(
            select(func.count(ConversionEvent.id)).where(
                ConversionEvent.organization_id == org_uuid,
                ConversionEvent.event_type == "checkout_start",
            )
        ) or 0
        purchases = await db.scalar(
            select(func.count(ConversionEvent.id)).where(
                ConversionEvent.organization_id == org_uuid,
                ConversionEvent.event_type == "purchase",
            )
        ) or 0

        rate = round(purchases / views * 100, 2) if views > 0 else 0.0

        return MCPResponse.ok_response(
            data={
                "total_views": int(views),
                "total_checkouts": int(checkouts),
                "total_purchases": int(purchases),
                "conversion_rate": rate,
            },
            organization_id=organization_id,
            estimated_tokens=20,
        )


@mcp_registry.register(
    name="get_checkout_abandonment",
    description="Get checkout abandonment rate for an organization.",
    input_schema=TOOL_INPUT_ORG,
    output_schema={
        "type": "object",
        "properties": {
            "checkout_abandonment_rate": {"type": "number"},
            "total_checkouts": {"type": "integer"},
            "total_purchases": {"type": "integer"},
            "abandoned": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_checkout_abandonment(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get checkout abandonment rate."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        checkouts = await db.scalar(
            select(func.count(ConversionEvent.id)).where(
                ConversionEvent.organization_id == org_uuid,
                ConversionEvent.event_type == "checkout_start",
            )
        ) or 0
        purchases = await db.scalar(
            select(func.count(ConversionEvent.id)).where(
                ConversionEvent.organization_id == org_uuid,
                ConversionEvent.event_type == "purchase",
            )
        ) or 0

        abandoned = checkouts - purchases
        rate = round(abandoned / checkouts * 100, 2) if checkouts > 0 else 0.0

        return MCPResponse.ok_response(
            data={
                "checkout_abandonment_rate": rate,
                "total_checkouts": int(checkouts),
                "total_purchases": int(purchases),
                "abandoned": int(max(abandoned, 0)),
            },
            organization_id=organization_id,
            estimated_tokens=20,
        )


@mcp_registry.register(
    name="get_delivery_open_rate",
    description="Get delivery open rate for an organization.",
    input_schema=TOOL_INPUT_ORG,
    output_schema={
        "type": "object",
        "properties": {
            "total_deliveries": {"type": "integer"},
            "opened_deliveries": {"type": "integer"},
            "delivery_open_rate": {"type": "number"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_delivery_open_rate(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get delivery open rate."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        total = await db.scalar(
            select(func.count(DeliveryAccess.id)).where(DeliveryAccess.organization_id == org_uuid)
        ) or 0
        opened = await db.scalar(
            select(func.count(DeliveryAccess.id)).where(
                DeliveryAccess.organization_id == org_uuid,
                DeliveryAccess.first_opened_at.is_not(None),
            )
        ) or 0

        rate = round(opened / total * 100, 2) if total > 0 else 0.0

        return MCPResponse.ok_response(
            data={
                "total_deliveries": int(total),
                "opened_deliveries": int(opened),
                "delivery_open_rate": rate,
            },
            organization_id=organization_id,
            estimated_tokens=20,
        )


TOOL_INPUT_STATUS = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
        "status": {"type": "string", "description": "Filter by status (pending, approved, rejected)", "default": "pending"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_pending_approvals",
    description="Get pending approvals for an organization.",
    input_schema=TOOL_INPUT_STATUS,
    output_schema=TOOL_OUTPUT_LIST,
    risk_level="READ_ONLY",
)
async def handle_get_pending_approvals(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    status: str = "pending",
) -> MCPResponse:
    """Get pending approvals."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=auth.request_id if auth else "",
        )

    if not validate_org_context(auth, org_uuid):
        safe_org_not_found()

    async with AsyncSessionLocal() as db:
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.organization_id == org_uuid,
                ApprovalRequest.status == status,
            )
            .order_by(ApprovalRequest.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        approvals = result.scalars().all()

        return MCPResponse.ok_response(
            data={
                "items": [
                    {
                        "id": str(a.id),
                        "title": a.title[:100] if a.title else "",
                        "action_type": a.action_type,
                        "status": a.status,
                        "policy_class": a.policy_class,
                        "preview_summary": (a.preview or {}).get("summary", "")[:100] if a.preview else "",
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in approvals
                ],
                "total": len(approvals),
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(approvals) * 15),
        )
