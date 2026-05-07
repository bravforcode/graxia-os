"""
Test Approval Service
Verify human-in-the-loop approval workflow
"""
import pytest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..services.approval_service import ApprovalService
from ..models import Approval, AIDraft
from ..enums import ApprovalStatus


@pytest.mark.asyncio
async def test_create_approval(db_session: AsyncSession):
    """Test creating an approval request."""
    approval = await ApprovalService.create_approval(
        db=db_session,
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000001",
        title="Test Approval",
        preview="This is a test approval",
        requested_by_agent="test_agent",
    )
    
    assert approval.id is not None
    assert approval.status == ApprovalStatus.PENDING
    assert approval.object_type == "email"
    assert approval.expires_at is not None


@pytest.mark.asyncio
async def test_approve_approval(db_session: AsyncSession):
    """Test approving a pending request."""
    # Create approval
    approval = await ApprovalService.create_approval(
        db=db_session,
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000002",
        title="Test Approval",
    )
    
    # Approve it
    approved = await ApprovalService.approve(
        db=db_session,
        approval_id=approval.id,
        ceo_notes="Looks good!",
    )
    
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.reviewed_at is not None
    assert approved.ceo_notes == "Looks good!"


@pytest.mark.asyncio
async def test_reject_approval(db_session: AsyncSession):
    """Test rejecting a pending request."""
    # Create approval
    approval = await ApprovalService.create_approval(
        db=db_session,
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000003",
        title="Test Approval",
    )
    
    # Reject it
    rejected = await ApprovalService.reject(
        db=db_session,
        approval_id=approval.id,
        reason="Not aligned with brand voice",
        ceo_notes="Please revise",
    )
    
    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.reviewed_at is not None
    assert rejected.reason == "Not aligned with brand voice"
    assert rejected.ceo_notes == "Please revise"


@pytest.mark.asyncio
async def test_approve_non_pending_fails(db_session: AsyncSession):
    """Test that approving non-pending approval fails."""
    # Create and approve approval
    approval = await ApprovalService.create_approval(
        db=db_session,
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000004",
        title="Test Approval",
    )
    
    await ApprovalService.approve(db_session, approval.id)
    
    # Try to approve again
    with pytest.raises(ValueError, match="is not pending"):
        await ApprovalService.approve(db_session, approval.id)


@pytest.mark.asyncio
async def test_check_expired_approvals(db_session: AsyncSession):
    """Test checking and auto-rejecting expired approvals."""
    # Create expired approval
    approval = Approval(
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000005",
        title="Expired Approval",
        status=ApprovalStatus.PENDING,
        expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
    )
    db_session.add(approval)
    await db_session.commit()
    
    # Check expired approvals
    expired_count = await ApprovalService.check_expired_approvals(
        db=db_session,
        auto_reject=True,
    )
    
    assert expired_count == 1
    
    # Verify approval was rejected
    result = await db_session.execute(
        select(Approval).where(Approval.id == approval.id)
    )
    rejected_approval = result.scalar_one()
    
    assert rejected_approval.status == ApprovalStatus.REJECTED
    assert rejected_approval.reason == "Auto-rejected: expired"


@pytest.mark.asyncio
async def test_get_pending_approvals(db_session: AsyncSession):
    """Test getting all pending approvals."""
    # Create multiple approvals
    for i in range(5):
        await ApprovalService.create_approval(
            db=db_session,
            object_type="email",
            object_id=f"00000000-0000-0000-0000-00000000000{i}",
            title=f"Approval {i}",
        )
    
    # Get pending approvals
    pending = await ApprovalService.get_pending_approvals(db_session, limit=10)
    
    assert len(pending) == 5
    assert all(a.status == ApprovalStatus.PENDING for a in pending)


@pytest.mark.asyncio
async def test_create_draft_approval(db_session: AsyncSession):
    """Test creating approval for an AI draft."""
    # Create AI draft
    draft = AIDraft(
        draft_type="email",
        prompt="Write a sales email",
        output="Dear customer, ...",
        generated_by_agent="sales_agent",
    )
    db_session.add(draft)
    await db_session.commit()
    
    # Create approval for draft
    approval = await ApprovalService.create_draft_approval(
        db=db_session,
        draft_id=draft.id,
        title="Review sales email",
        preview="Dear customer, ...",
    )
    
    assert approval.ai_draft_id == draft.id
    assert approval.object_type == "ai_draft"
    
    # Verify draft is linked to approval
    result = await db_session.execute(
        select(AIDraft).where(AIDraft.id == draft.id)
    )
    updated_draft = result.scalar_one()
    
    assert updated_draft.approval_id == approval.id


@pytest.mark.asyncio
async def test_approval_custom_expiry(db_session: AsyncSession):
    """Test approval with custom expiry time."""
    approval = await ApprovalService.create_approval(
        db=db_session,
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000010",
        title="Custom Expiry",
        expires_in_hours=1,  # 1 hour instead of default 24
    )
    
    # Verify expiry time
    time_until_expiry = (approval.expires_at - datetime.utcnow()).total_seconds()
    
    # Should be approximately 1 hour (3600 seconds)
    assert 3500 <= time_until_expiry <= 3700  # Allow 100 second tolerance
