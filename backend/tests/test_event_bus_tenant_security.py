"""Offline regressions for trusted event ownership and terminal delivery gates."""
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.context import AuthContext
from app.core.approval_flow import VerifiedJobApplicationReceipt
from app.core.event_bus import DeliverySuccessReplayError, EventBus
from app.models.organization import Organization
from app.models.submission import Submission


OWNER = UUID("00000000-0000-0000-0000-000000000001")
FOREIGN = UUID("00000000-0000-0000-0000-000000000002")


def persisted_auth(organization_id: UUID) -> AuthContext:
    return AuthContext(
        organization_id=organization_id,
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )


async def queue_and_process(bus: EventBus, event: str, payload: dict, auth=None):
    await bus.emit(event, payload, auth_context=auth)
    await bus._process_event(*bus._queue.get_nowait())


@pytest.mark.asyncio
async def test_dlq_owner_requires_trusted_context_and_matching_payload():
    bus = EventBus()

    async def fail(_payload):
        raise RuntimeError("synthetic handler failure")

    for event in (
        "untrusted.payload",
        "forged.owner",
        "mismatched.nested",
        "mismatched.metadata",
        "owner.ok",
    ):
        bus.subscribe(event, fail)

    await queue_and_process(
        bus, "untrusted.payload", {"organization_id": str(OWNER)}
    )
    await queue_and_process(
        bus,
        "forged.owner",
        {"organization_id": str(OWNER)},
        AuthContext(
            organization_id=OWNER,
            environment="production",
            auth_method="local_test",
            is_mock_auth=True,
            is_authenticated=True,
        ),
    )
    await queue_and_process(
        bus,
        "mismatched.nested",
        {
            "organization_id": str(OWNER),
            "data": {"org_id": str(FOREIGN)},
        },
        persisted_auth(OWNER),
    )
    await queue_and_process(
        bus,
        "mismatched.metadata",
        {"metadata": {"org_id": str(FOREIGN)}},
        persisted_auth(OWNER),
    )
    await queue_and_process(
        bus,
        "owner.ok",
        {"data": {"org_id": str(OWNER)}},
        persisted_auth(OWNER),
    )

    assert [row[0] for row in bus.get_failed_events_for_organization(OWNER)] == [
        "owner.ok"
    ]
    assert bus.get_failed_events_for_organization(FOREIGN) == []
    assert len(bus.get_failed_events()) == 5
    assert bus._failed_event_organizations == [None, None, None, None, str(OWNER)]


@pytest.mark.asyncio
async def test_production_missing_or_mock_auth_never_uses_payload_owner():
    bus = EventBus()

    async def fail(_payload):
        raise RuntimeError("synthetic handler failure")

    bus.subscribe("private.failure", fail)
    bus.subscribe("dev.foreign.failure", fail)
    await queue_and_process(
        bus,
        "private.failure",
        {"organization_id": str(OWNER)},
        AuthContext(
            organization_id=OWNER,
            environment="production",
            auth_method="local_test",
            is_mock_auth=True,
            is_authenticated=True,
        ),
    )
    await queue_and_process(
        bus,
        "dev.foreign.failure",
        {},
        AuthContext(
            organization_id=FOREIGN,
            environment="development",
            auth_method="bearer_jwt",
            is_mock_auth=False,
            is_authenticated=True,
        ),
    )
    assert bus.get_failed_events_for_organization(OWNER) == []
    assert bus.get_failed_events_for_organization(FOREIGN) == []


