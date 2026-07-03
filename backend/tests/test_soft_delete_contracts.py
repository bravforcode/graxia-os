from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from app.models.contact import Contact
from app.models.opportunity import Opportunity
from app.models.organization import Organization
from app.models.submission import Submission
from app.repositories.contact_repository import ContactRepository
from app.repositories.opportunity_repository import OpportunityRepository
from app.repositories.submission_repository import SubmissionRepository
from sqlalchemy import select


@pytest.fixture()
def cqrs_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.core.unit_of_work.AsyncSessionLocal", session_factory)
    return session_factory


@pytest_asyncio.fixture()
async def test_org(db_session):
    org = Organization(
        id=uuid4(),
        name="Soft Delete Org",
        slug=f"soft-delete-org-{uuid4()}",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.mark.asyncio
async def test_repositories_soft_delete_without_removing_rows(db_session, test_org):
    opportunity = Opportunity(
        type="competition",
        title="Soft Delete Opportunity",
        total_score=Decimal("7.50"),
        status="found",
        found_at=datetime.now(UTC),
        organization_id=test_org.id,
    )
    contact = Contact(
        name="Soft Delete Contact",
        email="soft-delete@example.com",
        contact_type="lead",
        organization_id=test_org.id,
    )
    submission = Submission(
        type="proposal",
        title="Soft Delete Submission",
        status="draft",
        content="Draft content",
        organization_id=test_org.id,
    )
    db_session.add_all([opportunity, contact, submission])
    await db_session.commit()

    opportunity_repo = OpportunityRepository(db_session)
    contact_repo = ContactRepository(db_session)
    submission_repo = SubmissionRepository(db_session)

    assert await opportunity_repo.delete(opportunity.id) is True
    assert await contact_repo.delete(contact.id) is True
    assert await submission_repo.delete(submission.id) is True
    await db_session.commit()

    assert await opportunity_repo.get_by_id(opportunity.id) is None
    assert await contact_repo.get_by_id(contact.id) is None
    assert await submission_repo.get_by_id(submission.id) is None
    assert await opportunity_repo.count() == 0
    assert await contact_repo.count() == 0
    assert await submission_repo.count() == 0

    raw_opportunity = (
        await db_session.execute(
            select(Opportunity).where(Opportunity.id == opportunity.id).limit(1)
        )
    ).scalar_one()
    raw_contact = (
        await db_session.execute(select(Contact).where(Contact.id == contact.id).limit(1))
    ).scalar_one()
    raw_submission = (
        await db_session.execute(select(Submission).where(Submission.id == submission.id).limit(1))
    ).scalar_one()

    assert raw_opportunity.is_deleted is True
    assert raw_contact.is_deleted is True
    assert raw_submission.is_deleted is True
    assert raw_opportunity.deleted_at is not None
    assert raw_contact.deleted_at is not None
    assert raw_submission.deleted_at is not None


@pytest.mark.asyncio
async def test_canonical_apis_hide_soft_deleted_records(
    db_session, session_factory, public_async_client, cqrs_session_factory
):
    from app.core.auth import get_password_hash
    from app.models.user import User
    from app.models.organization import Organization

    # Create an org and user for API auth
    test_org_api = Organization(
        id=uuid4(),
        name="Soft Delete API Test Org",
        slug=f"soft-del-api-{uuid4()}",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(test_org_api)
    await db_session.commit()
    await db_session.refresh(test_org_api)

    test_email = f"soft-delete-user-{uuid4()}@example.com"
    test_user = User(
        id=uuid4(),
        email=test_email,
        hashed_password=get_password_hash("testpass123"),
        full_name="Soft Delete Tester",
        role="admin",
        is_active=True,
        organization_id=test_org_api.id,
    )
    db_session.add(test_user)
    await db_session.commit()
    await db_session.refresh(test_user)

    # Login to get auth token
    login_resp = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": test_email, "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json().get("access_token")
    public_async_client.headers["Authorization"] = f"Bearer {token}"

    active_opportunity = Opportunity(
        type="competition",
        title="Visible Opportunity",
        total_score=Decimal("8.10"),
        status="found",
        found_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    deleted_opportunity = Opportunity(
        type="competition",
        title="Hidden Opportunity",
        total_score=Decimal("7.90"),
        status="found",
        found_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    active_contact = Contact(
        name="Visible Contact",
        email="visible@example.com",
        contact_type="lead",
        created_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    deleted_contact = Contact(
        name="Hidden Contact",
        email="hidden@example.com",
        contact_type="lead",
        created_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    visible_submission = Submission(
        type="proposal",
        title="Visible Submission",
        status="draft",
        content="Visible draft",
        created_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    hidden_submission = Submission(
        type="proposal",
        title="Hidden Submission",
        status="draft",
        content="Hidden draft",
        created_at=datetime.now(UTC),
        organization_id=test_org_api.id,
    )
    db_session.add_all(
        [
            active_opportunity,
            deleted_opportunity,
            active_contact,
            deleted_contact,
            visible_submission,
            hidden_submission,
        ]
    )
    await db_session.commit()

    await OpportunityRepository(db_session).delete(deleted_opportunity.id)
    await ContactRepository(db_session).delete(deleted_contact.id)
    await SubmissionRepository(db_session).delete(hidden_submission.id)
    await db_session.commit()

    opportunities_response = await public_async_client.get("/api/v1/opportunities")
    assert opportunities_response.status_code == 200
    opportunities_payload = opportunities_response.json()
    opportunity_titles = {item["title"] for item in opportunities_payload["items"]}
    assert "Visible Opportunity" in opportunity_titles
    assert "Hidden Opportunity" not in opportunity_titles

    deleted_opportunity_response = await public_async_client.get(
        f"/api/v1/opportunities/{deleted_opportunity.id}"
    )
    assert deleted_opportunity_response.status_code == 404

    contacts_response = await public_async_client.get("/api/v1/contacts")
    assert contacts_response.status_code == 200
    contacts_payload = contacts_response.json()
    contact_names = {item["name"] for item in contacts_payload["items"]}
    assert "Visible Contact" in contact_names
    assert "Hidden Contact" not in contact_names

    deleted_contact_response = await public_async_client.get(f"/api/v1/contacts/{deleted_contact.id}")
    assert deleted_contact_response.status_code == 404

    submissions_response = await public_async_client.get("/api/v1/submissions")
    assert submissions_response.status_code == 200
    submission_titles = {item["title"] for item in submissions_response.json()}
    assert "Visible Submission" in submission_titles
    assert "Hidden Submission" not in submission_titles


def test_soft_delete_indexes_declared_on_models():
    opportunity_indexes = {index.name for index in Opportunity.__table__.indexes}
    submission_indexes = {index.name for index in Submission.__table__.indexes}
    contact_indexes = {index.name for index in Contact.__table__.indexes}

    assert "ix_opportunities_status_deleted_found_at" in opportunity_indexes
    assert "ix_opportunities_decision_deleted_score" in opportunity_indexes
    assert "ix_submissions_status_deleted_created_at" in submission_indexes
    assert "ix_submissions_opportunity_deleted_sent_at" in submission_indexes
    assert "ix_contacts_company_deleted_created_at" in contact_indexes
    assert "ix_contacts_email_deleted" in contact_indexes
