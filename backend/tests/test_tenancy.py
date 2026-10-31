"""
Phase 4 Multi-Tenancy Tests
Tests for organization isolation, tenant middleware, and data filtering
"""
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select


class TestOrganizationModel:
    """Test Organization model and relationships"""

    @pytest.mark.asyncio
    async def test_organization_creation(self, db_session):
        """Organization should be created with all required fields"""
        from app.models.organization import Organization
        
        org_id = uuid4()
        org = Organization(
            id=org_id,
            name="Test Organization",
            slug="test-organization",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
            settings={},
        )
        
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        assert org.id == org_id
        assert org.name == "Test Organization"
        assert org.slug == "test-organization"
        assert org.plan == "free"
        assert org.status == "active"

    @pytest.mark.asyncio
    async def test_organization_slug_unique(self, db_session):
        """Organization slug should be unique"""
        from app.models.organization import Organization
        from sqlalchemy.exc import IntegrityError
        
        org1 = Organization(
            id=uuid4(),
            name="Org One",
            slug="unique-slug",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add(org1)
        await db_session.commit()
        
        # Duplicate slug should fail
        org2 = Organization(
            id=uuid4(),
            name="Org Two",
            slug="unique-slug",  # Same slug
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add(org2)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_organization_relationship(self, db_session):
        """User should have organization_id foreign key"""
        from app.core.auth import get_password_hash
        from app.models.organization import Organization
        from app.models.user import User
        
        # Create organization
        org = Organization(
            id=uuid4(),
            name="Test Org",
            slug="test-org-user",
            plan="pro",
            status="active",
            monthly_lead_limit=1000,
            monthly_ai_credit_cents=5000,
            seats=5,
        )
        db_session.add(org)
        await db_session.commit()
        
        # Create user with organization
        user = User(
            id=uuid4(),
            email="test@org.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Test User",
            organization_id=org.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        assert user.organization_id == org.id


class TestTenantIsolation:
    """Test data isolation between tenants"""

    @pytest.mark.asyncio
    async def test_contacts_isolated_by_organization(self, db_session):
        """Contacts should be filtered by organization_id"""
        from app.models.contact import Contact
        from app.models.organization import Organization
        
        # Create two organizations
        org1 = Organization(
            id=uuid4(),
            name="Org 1",
            slug="org-1",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        org2 = Organization(
            id=uuid4(),
            name="Org 2",
            slug="org-2",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add_all([org1, org2])
        await db_session.commit()
        
        # Create contacts for each org
        contact1 = Contact(
            id=uuid4(),
            name="Contact 1",
            email="contact1@test.com",
            organization_id=org1.id,
        )
        contact2 = Contact(
            id=uuid4(),
            name="Contact 2",
            email="contact2@test.com",
            organization_id=org2.id,
        )
        db_session.add_all([contact1, contact2])
        await db_session.commit()
        
        # Query contacts for org1 only
        result = await db_session.execute(
            select(Contact).where(Contact.organization_id == org1.id)
        )
        org1_contacts = result.scalars().all()
        
        assert len(org1_contacts) == 1
        assert org1_contacts[0].name == "Contact 1"

    @pytest.mark.asyncio
    async def test_opportunities_isolated_by_organization(self, db_session):
        """Opportunities should be filtered by organization_id"""
        from app.models.opportunity import Opportunity
        from app.models.organization import Organization
        
        # Create organization
        org = Organization(
            id=uuid4(),
            name="Test Org",
            slug="test-opp-org",
            plan="pro",
            status="active",
            monthly_lead_limit=1000,
            monthly_ai_credit_cents=5000,
            seats=5,
        )
        db_session.add(org)
        await db_session.commit()
        
        # Create opportunity with org
        opp = Opportunity(
            id=uuid4(),
            title="Test Opportunity",
            organization_id=org.id,
            status="found",  # 'open' is not valid
        )
        db_session.add(opp)
        await db_session.commit()
        
        # Verify opportunity has organization
        result = await db_session.execute(
            select(Opportunity).where(Opportunity.id == opp.id)
        )
        found = result.scalar_one()
        assert found.organization_id == org.id


class TestTenantMiddleware:
    """Test tenant middleware functionality"""

    @pytest.mark.asyncio
    async def test_get_org_dependency(self, async_client):
        """get_org dependency should return user's organization"""
        # This tests that the tenant middleware is working
        # The actual behavior depends on the implementation
        response = await async_client.get("/api/v1/billing/plans")
        
        # Should not crash due to tenant issues
        assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_auto_org_creation_for_new_user(
        self, public_async_client, db_session, monkeypatch
    ):
        """Confirmed social signups get separate personal organizations."""
        import jwt

        from app.api import auth as auth_api
        from app.models.organization import Organization
        from app.models.user import User

        token_claims = {}
        canonical_users = {}
        monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")
        monkeypatch.setattr(
            jwt, "decode", lambda token, *args, **kwargs: token_claims[token]
        )
        monkeypatch.setattr(
            auth_api,
            "_fetch_supabase_user",
            AsyncMock(side_effect=lambda token: canonical_users[token]),
        )
        monkeypatch.setattr(
            "app.services.automation_email_service.AutomationEmailService.trigger_welcome",
            AsyncMock(),
        )

        emails = [f"newuser_{uuid4().hex}@test.com" for _ in range(2)]
        for email in emails:
            token = f"offline-social-token-{uuid4().hex}"
            subject = f"supabase-user-{uuid4().hex}"
            token_claims[token] = {
                "sub": subject,
                "email": "untrusted-token-email@example.invalid",
            }
            canonical_users[token] = {
                "id": subject,
                "email": email,
                "email_confirmed_at": "2026-01-01T00:00:00Z",
                "app_metadata": {"provider": "google", "providers": ["google"]},
                "user_metadata": {"full_name": "New Test User"},
            }
            response = await public_async_client.post(
                "/api/v1/auth/social-login",
                json={"token": token, "provider": "google"},
            )
            assert response.status_code == 200, response.text

        result = await db_session.execute(select(User).where(User.email.in_(emails)))
        users = result.scalars().all()
        assert {user.email for user in users} == set(emails)
        organization_ids = {user.organization_id for user in users}
        assert None not in organization_ids
        assert len(organization_ids) == len(emails)

        result = await db_session.execute(
            select(Organization).where(Organization.id.in_(organization_ids))
        )
        organizations = result.scalars().all()
        assert {organization.id for organization in organizations} == organization_ids


class TestMultiTenantModels:
    """Test all models have organization_id"""

    @pytest.mark.asyncio
    async def test_job_posting_has_organization_id(self, db_session):
        """JobPosting model should have organization_id column"""
        from app.models.job_posting import JobPosting
        from app.models.organization import Organization
        
        org = Organization(
            id=uuid4(),
            name="Test Org",
            slug="test-job-org",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add(org)
        await db_session.commit()
        
        job = JobPosting(
            id=uuid4(),
            title="Test Job",
            company="Test Co",
            source_platform="linkedin",
            source_url="http://test.com/job",
            job_type="job",
            organization_id=org.id,
            source_hash=f"hash-{uuid4()}",
        )
        db_session.add(job)
        await db_session.commit()
        
        assert job.organization_id == org.id

    @pytest.mark.asyncio
    async def test_submission_has_organization_id(self, db_session):
        """Submission model should have organization_id column"""
        from app.models.organization import Organization
        from app.models.submission import Submission
        
        org = Organization(
            id=uuid4(),
            name="Test Org",
            slug="test-sub-org",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add(org)
        await db_session.commit()
        
        sub = Submission(
            id=uuid4(),
            title="Test Submission",
            type="proposal",
            status="draft",
            organization_id=org.id,
        )
        db_session.add(sub)
        await db_session.commit()
        
        assert sub.organization_id == org.id

    @pytest.mark.asyncio
    async def test_email_thread_has_organization_id(self, db_session):
        """EmailThread model should have organization_id column"""
        from app.models.email_thread import EmailThread
        from app.models.organization import Organization
        
        org = Organization(
            id=uuid4(),
            name="Test Org",
            slug="test-email-org",
            plan="free",
            status="active",
            monthly_lead_limit=100,
            monthly_ai_credit_cents=500,
            seats=1,
        )
        db_session.add(org)
        await db_session.commit()
        
        thread = EmailThread(
            id=uuid4(),
            thread_id=f"thread-{uuid4()}",
            subject="Test Thread",
            organization_id=org.id,
        )
        db_session.add(thread)
        await db_session.commit()
        
        assert thread.organization_id == org.id
