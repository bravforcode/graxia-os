"""
ULTRA: Universal Test Factories
Factory pattern for generating test data with realistic defaults
"""
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.auth import get_password_hash
from app.models.contact import Contact
from app.models.job_posting import JobPosting
from app.models.opportunity import Opportunity
from app.models.organization import Organization
from app.models.submission import Submission
from app.models.usage_log import UsageLog
from app.models.user import User


class Factory:
    """Base factory with common utilities"""
    
    _counter = 0
    
    @classmethod
    def _next_sequence(cls) -> int:
        """Get next sequence number for unique values"""
        cls._counter += 1
        return cls._counter
    
    @classmethod
    def _fake_email(cls, prefix: str = "user") -> str:
        """Generate fake email"""
        return f"{prefix}_{cls._next_sequence()}_{uuid4().hex[:8]}@test.com"
    
    @classmethod
    def _fake_uuid(cls) -> str:
        """Generate fake UUID"""
        return str(uuid4())


class OrganizationFactory(Factory):
    """Factory for Organization model"""
    
    @classmethod
    def create(
        cls,
        name: str | None = None,
        plan: str = "free",
        **overrides
    ) -> dict[str, Any]:
        """Create organization data"""
        seq = cls._next_sequence()
        
        defaults = {
            "id": uuid4(),
            "name": name or f"Test Organization {seq}",
            "slug": f"test-org-{seq}-{uuid4().hex[:6]}",
            "plan": plan,
            "status": "active",
            "monthly_lead_limit": cls._get_plan_limit(plan),
            "monthly_ai_credit_cents": cls._get_plan_credits(plan),
            "seats": cls._get_plan_seats(plan),
            "settings": {},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    def _get_plan_limit(cls, plan: str) -> int:
        limits = {"free": 100, "starter": 1000, "pro": 5000, "enterprise": 50000}
        return limits.get(plan, 100)
    
    @classmethod
    def _get_plan_credits(cls, plan: str) -> int:
        credits = {"free": 500, "starter": 5000, "pro": 20000, "enterprise": 100000}
        return credits.get(plan, 500)
    
    @classmethod
    def _get_plan_seats(cls, plan: str) -> int:
        seats = {"free": 1, "starter": 5, "pro": 10, "enterprise": 100}
        return seats.get(plan, 1)
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> Organization:
        """Build and persist organization"""
        data = cls.create(**kwargs)
        org = Organization(**data)
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        return org


class UserFactory(Factory):
    """Factory for User model"""
    
    @classmethod
    def create(
        cls,
        email: str | None = None,
        organization_id: str | None = None,
        role: str = "user",
        **overrides
    ) -> dict[str, Any]:
        """Create user data"""
        seq = cls._next_sequence()
        
        defaults = {
            "id": uuid4(),
            "email": email or cls._fake_email(f"user{seq}"),
            "hashed_password": get_password_hash("Test123!@#"),
            "full_name": f"Test User {seq}",
            "role": role,
            "is_active": True,
            "organization_id": organization_id,
            "totp_enabled": False,
            "totp_secret": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "onboarding_completed_at": None,
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> User:
        """Build and persist user"""
        data = cls.create(**kwargs)
        user = User(**data)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user


class ContactFactory(Factory):
    """Factory for Contact model"""
    
    @classmethod
    def create(
        cls,
        organization_id: str | None = None,
        **overrides
    ) -> dict[str, Any]:
        """Create contact data"""
        seq = cls._next_sequence()
        
        first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Edward", "Fiona"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        
        defaults = {
            "id": uuid4(),
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
            "organization_id": organization_id,
            "status": random.choice(["active", "inactive", "lead"]),
            "source": random.choice(["manual", "import", "scraper"]),
            "notes": f"Test contact {seq}",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> Contact:
        """Build and persist contact"""
        data = cls.create(**kwargs)
        contact = Contact(**data)
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)
        return contact
    
    @classmethod
    async def build_batch(cls, db_session, count: int, **kwargs) -> list[Contact]:
        """Build multiple contacts"""
        contacts = []
        for _ in range(count):
            contact = await cls.build(db_session, **kwargs)
            contacts.append(contact)
        return contacts


class OpportunityFactory(Factory):
    """Factory for Opportunity model"""
    
    @classmethod
    def create(
        cls,
        organization_id: str | None = None,
        **overrides
    ) -> dict[str, Any]:
        """Create opportunity data"""
        seq = cls._next_sequence()
        
        titles = [
            "Senior Software Engineer",
            "Product Manager",
            "Data Scientist",
            "UX Designer",
            "DevOps Engineer",
            "Marketing Manager",
            "Sales Representative",
        ]
        
        defaults = {
            "id": uuid4(),
            "title": f"{random.choice(titles)} - Position {seq}",
            "company": f"Tech Corp {seq}",
            "description": f"Exciting opportunity {seq}",
            "organization_id": organization_id,
            "status": random.choice(["open", "in_progress", "closed", "won", "lost"]),
            "value": Decimal(str(random.randint(10000, 200000))),
            "probability": random.randint(0, 100),
            "expected_close_date": datetime.now(UTC) + timedelta(days=random.randint(7, 90)),
            "found_at": datetime.now(UTC) - timedelta(days=random.randint(1, 30)),
            "source": random.choice(["linkedin", "upwork", "indeed", "referral"]),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> Opportunity:
        """Build and persist opportunity"""
        data = cls.create(**kwargs)
        opp = Opportunity(**data)
        db_session.add(opp)
        await db_session.commit()
        await db_session.refresh(opp)
        return opp


class SubmissionFactory(Factory):
    """Factory for Submission model"""
    
    @classmethod
    def create(
        cls,
        organization_id: str | None = None,
        **overrides
    ) -> dict[str, Any]:
        """Create submission data"""
        seq = cls._next_sequence()
        
        defaults = {
            "id": uuid4(),
            "title": f"Proposal {seq}",
            "type": random.choice(["proposal", "application", "bid", "contract"]),
            "status": random.choice(["draft", "submitted", "approved", "rejected", "pending"]),
            "organization_id": organization_id,
            "content": f"Submission content {seq}",
            "submitted_at": datetime.now(UTC) if random.random() > 0.5 else None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> Submission:
        """Build and persist submission"""
        data = cls.create(**kwargs)
        sub = Submission(**data)
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)
        return sub


class JobPostingFactory(Factory):
    """Factory for JobPosting model"""
    
    @classmethod
    def create(
        cls,
        organization_id: str | None = None,
        **overrides
    ) -> dict[str, Any]:
        """Create job posting data"""
        seq = cls._next_sequence()
        
        platforms = ["linkedin", "indeed", "glassdoor", "ziprecruiter"]
        
        defaults = {
            "id": uuid4(),
            "title": f"Job Title {seq}",
            "company": f"Company {seq}",
            "description": f"Job description {seq}",
            "organization_id": organization_id,
            "source_platform": random.choice(platforms),
            "source_url": f"https://example.com/job/{seq}",
            "status": random.choice(["discovered", "applied", "interviewing", "offer", "rejected"]),
            "match_score": Decimal(str(random.uniform(1.0, 10.0))),
            "job_type": random.choice(["full_time", "part_time", "contract", "freelance"]),
            "source_hash": f"hash_{uuid4().hex[:16]}",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> JobPosting:
        """Build and persist job posting"""
        data = cls.create(**kwargs)
        job = JobPosting(**data)
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)
        return job


class UsageLogFactory(Factory):
    """Factory for UsageLog model"""
    
    @classmethod
    def create(
        cls,
        organization_id: str | None = None,
        **overrides
    ) -> dict[str, Any]:
        """Create usage log data"""
        seq = cls._next_sequence()
        
        features = ["lead_discovery", "scoring", "email_send", "ai_generation", "export"]
        
        defaults = {
            "id": uuid4(),
            "organization_id": organization_id,
            "feature": random.choice(features),
            "quantity": random.randint(1, 100),
            "cost_usd": Decimal(str(random.uniform(0.01, 5.00))),
            "meta": {"source": "test", "seq": seq},
            "created_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults
    
    @classmethod
    async def build(cls, db_session, **kwargs) -> UsageLog:
        """Build and persist usage log"""
        data = cls.create(**kwargs)
        log = UsageLog(**data)
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)
        return log


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Scenario Builders
# ═══════════════════════════════════════════════════════════════════════════════

class ScenarioBuilder:
    """Build complete test scenarios"""
    
    @classmethod
    async def create_organization_with_users(
        cls,
        db_session,
        plan: str = "pro",
        user_count: int = 3,
    ) -> tuple[Organization, list[User]]:
        """Create organization with multiple users"""
        org = await OrganizationFactory.build(db_session, plan=plan)
        
        users = []
        # Create admin
        admin = await UserFactory.build(
            db_session,
            organization_id=org.id,
            role="admin",
            email="admin@test.com"
        )
        users.append(admin)
        
        # Create regular users
        for i in range(user_count - 1):
            user = await UserFactory.build(
                db_session,
                organization_id=org.id,
                role="user"
            )
            users.append(user)
        
        return org, users
    
    @classmethod
    async def create_full_tenant_context(
        cls,
        db_session,
        plan: str = "pro",
    ) -> dict[str, Any]:
        """Create complete tenant context with all data types"""
        org, users = await cls.create_organization_with_users(db_session, plan)
        
        # Create contacts
        contacts = await ContactFactory.build_batch(db_session, 10, organization_id=org.id)
        
        # Create opportunities
        opportunities = []
        for _ in range(5):
            opp = await OpportunityFactory.build(db_session, organization_id=org.id)
            opportunities.append(opp)
        
        # Create submissions
        submissions = []
        for _ in range(3):
            sub = await SubmissionFactory.build(db_session, organization_id=org.id)
            submissions.append(sub)
        
        # Create usage logs
        usage_logs = []
        for _ in range(10):
            log = await UsageLogFactory.build(db_session, organization_id=org.id)
            usage_logs.append(log)
        
        return {
            "organization": org,
            "users": users,
            "contacts": contacts,
            "opportunities": opportunities,
            "submissions": submissions,
            "usage_logs": usage_logs,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Export all factories
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "OrganizationFactory",
    "UserFactory",
    "ContactFactory",
    "OpportunityFactory",
    "SubmissionFactory",
    "JobPostingFactory",
    "UsageLogFactory",
    "ScenarioBuilder",
]
