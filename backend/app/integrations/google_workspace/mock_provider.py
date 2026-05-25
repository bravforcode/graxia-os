"""Mock Google Workspace provider — stores everything in memory, no real external calls.

All methods are safe for local/test use. Email send, public doc share,
real calendar events, and Drive file moves all require ApprovalRequest
(approval-gated) — they return approval_required status without executing.

Storage is scoped by organization_id for defense-in-depth.
"""
from __future__ import annotations

import copy
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.integrations.google_workspace.base import GoogleWorkspaceProvider
from app.integrations.google_workspace.errors import (
    WorkspaceNotFoundError,
    WorkspacePermissionError,
)
from app.integrations.google_workspace.schemas import (
    WorkspaceMockEmail,
    WorkspaceMockDoc,
    WorkspaceMockSheet,
    WorkspaceMockDriveFile,
    WorkspaceMockCalendarEvent,
    WorkspaceActionResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_ORG = "00000000-0000-0000-0000-000000000001"


class MockGoogleWorkspaceProvider(GoogleWorkspaceProvider):
    """Mock Google Workspace provider — pure in-memory, no real API calls.

    Stores mock emails, docs, sheets, drive files, and calendar events in
    organization-scoped storage. Gmail send, public doc share, real calendar
    events, and Drive file moves return approval_required (approval-gated).

    Use reset() to clear storage between test runs.
    """

    def __init__(self) -> None:
        self._org_storage: dict[str, dict[str, dict[str, Any]]] = {}
        self._ensure_org(_DEFAULT_ORG)
        self._seed_default_data()
        self._reset_count = 0

    def reset(self) -> None:
        """Reset all storage — call between test runs for isolation."""
        self._org_storage = {}
        self._ensure_org(_DEFAULT_ORG)
        self._seed_default_data()
        self._reset_count += 1

    def _ensure_org(self, org_id: str) -> None:
        """Ensure storage exists for the given org."""
        if org_id not in self._org_storage:
            self._org_storage[org_id] = {
                "emails": {},
                "docs": {},
                "sheets": {},
                "drive_files": {},
                "calendar_events": {},
            }

    def _org(self, org_id: str) -> dict[str, dict]:
        """Get or create org storage, defaulting to _DEFAULT_ORG if empty."""
        oid = org_id or _DEFAULT_ORG
        self._ensure_org(oid)
        return self._org_storage[oid]

    def _seed_default_data(self, org_id: str | None = None) -> None:
        """Seed default mock data for a realistic workspace experience.

        If org_id is None, seeds into the default org only.
        """
        target = self._org(org_id or _DEFAULT_ORG)
        now = datetime.now(UTC).isoformat()

        # ── Seed emails ─────────────────────────────────────────────────
        for i in range(3):
            email_id = str(uuid4())
            target["emails"][email_id] = WorkspaceMockEmail(
                id=email_id,
                thread_id=f"thread-{i}",
                to="owner@graxia.local",
                from_=f"customer{i}@example.com",
                subject=f"Customer Inquiry #{i+1}" if i > 0 else "Question about Digital Product",
                body=f"This is a test email from customer {i+1}." if i > 0 else "Hi, I'm interested in your digital product. Can you tell me more about it?",
                status="inbox",
                created_at=now,
            )

        # ── Seed drive files ────────────────────────────────────────────
        for i in range(2):
            file_id = str(uuid4())
            target["drive_files"][file_id] = WorkspaceMockDriveFile(
                id=file_id,
                name=f"Launch Document {i+1}" if i > 0 else "Funnel Report Q1",
                mime_type="application/vnd.google-apps.document",
                size_bytes=1024 * (i + 1),
                parent_folder_id=None,
                status="private",
                created_at=now,
            )

    def is_mock(self) -> bool:
        return True

    def _org_emails(self, org_id: str) -> dict[str, WorkspaceMockEmail]:
        return self._org(org_id)["emails"]

    def _org_docs(self, org_id: str) -> dict[str, WorkspaceMockDoc]:
        return self._org(org_id)["docs"]

    def _org_sheets(self, org_id: str) -> dict[str, WorkspaceMockSheet]:
        return self._org(org_id)["sheets"]

    def _org_drive(self, org_id: str) -> dict[str, WorkspaceMockDriveFile]:
        return self._org(org_id)["drive_files"]

    def _org_calendar(self, org_id: str) -> dict[str, WorkspaceMockCalendarEvent]:
        return self._org(org_id)["calendar_events"]

    # ── Gmail ───────────────────────────────────────────────────────────────

    async def search_emails(
        self, query: str = "", max_results: int = 10, organization_id: str = ""
    ) -> list[WorkspaceMockEmail]:
        """Search mock emails by query string."""
        results = list(self._org_emails(organization_id).values())
        if query:
            q = query.lower()
            results = [
                e for e in results
                if q in e.subject.lower() or q in e.body.lower() or q in e.from_.lower() or q in e.to.lower()
            ]
        return results[:max_results]

    async def draft_reply(
        self, thread_id: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Create a draft reply to an email thread. Does NOT send."""
        emails = self._org_emails(organization_id)
        thread_emails = [e for e in emails.values() if e.thread_id == thread_id]
        if not thread_emails:
            raise WorkspaceNotFoundError("thread")

        draft_id = str(uuid4())
        draft = WorkspaceMockEmail(
            id=draft_id,
            thread_id=thread_id,
            to=thread_emails[0].from_,
            from_="owner@graxia.local",
            subject=f"Re: {thread_emails[0].subject}",
            body=body,
            status="draft",
        )
        emails[draft_id] = draft

        return WorkspaceActionResult(
            success=True,
            action="draft_reply",
            item_id=draft_id,
            message=f"Draft reply created for thread {thread_id[:12]}...",
            data={"thread_id": thread_id, "to": draft.to, "subject": draft.subject},
        )

    async def send_email(
        self, to: str, subject: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Send email — returns approval_required (approval-gated). Does NOT send."""
        emails = self._org_emails(organization_id)
        email_id = str(uuid4())
        emails[email_id] = WorkspaceMockEmail(
            id=email_id,
            to=to,
            from_="owner@graxia.local",
            subject=subject,
            body=body,
            status="approval_required",
        )

        return WorkspaceActionResult(
            success=False,
            action="send_email",
            item_id=email_id,
            message="Sending email requires human approval. An approval request has been created.",
            data={"approval_required": True, "email_id": email_id, "to": to, "subject_preview": subject[:100]},
        )

    # ── Docs ────────────────────────────────────────────────────────────────

    async def create_doc(
        self, title: str, body: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Create a mock Google Doc."""
        docs = self._org_docs(organization_id)
        doc_id = str(uuid4())
        doc = WorkspaceMockDoc(
            id=doc_id,
            title=title,
            body=body,
            status="draft",
        )
        docs[doc_id] = doc

        return WorkspaceActionResult(
            success=True,
            action="create_doc",
            item_id=doc_id,
            message=f"Document '{title}' created (mock).",
            data={"doc_id": doc_id, "title": title, "body_preview": body[:200]},
        )

    async def append_to_doc(
        self, doc_id: str, content: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Append content to a mock Google Doc."""
        docs = self._org_docs(organization_id)
        doc = docs.get(doc_id)
        if doc is None:
            raise WorkspaceNotFoundError("document")

        doc.body += f"\n\n{content}"
        doc.updated_at = datetime.now(UTC).isoformat()

        return WorkspaceActionResult(
            success=True,
            action="append_to_doc",
            item_id=doc_id,
            message=f"Content appended to document '{doc.title}' (mock).",
            data={"doc_id": doc_id, "title": doc.title, "new_length": len(doc.body)},
        )

    # ── Sheets ──────────────────────────────────────────────────────────────

    async def create_sheet(
        self, title: str, columns: list[str], rows: list[list[str]] | None = None,
        organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Create a mock Google Sheet."""
        sheets = self._org_sheets(organization_id)
        sheet_id = str(uuid4())
        sheet = WorkspaceMockSheet(
            id=sheet_id,
            title=title,
            columns=columns,
            rows=rows or [columns],
        )
        sheets[sheet_id] = sheet

        return WorkspaceActionResult(
            success=True,
            action="create_sheet",
            item_id=sheet_id,
            message=f"Sheet '{title}' created with {len(columns)} columns (mock).",
            data={"sheet_id": sheet_id, "title": title, "columns": columns, "row_count": len(sheet.rows)},
        )

    async def append_to_sheet(
        self, sheet_id: str, rows: list[list[str]], organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Append rows to a mock Google Sheet."""
        sheets = self._org_sheets(organization_id)
        sheet = sheets.get(sheet_id)
        if sheet is None:
            raise WorkspaceNotFoundError("sheet")

        sheet.rows.extend(rows)

        return WorkspaceActionResult(
            success=True,
            action="append_to_sheet",
            item_id=sheet_id,
            message=f"Appended {len(rows)} rows to sheet '{sheet.title}' (mock).",
            data={"sheet_id": sheet_id, "title": sheet.title, "total_rows": len(sheet.rows)},
        )

    # ── Drive ───────────────────────────────────────────────────────────────

    async def list_files(
        self, query: str = "", max_results: int = 20, organization_id: str = ""
    ) -> list[WorkspaceMockDriveFile]:
        """List mock Drive files."""
        results = list(self._org_drive(organization_id).values())
        if query:
            q = query.lower()
            results = [
                f for f in results
                if q in f.name.lower()
            ]
        return results[:max_results]

    async def share_file(
        self, file_id: str, email: str, role: str = "reader",
        organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Share a Drive file — returns approval_required. Does NOT share.

        Does NOT validate file existence since this is an approval-gated action.
        """
        return WorkspaceActionResult(
            success=False,
            action="share_file",
            item_id=file_id,
            message="Sharing files publicly requires human approval. An approval request has been created.",
            data={"approval_required": True, "file_id": file_id, "share_with": email, "role": role},
        )

    async def move_file(
        self, file_id: str, new_parent_id: str, organization_id: str = ""
    ) -> WorkspaceActionResult:
        """Move a Drive file — returns approval_required. Does NOT move.

        Does NOT validate file existence since this is an approval-gated action.
        """
        return WorkspaceActionResult(
            success=False,
            action="move_file",
            item_id=file_id,
            message="Moving Drive files requires human approval. An approval request has been created.",
            data={"approval_required": True, "file_id": file_id, "new_parent_id": new_parent_id},
        )

    # ── Calendar ────────────────────────────────────────────────────────────

    async def create_calendar_event(
        self, summary: str, description: str, start_time: str, end_time: str,
        attendees: list[str] | None = None, organization_id: str = "",
    ) -> WorkspaceActionResult:
        """Create a calendar event — returns tentative (mock mode)."""
        cal = self._org_calendar(organization_id)
        event_id = str(uuid4())
        event = WorkspaceMockCalendarEvent(
            id=event_id,
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees or [],
            status="tentative",
        )
        cal[event_id] = event

        return WorkspaceActionResult(
            success=True,
            action="create_calendar_event",
            item_id=event_id,
            message=f"Calendar event '{summary}' created (tentative, mock).",
            data={
                "event_id": event_id,
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time,
                "status": "tentative",
                "attendees": attendees or [],
            },
        )


# Global mock instance
mock_workspace_provider = MockGoogleWorkspaceProvider()
