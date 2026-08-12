"""MCP workspace tools — mock Google Workspace operations via MCP.

Read / Low-Write tools:
  - search_customer_emails
  - draft_customer_reply
  - create_launch_doc
  - append_funnel_report_to_doc
  - export_revenue_summary_to_sheet
  - create_launch_calendar_plan
  - index_drive_knowledge_mock

Approval-Required tools:
  - send_customer_email
  - share_public_doc
  - create_real_calendar_event
  - move_drive_files

All tools operate through MockGoogleWorkspaceProvider — no real external calls.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.database import AsyncSessionLocal
from app.integrations.google_workspace import mock_workspace_provider
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPAuthContext
from app.mcp.auth import validate_org_context, safe_org_not_found
from app.mcp.audit import log_mcp_tool_call
from app.mcp.tools.write import (
    _validate_org,
    _create_approval_request,
    _approval_response,
)

logger = logging.getLogger(__name__)

TOOL_INPUT_ORG = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_OUTPUT_WORKSPACE = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "action": {"type": "string"},
        "item_id": {"type": "string"},
        "message": {"type": "string"},
        "data": {"type": "object"},
    },
    "additionalProperties": False,
}


# ── READ / LOW_WRITE Tools ───────────────────────────────────────────────────


@mcp_registry.register(
    name="search_customer_emails",
    description="Search customer emails in Gmail (mock). Returns up to 10 emails matching a query.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "query": {"type": "string", "description": "Search query to filter emails"},
            "max_results": {"type": "integer", "description": "Max results", "default": 10},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="READ_ONLY",
)
async def handle_search_customer_emails(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    query: str = "",
    max_results: int = 10,
) -> MCPResponse:
    """Search customer emails in Gmail (mock)."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        emails = await mock_workspace_provider.search_emails(
            query=query, max_results=max_results, organization_id=organization_id,
        )
        return MCPResponse.ok_response(
            data={
                "success": True,
                "action": "search_customer_emails",
                "items": [
                    {
                        "id": e.id,
                        "from": e.from_,
                        "subject": e.subject[:100] if e.subject else "",
                        "body_preview": e.body[:200] if e.body else "",
                        "status": e.status,
                    "created_at": e.created_at,
                    "thread_id": e.thread_id,
                }
                for e in emails
            ],
                "total": len(emails),
            },
            organization_id=organization_id,
            estimated_tokens=max(30, len(emails) * 20),
        )
    except Exception as exc:
        logger.warning("search_customer_emails error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to search customer emails.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="draft_customer_reply",
    description="Create a draft reply to a customer email thread. Does NOT send.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "thread_id": {"type": "string", "description": "ID of the email thread to reply to"},
            "body": {"type": "string", "description": "Draft reply body"},
        },
        "required": ["organization_id", "thread_id", "body"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="LOW_WRITE",
)
async def handle_draft_customer_reply(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    thread_id: str = "",
    body: str = "",
) -> MCPResponse:
    """Create a draft reply (mock). Does NOT send."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        result = await mock_workspace_provider.draft_reply(
            thread_id=thread_id, body=body, organization_id=organization_id,
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="draft_customer_reply",
            risk_level="LOW_WRITE",
            status="success",
            request_id=auth.request_id if auth else "",
        )
        return MCPResponse.ok_response(
            data=result.to_dict(),
            organization_id=organization_id,
            estimated_tokens=30,
        )
    except Exception as exc:
        logger.warning("draft_customer_reply error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to draft customer reply.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="create_launch_doc",
    description="Create a launch document in Google Docs (mock).",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "title": {"type": "string", "description": "Document title"},
            "body": {"type": "string", "description": "Document body content"},
        },
        "required": ["organization_id", "title", "body"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="LOW_WRITE",
)
async def handle_create_launch_doc(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    title: str = "",
    body: str = "",
) -> MCPResponse:
    """Create a launch document (mock)."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        result = await mock_workspace_provider.create_doc(
            title=title, body=body, organization_id=organization_id,
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="create_launch_doc",
            risk_level="LOW_WRITE",
            status="success",
            request_id=auth.request_id if auth else "",
        )
        return MCPResponse.ok_response(
            data=result.to_dict(),
            organization_id=organization_id,
            estimated_tokens=30,
        )
    except Exception as exc:
        logger.warning("create_launch_doc error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to create launch document.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="append_funnel_report_to_doc",
    description="Append funnel report content to an existing document (mock).",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "doc_id": {"type": "string", "description": "Document ID to append to"},
            "content": {"type": "string", "description": "Content to append"},
        },
        "required": ["organization_id", "doc_id", "content"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="LOW_WRITE",
)
async def handle_append_funnel_report_to_doc(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    doc_id: str = "",
    content: str = "",
) -> MCPResponse:
    """Append funnel report to a doc (mock)."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        result = await mock_workspace_provider.append_to_doc(
            doc_id=doc_id, content=content, organization_id=organization_id,
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="append_funnel_report_to_doc",
            risk_level="LOW_WRITE",
            status="success",
            request_id=auth.request_id if auth else "",
        )
        return MCPResponse.ok_response(
            data=result.to_dict(),
            organization_id=organization_id,
            estimated_tokens=30,
        )
    except Exception as exc:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to append content to document.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="export_revenue_summary_to_sheet",
    description="Export revenue summary to a Google Sheet (mock). Creates a new sheet with revenue data.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "sheet_title": {"type": "string", "description": "Title for the new sheet", "default": "Revenue Summary"},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="LOW_WRITE",
)
async def handle_export_revenue_summary_to_sheet(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    sheet_title: str = "Revenue Summary",
) -> MCPResponse:
    """Export revenue summary to a sheet (mock)."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        # Fetch revenue data from DB
        from sqlalchemy import select, func
        from app.models.funnel import FunnelOrder
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            revenue = await db.scalar(
                select(func.coalesce(func.sum(FunnelOrder.total_amount), 0)).where(
                    FunnelOrder.organization_id == org_uuid,
                    FunnelOrder.status == "paid",
                )
            ) or 0
            paid_count = await db.scalar(
                select(func.count(FunnelOrder.id)).where(
                    FunnelOrder.organization_id == org_uuid,
                    FunnelOrder.status == "paid",
                )
            ) or 0

        columns = ["Metric", "Value"]
        rows = [
            ["Total Revenue", str(revenue)],
            ["Paid Orders", str(paid_count)],
            ["Currency", "THB"],
            ["Generated At", str(datetime.now(UTC).isoformat())],
        ]

        result = await mock_workspace_provider.create_sheet(
            title=sheet_title,
            columns=columns,
            rows=rows,
            organization_id=organization_id,
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="export_revenue_summary_to_sheet",
            risk_level="LOW_WRITE",
            status="success",
            request_id=auth.request_id if auth else "",
        )
        return MCPResponse.ok_response(
            data=result.to_dict(),
            organization_id=organization_id,
            estimated_tokens=50,
        )
    except Exception as exc:
        logger.warning("export_revenue_summary_to_sheet error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to export revenue summary.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="create_launch_calendar_plan",
    description="Create a launch plan calendar with milestones (mock).",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "summary": {"type": "string", "description": "Calendar event summary"},
            "description": {"type": "string", "description": "Detailed description of the launch plan"},
            "start_time": {"type": "string", "description": "Start time (ISO format)"},
            "end_time": {"type": "string", "description": "End time (ISO format)"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee emails",
                "default": [],
            },
        },
        "required": ["organization_id", "summary", "start_time", "end_time"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="LOW_WRITE",
)
async def handle_create_launch_calendar_plan(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    summary: str = "",
    description: str = "",
    start_time: str = "",
    end_time: str = "",
    attendees: list[str] | None = None,
) -> MCPResponse:
    """Create a launch calendar plan (mock)."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        result = await mock_workspace_provider.create_calendar_event(
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees or [],
            organization_id=organization_id,
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="create_launch_calendar_plan",
            risk_level="LOW_WRITE",
            status="success",
            request_id=auth.request_id if auth else "",
        )
        return MCPResponse.ok_response(
            data=result.to_dict(),
            organization_id=organization_id,
            estimated_tokens=40,
        )
    except Exception as exc:
        logger.warning("create_launch_calendar_plan error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to create launch calendar plan.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="index_drive_knowledge_mock",
    description="Index Drive files for knowledge search (mock). Lists available mock drive files.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "query": {"type": "string", "description": "Optional search query", "default": ""},
            "max_results": {"type": "integer", "description": "Max results", "default": 20},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKSPACE,
    risk_level="READ_ONLY",
)
async def handle_index_drive_knowledge_mock(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    query: str = "",
    max_results: int = 20,
) -> MCPResponse:
    """Index Drive knowledge (mock). Lists available mock drive files."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    try:
        files = await mock_workspace_provider.list_files(
            query=query, max_results=max_results, organization_id=organization_id,
        )
        return MCPResponse.ok_response(
            data={
                "success": True,
                "action": "index_drive_knowledge_mock",
                "items": [
                    {
                        "id": f.id,
                        "name": f.name,
                        "mime_type": f.mime_type,
                        "size_bytes": f.size_bytes,
                        "status": f.status,
                        "parent_folder_id": f.parent_folder_id,
                    }
                    for f in files
                ],
                "total": len(files),
            },
            organization_id=organization_id,
            estimated_tokens=max(20, len(files) * 15),
        )
    except Exception as exc:
        logger.warning("index_drive_knowledge_mock error: %s", exc)
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message="Failed to index drive knowledge.",
            request_id=auth.request_id if auth else "",
            organization_id=organization_id,
        )


