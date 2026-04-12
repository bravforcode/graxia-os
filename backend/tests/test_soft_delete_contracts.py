from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.contact import Contact
from app.models.opportunity import Opportunity
from app.models.submission import Submission
from app.repositories.contact_repository import ContactRepository
from app.repositories.opportunity_repository import OpportunityRepository
from app.repositories.submission_repository import SubmissionRepository


@pytest.fixture()
def cqrs_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.cqrs.submission_handlers.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.cqrs.opportunity_handlers.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.cqrs.contact_handlers.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.cqrs.draft_handlers.AsyncSessionLocal", session_factory)
    return session_factory


@pytest.mark.asyncio
async def test_repositories_soft_delete_without_removing_rows(db_session):
    opportunity = Opportunity(
        type="competition",
        title="Soft Delete Opportunity",
        total_score=Decimal("7.50"),
        status="found",
        found_at=datetime.now(timezone.utc),
    )
    contact = Contact(
        name="Soft Delete Contact",
        email="soft-delete@example.com",
        contact_type="lead",
    )
    submission = Submission(
        type="proposal",
        title="Soft Delete Submission",
        status="draft",
        content="Draft content",
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
        await db_session.execute(
            select(Submission).where(Submission.id == submission.id).limit(1)
        )
    ).scalar_one()

    assert raw_opportunity.is_deleted is True
    assert raw_contact.is_deleted is True
    assert raw_submission.is_deleted is True
    assert raw_opportunity.deleted_at is not None
    assert raw_contact.deleted_at is not None
    assert raw_submission.deleted_at is not None


@pytest.mark.asyncio
async def test_canonical_apis_hide_soft_deleted_records(async_client, db_session, cqrs_session_factory):
    active_opportunity = Opportunity(
        type="competition",
        title="Visible Opportunity",
        total_score=Decimal("8.10"),
        status="found",
        found_at=datetime.now(timezone.utc),
    )
    deleted_opportunity = Opportunity(
        type="competition",
        title="Hidden Opportunity",
        total_score=Decimal("7.90"),
        status="found",
        found_at=datetime.now(timezone.utc),
    )
    active_contact = Contact(
        name="Visible Contact",
        email="visible@example.com",
        contact_type="lead",
        created_at=datetime.now(timezone.utc),
    )
    deleted_contact = Contact(
        name="Hidden Contact",
        email="hidden@example.com",
        contact_type="lead",
        created_at=datetime.now(timezone.utc),
    )
    visible_submission = Submission(
        type="proposal",
        title="Visible Submission",
        status="draft",
        content="Visible draft",
        created_at=datetime.now(timezone.utc),
    )
    hidden_submission = Submission(
        type="proposal",
        title="Hidden Submission",
        status="draft",
        content="Hidden draft",
        created_at=datetime.now(timezone.utc),
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

    opportunities_response = await async_client.get("/api/v1/opportunities")
    assert opportunities_response.status_code == 200
    opportunities_payload = opportunities_response.json()
    opportunity_titles = {item["title"] for item in opportunities_payload["items"]}
    assert "Visible Opportunity" in opportunity_titles
    assert "Hidden Opportunity" not in opportunity_titles

    deleted_opportunity_response = await async_client.get(
        f"/api/v1/opportunities/{deleted_opportunity.id}"
    )
    assert deleted_opportunity_response.status_code == 404

    contacts_response = await async_client.get("/api/v1/contacts")
    assert contacts_response.status_code == 200
    contacts_payload = contacts_response.json()
    contact_names = {item["name"] for item in contacts_payload["items"]}
    assert "Visible Contact" in contact_names
    assert "Hidden Contact" not in contact_names

    deleted_contact_response = await async_client.get(
        f"/api/v1/contacts/{deleted_contact.id}"
    )
    assert deleted_contact_response.status_code == 404

    submissions_response = await async_client.get("/api/v1/submissions")
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
