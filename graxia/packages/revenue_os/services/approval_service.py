"""
Revenue OS Approval Service
Human-in-the-loop approval workflow management
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
import structlog

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError

from ..models import Approval, AIDraft, EmailOutbox, ContentPost
from ..enums import ApprovalStatus
from ..constants import APPROVAL_DEFAULT_EXPIRY_HOURS
from ..core.db_ops import atomic_operation
from ..core.validators import (
    validate_string_length,
    validate_positive_integer,
    ValidationError,
)

logger = structlog.get_logger()


class ApprovalService:
    """
    Approval workflow service for CEO oversight.
    All AI-generated content and critical actions require approval.
    """

    @staticmethod
    async def create_approval(
        db: AsyncSession,
        object_type: str,
        object_id: UUID,
        title: str,
        preview: Optional[str] = None,
        requested_by_agent: Optional[str] = None,
        product_id: Optional[UUID] = None,
        content_post_id: Optional[UUID] = None,
        ai_draft_id: Optional[UUID] = None,
        expires_in_hours: int = APPROVAL_DEFAULT_EXPIRY_HOURS,
    ) -> Approval:
        """
        Create an approval request.

        Args:
            db: Database session
            object_type: Type of object requiring approval
            object_id: ID of object requiring approval
            title: Approval title/summary
            preview: Optional preview text
            requested_by_agent: Agent requesting approval
            product_id: Optional product reference
            content_post_id: Optional content post reference
            ai_draft_id: Optional AI draft reference
            expires_in_hours: Hours until auto-rejection

        Returns:
            Approval: Created approval request

        Raises:
            ValidationError: If input validation fails
        """
        # Validate inputs
        try:
            validate_string_length(object_type, "object_type", max_length=50)
            validate_string_length(title, "title", max_length=255)
            validate_positive_integer(expires_in_hours, "expires_in_hours")

            if preview:
                validate_string_length(preview, "preview", max_length=5000)
            if requested_by_agent:
                validate_string_length(requested_by_agent, "requested_by_agent", max_length=100)

        except ValidationError as e:
            logger.error(
                "approval_validation_failed",
                error=str(e),
                object_type=object_type,
                title=title,
            )
            raise

        async with atomic_operation(db):
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

            approval = Approval(
                object_type=object_type,
                object_id=object_id,
                title=title,
                preview=preview,
                requested_by_agent=requested_by_agent,
                product_id=product_id,
                content_post_id=content_post_id,
                ai_draft_id=ai_draft_id,
                status=ApprovalStatus.PENDING,
                expires_at=expires_at,
            )
            db.add(approval)
            await db.flush()

            logger.info(
                "approval_created",
                approval_id=str(approval.id),
                object_type=object_type,
                requested_by=requested_by_agent,
                expires_at=expires_at.isoformat(),
            )

            return approval

    @staticmethod
    async def approve(
        db: AsyncSession,
        approval_id: UUID,
        ceo_notes: Optional[str] = None,
    ) -> Approval:
        """
        Approve a pending request.

        Args:
            db: Database session
            approval_id: Approval ID
            ceo_notes: Optional CEO notes

        Returns:
            Approval: Approved approval record

        Raises:
            ValueError: If approval not found or not pending
            ValidationError: If input validation fails
        """
        # Validate inputs
        if ceo_notes:
            try:
                validate_string_length(ceo_notes, "ceo_notes", max_length=5000)
            except ValidationError as e:
                logger.error(
                    "approval_notes_validation_failed",
                    error=str(e),
                    approval_id=str(approval_id),
                )
                raise

        async with atomic_operation(db):
            try:
                result = await db.execute(
                    select(Approval).where(Approval.id == approval_id)
                )
                approval = result.scalar_one_or_none()

                if not approval:
                    raise ValueError(f"Approval {approval_id} not found")

                if approval.status != ApprovalStatus.PENDING:
                    raise ValueError(
                        f"Approval {approval_id} is not pending (status: {approval.status.value})"
                    )

                approval.status = ApprovalStatus.APPROVED
                approval.reviewed_at = datetime.utcnow()
                approval.ceo_notes = ceo_notes

                await db.commit()

                logger.info(
                    "approval_approved",
                    approval_id=str(approval_id),
                    object_type=approval.object_type,
                    has_notes=ceo_notes is not None,
                )

                return approval

            except (OperationalError, SQLTimeoutError) as e:
                await db.rollback()
                logger.error(
                    "approval_database_error",
                    approval_id=str(approval_id),
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise ValueError(f"Database error: {str(e)}") from e

    @staticmethod
    async def reject(
        db: AsyncSession,
        approval_id: UUID,
        reason: str,
        ceo_notes: Optional[str] = None,
    ) -> Approval:
        """
        Reject a pending request.

        Args:
            db: Database session
            approval_id: Approval ID
            reason: Rejection reason
            ceo_notes: Optional CEO notes

        Returns:
            Approval: Rejected approval record

        Raises:
            ValueError: If approval not found or not pending
        """
        async with atomic_operation(db):
            result = await db.execute(
                select(Approval).where(Approval.id == approval_id)
            )
            approval = result.scalar_one_or_none()

            if not approval:
                raise ValueError(f"Approval {approval_id} not found")

            if approval.status != ApprovalStatus.PENDING:
                raise ValueError(
                    f"Approval {approval_id} is not pending (status: {approval.status.value})"
                )

            approval.status = ApprovalStatus.REJECTED
            approval.reviewed_at = datetime.utcnow()
            approval.reason = reason
            approval.ceo_notes = ceo_notes

            # Cancel associated email if exists
            email_result = await db.execute(
                select(EmailOutbox).where(EmailOutbox.approval_id == approval_id)
            )
            email = email_result.scalar_one_or_none()
            if email:
                from .email_service import EmailService
                await EmailService.cancel_email(db, email.id)

            await db.commit()

            logger.info(
                "approval_rejected",
                approval_id=str(approval_id),
                object_type=approval.object_type,
                reason=reason,
            )

            return approval

    @staticmethod
    async def check_expired_approvals(
        db: AsyncSession,
        auto_reject: bool = True,
    ) -> int:
        """
        Check for expired approvals and optionally auto-reject them.

        Args:
            db: Database session
            auto_reject: Whether to automatically reject expired approvals

        Returns:
            int: Number of expired approvals found
        """
        now = datetime.utcnow()

        result = await db.execute(
            select(Approval)
            .where(
                and_(
                    Approval.status == ApprovalStatus.PENDING,
                    Approval.expires_at < now,
                )
            )
        )
        expired_approvals = result.scalars().all()

        if auto_reject:
            for approval in expired_approvals:
                approval.status = ApprovalStatus.REJECTED
                approval.reviewed_at = now
                approval.reason = "Auto-rejected: expired"

                logger.info(
                    "approval_auto_rejected",
                    approval_id=str(approval.id),
                    object_type=approval.object_type,
                )

            await db.commit()

        logger.info(
            "expired_approvals_checked",
            count=len(expired_approvals),
            auto_rejected=auto_reject,
        )

        return len(expired_approvals)

    @staticmethod
    async def get_pending_approvals(
        db: AsyncSession,
        limit: int = 50,
    ) -> list[Approval]:
        """
        Get all pending approvals.

        Args:
            db: Database session
            limit: Maximum number to return

        Returns:
            list[Approval]: List of pending approvals
        """
        result = await db.execute(
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.requested_at.asc())
            .limit(limit)
        )

        return list(result.scalars().all())

    @staticmethod
    async def get_approval_by_id(
        db: AsyncSession,
        approval_id: UUID,
    ) -> Optional[Approval]:
        """Get approval by ID."""
        result = await db.execute(
            select(Approval).where(Approval.id == approval_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_draft_approval(
        db: AsyncSession,
        draft_id: UUID,
        title: str,
        preview: Optional[str] = None,
    ) -> Approval:
        """
        Create approval for an AI draft.

        Args:
            db: Database session
            draft_id: AI draft ID
            title: Approval title
            preview: Optional preview text

        Returns:
            Approval: Created approval
        """
        # Get draft details
        draft_result = await db.execute(
            select(AIDraft).where(AIDraft.id == draft_id)
        )
        draft = draft_result.scalar_one_or_none()

        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        approval = await ApprovalService.create_approval(
            db=db,
            object_type="ai_draft",
            object_id=draft_id,
            title=title,
            preview=preview or draft.output[:500],
            requested_by_agent=draft.generated_by_agent,
            ai_draft_id=draft_id,
        )

        # Link approval to draft
        draft.approval_id = approval.id
        await db.commit()

        return approval
