import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.briefer import Briefer
from app.agents.decision_engine import DecisionEngine
from app.agents.drafter import Drafter
from app.agents.scorer import Scorer
from app.core.bootstrap import wire_event_handlers
from app.core.event_bus import event_bus
from app.models.approval_request import ApprovalRequest
from app.models.audit import AuditLog
from app.models.cognitive_state import CognitiveState
from app.models.content_draft import ContentDraft
from app.models.metric import WeeklyMetric
from app.models.opportunity import Opportunity
from app.models.submission import Submission


@pytest_asyncio.fixture()
async def tactical_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.core.control_plane.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest_asyncio.fixture()
async def isolated_event_bus():
    event_bus.stop()
    event_bus.reset()
    yield event_bus
    event_bus.stop()
    event_bus.reset()


async def _create_opportunity(
    session_factory,
    *,
    title: str = "AI Operations Grant",
    opp_type: str = "competition",
    total_score: Decimal | None = None,
    action_priority: str | None = None,
    decision: str | None = None,
    decision_confidence: Decimal | None = None,
    deadline: date | None = None,
    status: str = "found",
):
    now = datetime.now(timezone.utc)
    async with session_factory() as db:
        opportunity = Opportunity(
            type=opp_type,
            title=title,
            description="Automate SME operations with AI and dashboards.",
            source_platform="devpost",
            deadline=deadline,
            money_score=8 if total_score is not None else None,
            brand_score=7 if total_score is not None else None,
            network_score=6 if total_score is not None else None,
            startup_score=8 if total_score is not None else None,
            effort_score=4 if total_score is not None else None,
            total_score=total_score,
            action_priority=action_priority,
            decision=decision,
            decision_confidence=decision_confidence,
            decision_reasoning="Strong upside." if decision else None,
            scoring_rationale="High fit." if total_score is not None else None,
            fit_summary="Strong fit with healthtech and automation goals.",
            status=status,
            prize_amount="120000 THB",
            tags=["ai", "startup"],
            location_type="global",
            is_student_eligible=True,
            found_at=now,
        )
        db.add(opportunity)
        await db.commit()
        await db.refresh(opportunity)
        return opportunity.id


@pytest.mark.asyncio
async def test_scorer_heuristic_scores_and_emits_event(
    tactical_session_factory, isolated_event_bus, monkeypatch
):
    opportunity_id = await _create_opportunity(
        tactical_session_factory,
        deadline=date.today() + timedelta(days=2),
    )
    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: True)
    emit_domain_event = AsyncMock()
    monkeypatch.setattr(event_bus, "emit_domain_event", emit_domain_event)

    await Scorer()._score_opportunity(opportunity_id)

    async with tactical_session_factory() as db:
        opportunity = await db.get(Opportunity, opportunity_id)
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "opportunity.scored")
            )
        ).scalar_one()

    assert opportunity.total_score is not None
    assert opportunity.status == "scored"
    assert opportunity.action_priority in {"do_now", "queue", "skip"}
    assert audit.was_fallback is True
    emit_domain_event.assert_awaited_once()
    event = emit_domain_event.await_args.args[0]
    assert event.opportunity_id == str(opportunity_id)
    assert event.action_priority == opportunity.action_priority


@pytest.mark.asyncio
async def test_decision_engine_rule_based_path_sets_do_now(
    tactical_session_factory, isolated_event_bus, monkeypatch
):
    opportunity_id = await _create_opportunity(
        tactical_session_factory,
        total_score=Decimal("8.80"),
        action_priority="do_now",
        deadline=date.today() + timedelta(days=1),
        status="scored",
    )
    monkeypatch.setattr(event_bus, "emit", AsyncMock())

    await DecisionEngine()._decide(opportunity_id)

    async with tactical_session_factory() as db:
        opportunity = await db.get(Opportunity, opportunity_id)
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "opportunity.decided")
            )
        ).scalar_one()

    assert opportunity.decision == "do_now"
    assert float(opportunity.decision_confidence) >= 0.9
    assert opportunity.status == "decided"
    assert audit.details["decision"] == "do_now"


