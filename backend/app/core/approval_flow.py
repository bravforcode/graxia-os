"""Approval flow manager backed by the canonical ApprovalRequest model."""
from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.core.policy import get_action_policy
from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from app.models.submission import Submission
from app.telegram_bot.keyboards import approval_keyboard

logger = logging.getLogger(__name__)


def _parse_uuid(value: str | UUID) -> UUID | None:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ApprovalFlowManager:
    """Create, resolve, remind, and summarize approval requests."""

    def __init__(self) -> None:
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self.approval_timeout_hours = 24
        self.reminder_timeout_hours = 12

    async def request_approval(
        self,
        action_type: str,
        action_description: str,
        action_data: dict[str, Any],
        priority: str = "normal",
        callback: Callable[[dict[str, Any]], Any] | None = None,
    ) -> str:
        policy = get_action_policy(action_type)
        now = datetime.now(UTC)
        details = {
            **(action_data or {}),
            "description": action_description,
            "priority": priority,
        }
        approval = ApprovalRequest(
            title=action_description[:300] or action_type,
            action_type=action_type,
            status="pending",
            policy_class=policy.policy_class,
            requested_by="approval_flow",
            details=details,
            preview={"description": action_description, "priority": priority},
            expires_at=now + timedelta(hours=self.approval_timeout_hours),
        )

        async with AsyncSessionLocal() as db:
            db.add(approval)
            await db.commit()
            await db.refresh(approval)

        if callback:
            self.pending_approvals[str(approval.id)] = {
                "callback": callback,
                "data": action_data or {},
            }

        await self._send_telegram_approval(approval)
        logger.info("Approval request created: %s (%s)", approval.id, action_type)
        return str(approval.id)

    async def _send_telegram_approval(self, approval: ApprovalRequest) -> None:
        from app.telegram_bot.bot import send_message

        details = approval.details or {}
        priority = str(details.get("priority") or "normal")
        priority_marker = {
            "urgent": "[urgent]",
            "high": "[high]",
            "normal": "[normal]",
            "low": "[low]",
        }.get(priority, "[normal]")
        expires_at = approval.expires_at.isoformat() if approval.expires_at else "no expiry"
        description = details.get("description") or approval.title
        message = (
            f"{priority_marker} Approval required\n\n"
            f"Action: {approval.action_type}\n"
            f"Description: {description}\n"
            f"Priority: {priority}\n"
            f"Expires: {expires_at}"
        )
        await send_message(
            message,
            parse_mode=None,
            reply_markup=approval_keyboard(str(approval.id), approval.batch_key),
        )

    async def handle_approval(self, approval_id: str, approved: bool, user_id: str = "user") -> bool:
        parsed_id = _parse_uuid(approval_id)
        if parsed_id is None:
            logger.warning("Approval request id is invalid: %s", approval_id)
            return False

        async with AsyncSessionLocal() as db:
            approval = await db.get(ApprovalRequest, parsed_id)
            if approval is None:
                logger.warning("Approval request not found: %s", approval_id)
                return False
            if approval.status != "pending":
                logger.warning("Approval request already processed: %s", approval_id)
                return False

            now = datetime.now(UTC)
            expires_at = _as_utc(approval.expires_at)
            if expires_at and now > expires_at:
                approval.status = "expired"
                approval.resolved_at = now
                approval.resolution_note = "Expired before approval"
                await db.commit()
                self.pending_approvals.pop(approval_id, None)
                return False

            approval.status = "approved" if approved else "rejected"
            approval.resolved_at = now
            approval.resolution_note = f"Resolved by {user_id}"
            await db.commit()
            await db.refresh(approval)

        if not approved:
            self.pending_approvals.pop(approval_id, None)
            return False

        success = await self._execute_action(approval)
        if not success:
            return False

        callback_info = self.pending_approvals.pop(approval_id, None)
        callback = callback_info.get("callback") if callback_info else None
        if callback:
            result = callback(approval.details or {})
            if inspect.isawaitable(result):
                await result
        return True

    async def _execute_action(self, approval: ApprovalRequest) -> bool:
        action_data = approval.details or {}
        if approval.action_type == "email_send":
            return await self._execute_email_send(action_data)
        if approval.action_type == "linkedin_outreach":
            return await self._execute_linkedin_outreach(action_data)
        if approval.action_type == "job_apply":
            return await self._execute_job_apply(action_data)
        logger.warning("Unknown action type: %s", approval.action_type)
        return False

    async def _execute_email_send(self, data: dict[str, Any]) -> bool:
        from app.core.google_workspace import google_workspace
        from app.telegram_bot.bot import send_message

        to_email = data.get("to")
        subject = data.get("subject")
        body = data.get("body")
        if not to_email or not subject or not body:
            return False

        message_id = await google_workspace.send_message(str(to_email), str(subject), str(body))
        if message_id:
            await send_message(f"Email sent: {to_email}\nSubject: {subject}", parse_mode=None)
        return bool(message_id)

    async def _execute_linkedin_outreach(self, data: dict[str, Any]) -> bool:
        from app.core.openclaw import openclaw_client

        profile_url = data.get("profile_url")
        if not profile_url:
            return False
        result = await openclaw_client.scrape_url(
            url=str(profile_url),
            platform="linkedin",
            use_cache=False,
        )
        return bool(result)

    async def _execute_job_apply(self, data: dict[str, Any]) -> bool:
        opportunity_id = _parse_uuid(data.get("opportunity_id") or data.get("job_id"))
        now = datetime.now(UTC)
        submission = Submission(
            opportunity_id=opportunity_id,
            type="application",
            title=str(data.get("title") or data.get("job_url") or "Job application"),
            status="sent",
            content=str(data.get("cover_letter") or data.get("proposal_text") or ""),
            subject_line=str(data.get("subject") or "Application"),
            sent_at=now,
        )

        async with AsyncSessionLocal() as db:
            db.add(submission)
            await db.commit()
            await db.refresh(submission)

        from app.core.event_bus import event_bus

        await event_bus.emit(
            "submission.sent",
            {
                "submission_id": str(submission.id),
                "opportunity_id": str(opportunity_id) if opportunity_id else None,
            },
        )
        return True

    async def check_expired_approvals(self) -> None:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            rows = list(
                (
                    await db.execute(
                        select(ApprovalRequest).where(
                            ApprovalRequest.status == "pending",
                            ApprovalRequest.expires_at.is_not(None),
                            ApprovalRequest.expires_at < now,
                        )
                    )
                ).scalars()
            )
            for approval in rows:
                approval.status = "expired"
                approval.resolved_at = now
                approval.resolution_note = "Expired before approval"
            if rows:
                await db.commit()
                logger.info("Auto-expired %s approval requests", len(rows))

    async def send_reminders(self) -> None:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            reminder_cutoff = now - timedelta(hours=self.reminder_timeout_hours)
            rows = list(
                (
                    await db.execute(
                        select(ApprovalRequest).where(
                            ApprovalRequest.status == "pending",
                            ApprovalRequest.expires_at.is_not(None),
                        )
                    )
                ).scalars()
            )

            reminded = 0
            for approval in rows:
                created_at = _as_utc(approval.created_at) or now
                details = dict(approval.details or {})
                if created_at > reminder_cutoff or details.get("reminder_sent_at"):
                    continue
                await self._send_reminder(approval)
                details["reminder_sent_at"] = now.isoformat()
                approval.details = details
                reminded += 1

            if reminded:
                await db.commit()
                logger.info("Sent %s approval reminders", reminded)

    async def _send_reminder(self, approval: ApprovalRequest) -> None:
        from app.telegram_bot.bot import send_message

        expires_at = _as_utc(approval.expires_at)
        hours_left = 0.0
        if expires_at:
            hours_left = max(0.0, (expires_at - datetime.now(UTC)).total_seconds() / 3600)
        await send_message(
            (
                "Approval reminder\n\n"
                f"Action: {approval.action_type}\n"
                f"Description: {(approval.details or {}).get('description') or approval.title}\n"
                f"Expires in: {hours_left:.1f} hours"
            ),
            parse_mode=None,
        )

    async def get_pending_approvals(self, limit: int = 10) -> list[ApprovalRequest]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_approval_stats(self) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            total = int(await db.scalar(select(func.count(ApprovalRequest.id))) or 0)
            status_result = await db.execute(
                select(ApprovalRequest.status, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.status)
            )
            by_status = {status: int(count) for status, count in status_result.all()}

        approved = by_status.get("approved", 0)
        rejected = by_status.get("rejected", 0)
        total_decided = approved + rejected
        approval_rate = (approved / total_decided * 100) if total_decided else 0
        return {
            "total": total,
            "by_status": by_status,
            "approval_rate_percent": round(approval_rate, 2),
        }


approval_flow_manager = ApprovalFlowManager()