@pytest.mark.asyncio
async def test_generic_emit_and_replay_reject_terminal_success_aliases():
    bus = EventBus()
    terminal_aliases = (
        "submission.sent",
        "SubmissionSent",
        "submissionsent",
        "submission.submitted",
        "jobApplicationSubmitted",
        "submission.completed",
        "submission.success",
        "submission.succeeded",
        "submission.accepted",
        "email.delivery.succeeded",
        "messageDelivered",
        "notification.completed",
        "delivery-delivered",
        "proposal.accepted",
        "winbacksucceeded",
    )

    for event in terminal_aliases:
        with pytest.raises(DeliverySuccessReplayError):
            await bus.emit(event, {})
        with pytest.raises(DeliverySuccessReplayError):
            await bus.replay_event(event, {})

    assert bus._queue.empty()
    assert bus.get_event_stats() == {}

    for event in ("job.accepted", "delivery.access.granted", "submission.created"):
        assert await bus.emit(event, {}) is True
    assert bus._queue.qsize() == 3


def receipt_for(owner: UUID, sent_at: datetime) -> VerifiedJobApplicationReceipt:
    return VerifiedJobApplicationReceipt(
        organization_id=owner,
        opportunity_id=None,
        provider="test_provider",
        external_reference="persisted-reference-1",
        sent_at=sent_at,
    )


async def persist_submission(
    session_factory,
    organization_id: UUID,
    *,
    sent_at: datetime,
    provider: str = "test_provider",
    reference: str = "persisted-reference-1",
    opportunity_id: UUID | None = None,
) -> UUID:
    row = Submission(
        organization_id=organization_id,
        opportunity_id=opportunity_id,
        type="application",
        title="Synthetic test submission",
        status="sent",
        content="Synthetic test content",
        subject_line="Synthetic",
        sent_at=sent_at,
        outcome_notes=json.dumps(
            {"provider": provider, "external_reference": reference},
            sort_keys=True,
        ),
    )
    async with session_factory() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row.id


@pytest.mark.asyncio
async def test_verified_terminal_emit_requires_exact_persisted_receipt(
    session_factory, default_org
):
    bus = EventBus()
    sent_at = datetime.now(UTC).replace(microsecond=0)
    receipt = receipt_for(default_org.id, sent_at)
    submission_id = await persist_submission(
        session_factory, default_org.id, sent_at=sent_at
    )

    assert await bus.emit_verified_submission_sent(
        receipt=receipt,
        submission_id=submission_id,
        organization_id=default_org.id,
    )
    queued = bus._queue.get_nowait()
    assert queued == (
        "submission.sent",
        {
            "submission_id": str(submission_id),
            "opportunity_id": None,
        },
        str(default_org.id),
    )

    mismatches = (
        {"verified": True, "provider_receipt": "forged"},
        replace(receipt, organization_id=FOREIGN),
        replace(receipt, provider="different_provider"),
        replace(receipt, external_reference="different-reference"),
        replace(receipt, sent_at=sent_at + timedelta(seconds=1)),
        replace(receipt, opportunity_id=uuid4()),
    )
    for mismatched_receipt in mismatches:
        with pytest.raises(DeliverySuccessReplayError):
            await bus.emit_verified_submission_sent(
                receipt=mismatched_receipt,
                submission_id=submission_id,
                organization_id=default_org.id,
            )
    with pytest.raises(DeliverySuccessReplayError):
        await bus.emit_verified_submission_sent(
            receipt=receipt,
            submission_id=uuid4(),
            organization_id=default_org.id,
        )
    assert bus._queue.empty()


@pytest.mark.asyncio
async def test_verified_terminal_emit_rejects_persisted_row_for_another_tenant(
    session_factory, default_org
):
    foreign_id = uuid4()
    foreign_org = Organization(
        id=foreign_id,
        name="Synthetic foreign organization",
        slug=f"event-test-{uuid4().hex}",
        status="active",
    )
    sent_at = datetime.now(UTC).replace(microsecond=0)
    async with session_factory() as db:
        db.add(foreign_org)
        await db.commit()
    submission_id = await persist_submission(
        session_factory, foreign_id, sent_at=sent_at
    )
    bus = EventBus()

    with pytest.raises(DeliverySuccessReplayError):
        await bus.emit_verified_submission_sent(
            receipt=receipt_for(default_org.id, sent_at),
            submission_id=submission_id,
            organization_id=default_org.id,
        )
    assert bus._queue.empty()