# ── APPROVAL_REQUIRED Tools ───────────────────────────────────────────────────


@mcp_registry.register(
    name="send_customer_email",
    description="Send a customer email. Creates an ApprovalRequest — does NOT send.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body content"},
        },
        "required": ["organization_id", "to", "subject", "body"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "approval_required": {"type": "boolean"},
            "approval_request_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["approval_required", "approval_request_id"],
        "additionalProperties": False,
    },
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_send_customer_email(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    to: str = "",
    subject: str = "",
    body: str = "",
) -> MCPResponse:
    """Send customer email — creates ApprovalRequest, does NOT send."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    # Also call mock provider to record the attempt
    await mock_workspace_provider.send_email(
        to=to, subject=subject, body=body, organization_id=organization_id,
    )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="send_customer_email",
        title=f"Send email to {to[:50]}: {subject[:100]}",
        subject_type="customer_communication",
        subject_id=None,
        details={"to": to, "subject": subject, "body_preview": body[:200]},
        preview={"action": "send_email", "to": to, "subject": subject[:200], "body_preview": body[:500]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="send_customer_email",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="share_public_doc",
    description="Share a document publicly. Creates an ApprovalRequest — does NOT share.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "doc_id": {"type": "string", "description": "Document ID to share"},
            "share_with_email": {"type": "string", "description": "Email to share with"},
            "role": {
                "type": "string",
                "description": "Permission role (reader, commenter, writer)",
                "default": "reader",
                "enum": ["reader", "commenter", "writer"],
            },
        },
        "required": ["organization_id", "doc_id", "share_with_email"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "approval_required": {"type": "boolean"},
            "approval_request_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["approval_required", "approval_request_id"],
        "additionalProperties": False,
    },
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_share_public_doc(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    doc_id: str = "",
    share_with_email: str = "",
    role: str = "reader",
) -> MCPResponse:
    """Share a document — creates ApprovalRequest, does NOT share."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    # Record via mock provider
    await mock_workspace_provider.share_file(
        file_id=doc_id, email=share_with_email, role=role, organization_id=organization_id,
    )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="share_public_doc",
        title=f"Share document {doc_id[:12]}... with {share_with_email[:50]}",
        subject_type="document",
        subject_id=None,
        details={"doc_id": doc_id, "share_with_email": share_with_email, "role": role},
        preview={"action": "share_doc", "doc_id": doc_id[:12], "share_with": share_with_email, "role": role},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="share_public_doc",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="create_real_calendar_event",
    description="Create a real calendar event with attendees. Creates an ApprovalRequest — does NOT create.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "summary": {"type": "string", "description": "Event summary/title"},
            "description": {"type": "string", "description": "Event description"},
            "start_time": {"type": "string", "description": "Start time (ISO format)"},
            "end_time": {"type": "string", "description": "End time (ISO format)"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Attendee emails",
                "default": [],
            },
        },
        "required": ["organization_id", "summary", "start_time", "end_time"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "approval_required": {"type": "boolean"},
            "approval_request_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["approval_required", "approval_request_id"],
        "additionalProperties": False,
    },
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_create_real_calendar_event(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    summary: str = "",
    description: str = "",
    start_time: str = "",
    end_time: str = "",
    attendees: list[str] | None = None,
) -> MCPResponse:
    """Create a real calendar event — creates ApprovalRequest, does NOT create real event."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    # Record via mock provider
    await mock_workspace_provider.create_calendar_event(
        summary=summary, description=description,
        start_time=start_time, end_time=end_time,
        attendees=attendees or [], organization_id=organization_id,
    )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="create_real_calendar_event",
        title=f"Create calendar event: {summary[:100]}",
        subject_type="calendar_event",
        subject_id=None,
        details={"summary": summary, "start_time": start_time, "end_time": end_time, "attendees": attendees or []},
        preview={"action": "create_event", "summary": summary[:100], "start_time": start_time, "attendees": (attendees or [])[:3]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="create_real_calendar_event",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")


@mcp_registry.register(
    name="move_drive_files",
    description="Move Drive files between folders. Creates an ApprovalRequest — does NOT move.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "file_id": {"type": "string", "description": "File ID to move"},
            "new_parent_folder_id": {"type": "string", "description": "Destination folder ID"},
            "reason": {"type": "string", "description": "Reason for moving", "default": ""},
        },
        "required": ["organization_id", "file_id", "new_parent_folder_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "approval_required": {"type": "boolean"},
            "approval_request_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["approval_required", "approval_request_id"],
        "additionalProperties": False,
    },
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_move_drive_files(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    file_id: str = "",
    new_parent_folder_id: str = "",
    reason: str = "",
) -> MCPResponse:
    """Move Drive files — creates ApprovalRequest, does NOT move."""
    org_uuid, err = await _validate_org(auth, organization_id, auth.request_id if auth else "")
    if err:
        return err

    # Record via mock provider
    await mock_workspace_provider.move_file(
        file_id=file_id, new_parent_id=new_parent_folder_id,
        organization_id=organization_id,
    )

    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="move_drive_files",
        title=f"Move file {file_id[:12]}... to folder {new_parent_folder_id[:12]}...",
        subject_type="drive_file",
        subject_id=None,
        details={"file_id": file_id, "new_parent_folder_id": new_parent_folder_id, "reason": reason},
        preview={"action": "move_file", "file_id": file_id[:12], "destination": new_parent_folder_id[:12], "reason": reason[:200]},
    )

    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="move_drive_files",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=auth.request_id if auth else "",
    )

    return _approval_response(ar, organization_id, auth.request_id if auth else "")
