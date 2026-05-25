"""Tests for ApprovalRequest organization scoping.

Verifies:
- ApprovalRequest inherits TenantMixin with organization_id
- Approval creation requires a valid Organization record (TenantMixin FK)
- Approval list is org-scoped through AuthContext
- Org mismatch returns 404 not found (no leak)
"""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_approval_list_org_scoped(async_client, db_session):
    """Approval list must be scoped to the authenticated organization."""
    resp = await async_client.get(
        "/api/v1/approvals?limit=5",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should always return valid response even if empty
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data


@pytest.mark.asyncio
async def test_approval_get_org_scoped(async_client, db_session):
    """Approval get by ID must be org-scoped.
    Non-existent or cross-org ID must return 404."""
    fake_id = uuid.uuid4()
    resp = await async_client.get(
        f"/api/v1/approvals/{fake_id}",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    # Should return 404, not reveal whether approval exists or not
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approval_model_has_organization_id(db_session):
    """ApprovalRequest model must have organization_id via TenantMixin."""
    from app.models.approval_request import ApprovalRequest

    assert hasattr(ApprovalRequest, "organization_id"), (
        "ApprovalRequest must have organization_id column from TenantMixin"
    )


@pytest.mark.asyncio
async def test_approval_creation_org_scoped(db_session):
    """Creating an approval must set organization_id.
    Requires a valid Organization record due to TenantMixin FK constraint.
    """
    from app.models.approval_request import ApprovalRequest
    from app.models.organization import Organization
    from datetime import datetime, timezone
    from uuid import uuid4

    org_id = uuid4()
    # TenantMixin has ForeignKey("organizations.id"), so we must create Org first
    org = Organization(
        id=org_id,
        name=f"Test Org {org_id}",
        slug=f"test-org-{org_id}",
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(org)
    await db_session.commit()

    # Create approval request
    approval = ApprovalRequest(
        id=uuid4(),
        organization_id=org_id,
        title="Test approval",
        action_type="funnel_recommendation",
        subject_type="funnel_recommendation",
        subject_id=None,
        status="pending",
        policy_class="recommendation_approval",
        requested_by="test",
        details={"test": True},
    )
    db_session.add(approval)
    await db_session.commit()

    # Verify organization_id is set
    assert approval.organization_id == org_id


@pytest.mark.asyncio
async def test_approval_cross_org_blocked(async_client, db_session):
    """Cross-org access to approval should return 404 (no leak)."""
    from app.models.approval_request import ApprovalRequest
    from app.models.organization import Organization
    from datetime import datetime, timezone
    from uuid import uuid4

    org_a = uuid4()
    org_b = uuid4()

    # Create both orgs (needed for FK constraint on TenantMixin)
    for org_id, name in [(org_a, "Org A"), (org_b, "Org B")]:
        org = Organization(
            id=org_id,
            name=f"{name} {org_id}",
            slug=f"test-{org_id}",
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(org)
    await db_session.commit()

    approval = ApprovalRequest(
        id=uuid4(),
        organization_id=org_a,
        title="Org A approval",
        action_type="test",
        status="pending",
        policy_class="test",
        requested_by="test",
    )
    db_session.add(approval)
    await db_session.commit()

    # Try to access from org B
    resp = await async_client.get(
        f"/api/v1/approvals/{approval.id}",
        headers={"X-Graxia-Org-Id": str(org_b)},
    )
    # Must be 404, not reveal that the approval exists in org A
    assert resp.status_code == 404