@pytest.mark.asyncio
async def test_drafter_creates_single_draft_and_approval_request(
    tactical_session_factory, isolated_event_bus, monkeypatch
):
    opportunity_id = await _create_opportunity(
        tactical_session_factory,
        total_score=Decimal("8.40"),
        action_priority="do_now",
        decision="do_now",
        decision_confidence=Decimal("0.91"),
        status="decided",
    )
    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: False)
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="Concrete draft with proof, scope, and CTA."),
    )
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.control_plane.send_message", notify)

    agent = Drafter()
    await agent._draft_for_opportunity(opportunity_id)
    await agent._draft_for_opportunity(opportunity_id)

    async with tactical_session_factory() as db:
        drafts = list((await db.execute(select(ContentDraft))).scalars())
        approvals = list((await db.execute(select(ApprovalRequest))).scalars())
        audit = (
            await db.execute(select(AuditLog).where(AuditLog.action == "draft.created"))
        ).scalar_one()

    assert len(drafts) == 1
    assert drafts[0].status == "pending"
    assert drafts[0].opportunity_id == opportunity_id
    assert len(approvals) == 1
    assert approvals[0].subject_id == drafts[0].id
    assert audit.details["draft_type"] == drafts[0].type
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_briefer_generates_contextual_message(
    tactical_session_factory, isolated_event_bus, monkeypatch
):
    now = datetime.now(timezone.utc)
    opportunity_id = await _create_opportunity(
        tactical_session_factory,
        title="Top Opportunity",
        total_score=Decimal("8.10"),
        action_priority="do_now",
        decision="do_now",
        decision_confidence=Decimal("0.93"),
        deadline=date.today() + timedelta(days=3),
        status="decided",
    )

    async with tactical_session_factory() as db:
        db.add(
            CognitiveState(
                date=date.today(),
                energy=2,
                stress=4,
                available_hours_this_week=10,
                exam_pressure=2,
            )
        )
        db.add(
            ContentDraft(
                type="proposal",
                title="Pending Draft",
                content="Preview",
                status="pending",
                opportunity_id=opportunity_id,
            )
        )
        db.add(
            Submission(
                opportunity_id=opportunity_id,
                type="proposal",
                status="sent",
                content="Submitted proposal",
                follow_up_date=date.today(),
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            WeeklyMetric(
                week_start=date.today() - timedelta(days=date.today().weekday()),
                revenue_thb=Decimal("55000.00"),
            )
        )
        db.add(
            AuditLog(
                action="strategy.generated",
                details={"strategy": "Double down on high-fit automation work this week."},
                triggered_by="strategy_agent",
                success=True,
            )
        )
        await db.commit()

    notify = AsyncMock(return_value=True)
    monkeypatch.setattr("app.telegram_bot.bot.send_message", notify)

    message = await Briefer().send_morning_brief()

    assert message is not None
    assert "Low energy day" in message
    assert "Top Opportunity" in message
    assert "55,000 THB" in message
    assert "Double down on high-fit automation work this week." in message
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_pipeline_scores_decides_and_creates_draft(
    tactical_session_factory, isolated_event_bus, monkeypatch
):
    opportunity_id = await _create_opportunity(
        tactical_session_factory,
        title="Pipeline Opportunity",
        deadline=date.today() + timedelta(days=1),
        status="found",
    )

    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: False)

    async def fake_complete_json(*, system, user, **kwargs):
        if '"money_score"' in user:
            return {
                "money_score": 9,
                "brand_score": 8,
                "network_score": 7,
                "startup_score": 8,
                "effort_score": 4,
                "total_score": 8.6,
                "action_priority": "do_now",
                "scoring_rationale": "High fit and strong upside.",
                "red_flags": [],
                "deadline_urgency": "critical",
            }
        raise AssertionError("DecisionEngine should not need LLM for this urgent high-score case")

    monkeypatch.setattr("app.core.llm.llm_client.complete_json", fake_complete_json)
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="Enterprise-grade draft with proof and a concrete delivery plan."),
    )
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.control_plane.send_message", notify)
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock(return_value=True))

    wire_event_handlers()
    processor = asyncio.create_task(event_bus.start_processing())
    try:
        await event_bus.emit("opportunity.found", {"opportunity_id": str(opportunity_id)})
        await asyncio.wait_for(event_bus._queue.join(), timeout=3)
    finally:
        event_bus.stop()
        processor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processor

    async with tactical_session_factory() as db:
        opportunity = await db.get(Opportunity, opportunity_id)
        draft = (
            await db.execute(
                select(ContentDraft).where(ContentDraft.opportunity_id == opportunity_id)
            )
        ).scalar_one()
        approval = (
            await db.execute(
                select(ApprovalRequest).where(ApprovalRequest.subject_id == draft.id)
            )
        ).scalar_one()

    assert opportunity.status == "decided"
    assert opportunity.decision == "do_now"
    assert draft.status == "pending"
    assert "Enterprise-grade draft" in draft.content
    assert approval.action_type == "draft_review"
    notify.assert_awaited_once()
