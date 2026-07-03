"""MCP approval-gated write tools — every action creates an ApprovalRequest instead of executing.

These tools NEVER execute the requested action. They create an ApprovalRequest
with status="pending" and return the approval_request_id for human review.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.database import AsyncSessionLocal
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPAuthContext, MCPResponseMeta, MCPError
from app.mcp.auth import validate_org_context, safe_org_not_found
from app.mcp.audit import log_mcp_tool_call
from app.models.approval_request import ApprovalRequest

logger = logging.getLogger(__name__)

TOOL_INPUT_BASE = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_OUTPUT_APPROVAL = {
    "type": "object",
    "properties": {
        "approval_required": {"type": "boolean"},
        "approval_request_id": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["approval_required", "approval_request_id"],
    "additionalProperties": False,
}

async def _create_approval_request(
    organization_id: UUID,
    action_type: str,
    title: str,
    subject_type: str | None,
    subject_id: UUID | None,
    details: dict | None = None,
    preview: dict | None = None,
) -> ApprovalRequest:
    """Create a pending ApprovalRequest and return it.

    Sets organization_id on the model for org-scoped queries.
    Also stores org in details dict for traceability.
    """
    safe_details = dict(details or {})
    safe_details["organization_id"] = str(organization_id)

    ar = ApprovalRequest(
        id=uuid4(),
        organization_id=organization_id,
        title=title,
        action_type=action_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status="pending",
        policy_class="mcp_write_tool",
        requested_by="mcp_system",
        details=safe_details,
        preview=preview or {},
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    async with AsyncSessionLocal() as db:
        db.add(ar)
        await db.commit()
        await db.refresh(ar)
    return ar


def _approval_response(ar: ApprovalRequest, org_id: str, request_id: str) -> MCPResponse:
    """Build a standard approval-required response."""
    meta = MCPResponseMeta(
        request_id=request_id,
        organization_id=org_id,
    )
    return MCPResponse(
        ok=False,
        data={
            "approval_required": True,
            "approval_request_id": str(ar.id),
            "message": "This action requires human approval. An ApprovalRequest has been created.",
        },
        error=MCPError(
            code="APPROVAL_REQUIRED",
            message="This action requires human approval.",
        ),
        meta=meta,
    )


async def _validate_org(auth: MCPAuthContext | None, org_id_str: str, request_id: str) -> tuple[UUID | None, MCPResponse | None]:
    """Validate organization_id. Returns (org_uuid, None) on success, (None, error_response) on failure."""
    try:
        org_uuid = UUID(org_id_str)
    except (ValueError, TypeError):
        return None, MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid organization_id.",
            request_id=request_id,
        )
    if not validate_org_context(auth, org_uuid):
        try:
            safe_org_not_found()
        except PermissionError:
            return None, MCPResponse.error_response(
                code="PERMISSION_DENIED",
                message="Resource not found.",
                request_id=request_id,
                organization_id=org_id_str,
            )
    return org_uuid, None


# ── Product Write Tools ──────────────────────────────────────────────────────


@mcp_registry.register(
    name="publish_product_update",
    description="Submit a product update for approval. Creates an ApprovalRequest — does NOT execute.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "product_id": {"type": "string", "description": "UUID of the product to publish"},
            "change_summary": {"type": "string", "description": "Summary of changes"},
        },
        "required": ["organization_id", "product_id", "change_summary"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_publish_product_update(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    product_id: str = "",
    change_summary: str = "",
) -> MCPResponse:
    """Submit a product update for approval. Does NOT publish — creates ApprovalRequest."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        prod_uuid = UUID(product_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS",
            message="Invalid product_id.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="publish_product_update",
        title=f"Publish product update: {change_summary[:100]}",
        subject_type="digital_product",
        subject_id=prod_uuid,
        details={"product_id": product_id, "change_summary": change_summary},
        preview={"action": "publish_update", "product_id": product_id, "change_summary": change_summary[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="publish_product_update",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
        input_summary_redacted=f"product_id={product_id}",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="archive_product",
    description="Submit a product archive request for approval. Creates an ApprovalRequest — does NOT execute.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "product_id": {"type": "string", "description": "UUID of the product to archive"},
            "reason": {"type": "string", "description": "Reason for archiving"},
        },
        "required": ["organization_id", "product_id", "reason"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_archive_product(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    product_id: str = "",
    reason: str = "",
) -> MCPResponse:
    """Submit product archive for approval."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        prod_uuid = UUID(product_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS", message="Invalid product_id.",
            request_id=auth.request_id if auth else "", organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="archive_product",
        title=f"Archive product: {reason[:100]}",
        subject_type="digital_product",
        subject_id=prod_uuid,
        details={"product_id": product_id, "reason": reason},
        preview={"action": "archive", "product_id": product_id, "reason": reason[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="archive_product",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="change_product_price",
    description="Submit a price change for approval. Creates an ApprovalRequest — does NOT execute.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "product_id": {"type": "string", "description": "UUID of the product"},
            "new_price": {"type": "string", "description": "New price amount (e.g. '499.00')"},
            "reason": {"type": "string", "description": "Reason for price change"},
        },
        "required": ["organization_id", "product_id", "new_price", "reason"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_change_product_price(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    product_id: str = "",
    new_price: str = "",
    reason: str = "",
) -> MCPResponse:
    """Submit a price change for approval. Does NOT change the price."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        prod_uuid = UUID(product_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS", message="Invalid product_id.",
            request_id=auth.request_id if auth else "", organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="change_product_price",
        title=f"Change product price to {new_price}: {reason[:100]}",
        subject_type="digital_product",
        subject_id=prod_uuid,
        details={"product_id": product_id, "new_price": new_price, "reason": reason},
        preview={"action": "change_price", "product_id": product_id, "new_price": new_price, "reason": reason[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="change_product_price",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


# ── Lead Magnet Tools ────────────────────────────────────────────────────────


@mcp_registry.register(
    name="activate_lead_magnet",
    description="Submit a lead magnet activation for approval. Creates an ApprovalRequest — does NOT execute.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "lead_magnet_slug": {"type": "string", "description": "Slug of the lead magnet to activate"},
        },
        "required": ["organization_id", "lead_magnet_slug"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_activate_lead_magnet(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    lead_magnet_slug: str = "",
) -> MCPResponse:
    """Submit lead magnet activation for approval."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="activate_lead_magnet",
        title=f"Activate lead magnet: {lead_magnet_slug}",
        subject_type="lead_magnet",
        subject_id=None,
        details={"slug": lead_magnet_slug},
        preview={"action": "activate_lead_magnet", "slug": lead_magnet_slug},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="activate_lead_magnet",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


# ── Customer Communication Tools ──────────────────────────────────────────────


@mcp_registry.register(
    name="send_customer_followup",
    description="Submit a customer follow-up for approval. Creates an ApprovalRequest — does NOT send.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "customer_email": {"type": "string", "description": "Customer email address"},
            "message_preview": {"type": "string", "description": "Preview of the follow-up message"},
        },
        "required": ["organization_id", "customer_email", "message_preview"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_send_customer_followup(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    customer_email: str = "",
    message_preview: str = "",
) -> MCPResponse:
    """Submit a customer follow-up for approval. Does NOT send."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="send_customer_followup",
        title=f"Send follow-up to {customer_email[:50]}",
        subject_type="customer_communication",
        subject_id=None,
        details={"customer_email": customer_email, "message_preview": message_preview},
        preview={"action": "send_followup", "to": customer_email[:50], "preview": message_preview[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="send_customer_followup",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="send_delivery_email_manual",
    description="Submit a manual delivery email for approval. Creates an ApprovalRequest — does NOT send.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "order_id": {"type": "string", "description": "UUID of the order"},
            "customer_email": {"type": "string", "description": "Customer email address"},
        },
        "required": ["organization_id", "order_id", "customer_email"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_send_delivery_email_manual(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    order_id: str = "",
    customer_email: str = "",
) -> MCPResponse:
    """Submit a manual delivery email for approval. Does NOT send."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        order_uuid = UUID(order_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS", message="Invalid order_id.",
            request_id=auth.request_id if auth else "", organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="send_delivery_email_manual",
        title=f"Manual delivery email to {customer_email[:50]}",
        subject_type="delivery_email",
        subject_id=order_uuid,
        details={"order_id": order_id, "customer_email": customer_email},
        preview={"action": "send_delivery_email", "order_id": order_id, "to": customer_email[:50]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="send_delivery_email_manual",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


# ── Delivery Access Tools ─────────────────────────────────────────────────────


@mcp_registry.register(
    name="grant_delivery_access_manual",
    description="Submit a manual delivery access grant for approval. Creates an ApprovalRequest — does NOT grant.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "order_id": {"type": "string", "description": "UUID of the order"},
            "product_id": {"type": "string", "description": "UUID of the product"},
            "customer_email": {"type": "string", "description": "Customer email"},
        },
        "required": ["organization_id", "order_id", "product_id", "customer_email"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_grant_delivery_access_manual(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    order_id: str = "",
    product_id: str = "",
    customer_email: str = "",
) -> MCPResponse:
    """Submit a manual delivery access grant for approval. Does NOT grant."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        order_uuid = UUID(order_id)
        prod_uuid = UUID(product_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS", message="Invalid order_id or product_id.",
            request_id=auth.request_id if auth else "", organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="grant_delivery_access_manual",
        title=f"Grant delivery access: order {order_id[:12]}...",
        subject_type="delivery_access",
        subject_id=order_uuid,
        details={"order_id": order_id, "product_id": product_id, "customer_email": customer_email},
        preview={"action": "grant_delivery_access", "order_id": order_id[:12], "product_id": product_id[:12], "to": customer_email[:50]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="grant_delivery_access_manual",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="revoke_delivery_access",
    description="Submit a delivery access revocation for approval. Creates an ApprovalRequest — does NOT revoke.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "access_id": {"type": "string", "description": "UUID of the delivery access record"},
            "reason": {"type": "string", "description": "Reason for revocation"},
        },
        "required": ["organization_id", "access_id", "reason"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_revoke_delivery_access(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    access_id: str = "",
    reason: str = "",
) -> MCPResponse:
    """Submit a delivery access revocation for approval. Does NOT revoke."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        access_uuid = UUID(access_id)
    except (ValueError, TypeError):
        return MCPResponse.error_response(
            code="INVALID_PARAMS", message="Invalid access_id.",
            request_id=auth.request_id if auth else "", organization_id=organization_id,
        )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="revoke_delivery_access",
        title=f"Revoke delivery access: {reason[:100]}",
        subject_type="delivery_access",
        subject_id=access_uuid,
        details={"access_id": access_id, "reason": reason},
        preview={"action": "revoke_access", "access_id": access_id[:12], "reason": reason[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="revoke_delivery_access",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


# ── Public Content Tools ──────────────────────────────────────────────────────


@mcp_registry.register(
    name="public_content_publish",
    description="Submit public content publication for approval. Creates an ApprovalRequest — does NOT publish.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "content_title": {"type": "string", "description": "Title of the content to publish"},
            "content_summary": {"type": "string", "description": "Summary of the content"},
        },
        "required": ["organization_id", "content_title", "content_summary"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_APPROVAL,
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_public_content_publish(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    content_title: str = "",
    content_summary: str = "",
) -> MCPResponse:
    """Submit public content publication for approval. Does NOT publish."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="public_content_publish",
        title=f"Publish content: {content_title[:100]}",
        subject_type="public_content",
        subject_id=None,
        details={"content_title": content_title, "content_summary": content_summary},
        preview={"action": "publish_content", "title": content_title[:100], "summary": content_summary[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="public_content_publish",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")
