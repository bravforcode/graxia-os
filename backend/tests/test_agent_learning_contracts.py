from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.compound_engine import CompoundEngine
from app.agents.failure_analysis import FailureAnalysis
from app.agents.learning_engine import LearningEngine
from app.agents.playbook_capture import PlaybookCapture
from app.core.domain_events import OpportunityScored
from app.core.event_bus import EventBus
from app.core.value_objects import Score
from app.models.audit import AuditLog
from app.models.cognitive_state import CognitiveState
from app.models.knowledge import KnowledgeItem
from app.models.metric import WeeklyMetric
from app.models.opportunity import Opportunity
from app.models.outcome_pattern import OutcomePattern
from app.models.scoring_weight_history import ScoringWeightHistory
from app.models.submission import Submission
from app.tasks.weekly_review import run_weekly_review


@pytest_asyncio.fixture()
async def agent_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.tasks.weekly_review.AsyncSessionLocal", session_factory)
    yield session_factory


async def _seed_submission_bundle(
    session_factory,
    *,
    title: str,
    submission_status: str,
    lost_reason: str | None = None,
    lost_stage: str | None = None,
    actual_value: Decimal | None = None,
):
    now = datetime.now(timezone.utc)
    async with session_factory() as db:
        existing_state = (
            await db.execute(
                select(CognitiveState).where(CognitiveState.date == date.today()).limit(1)
            )
        ).scalar_one_or_none()
        opportunity = Opportunity(
            type="competition",
            title=title,
            description="Build an AI workflow for SMEs.",
            money_score=8,
            brand_score=7,
            network_score=6,
            startup_score=8,
            effort_score=4,
            total_score=Decimal("7.80"),
            decision="do_now",
            status="approved",
            tags=["ai", "automation"],
            found_at=now,
            acted_on_at=now,
        )
        db.add(opportunity)
        await db.flush()

        submission = Submission(
            opportunity_id=opportunity.id,
            type="proposal",
            title=f"Submission for {title}",
            status=submission_status,
            content="Lead with the business problem, then prove delivery credibility.",
            actual_value=actual_value,
            lost_reason_primary=lost_reason,
            lost_stage=lost_stage,
            created_at=now,
            updated_at=now,
            outcome_at=now,
        )
        db.add(submission)
        if existing_state is None:
            db.add(
                CognitiveState(
                    date=date.today(),
                    energy=8,
                    stress=3,
                    available_hours_this_week=24,
                    exam_pressure=1,
                )
            )
        await db.commit()
        return opportunity.id, submission.id


@pytest.mark.asyncio
async def test_learning_engine_records_outcome_pattern_snapshot(agent_session_factory):
    _, submission_id = await _seed_submission_bundle(
        agent_session_factory,
        title="ASEAN Startup Hackathon",
        submission_status="won",
        actual_value=Decimal("95000.00"),
    )

    agent = LearningEngine()
    await agent.handle_win({"submission_id": submission_id, "actual_value_thb": 95000})

    async with agent_session_factory() as db:
        pattern = (await db.execute(select(OutcomePattern))).scalar_one()
        assert pattern.submission_id == submission_id
        assert pattern.outcome == "positive"
        assert Decimal(pattern.actual_value_thb) == Decimal("95000.00")
        assert pattern.energy_at_time == 8
        assert pattern.opportunity_type == "competition"


@pytest.mark.asyncio
async def test_learning_engine_weekly_analysis_persists_weight_version(agent_session_factory):
    async with agent_session_factory() as db:
        for _ in range(5):
            db.add(
                OutcomePattern(
                    outcome="positive",
                    money_score=9,
                    brand_score=8,
                    network_score=7,
                    startup_score=8,
                    effort_score=3,
                )
            )
        for _ in range(5):
            db.add(
                OutcomePattern(
                    outcome="negative",
                    money_score=3,
                    brand_score=4,
                    network_score=3,
                    startup_score=2,
                    effort_score=8,
                )
            )
        await db.commit()

    result = await LearningEngine().run_weekly_analysis()

    assert result is not None
    assert result["version"] == 1
    assert result["adjustments"]["money"] > 0
    assert result["adjustments"]["effort_inverse"] > 0
    assert pytest.approx(sum(result["weights"].values()), rel=1e-6) == 1.0

    async with agent_session_factory() as db:
        history = (await db.execute(select(ScoringWeightHistory))).scalar_one()
        assert history.changed_by == "learning_engine"
        assert history.is_current is True


@pytest.mark.asyncio
async def test_learning_engine_analyze_loss_returns_heuristic_insight_when_degraded(
    agent_session_factory, monkeypatch
):
    _, submission_id = await _seed_submission_bundle(
        agent_session_factory,
        title="Healthtech Client Proposal",
        submission_status="lost",
        lost_reason="no_reply",
        lost_stage="proposal",
    )
    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: True)

    async with agent_session_factory() as db:
        submission = await db.get(Submission, submission_id)
        insight = await LearningEngine().analyze_loss(submission)

    assert insight["category"] == "execution"
    assert "follow-up" in insight["recommendation"].lower()
    assert "no reply" in insight["key_insight"].lower()


@pytest.mark.asyncio
async def test_playbook_capture_saves_playbook_knowledge_item(
    agent_session_factory, monkeypatch
):
    _, submission_id = await _seed_submission_bundle(
        agent_session_factory,
        title="Thai Retail Automation Grant",
        submission_status="won",
        actual_value=Decimal("120000.00"),
    )
    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: False)
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="- Lead with ROI\n- Show shipped systems\n- Keep scope tight"),
    )
    notify = AsyncMock()
    monkeypatch.setattr("app.telegram_bot.bot.send_message", notify)

    await PlaybookCapture().handle_win(
        {"submission_id": submission_id, "actual_value_thb": 120000}
    )

    async with agent_session_factory() as db:
        item = (
            await db.execute(
                select(KnowledgeItem).where(KnowledgeItem.category == "playbook")
            )
        ).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "playbook.captured")
            )
        ).scalar_one()

    assert "Win:" in item.title
    assert item.metrics_achieved == "120000 THB"
    assert "playbook" in item.tags
    assert audit.triggered_by == "playbook_capture"
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_failure_analysis_saves_loss_lesson(agent_session_factory, monkeypatch):
    _, submission_id = await _seed_submission_bundle(
        agent_session_factory,
        title="SME Dashboard Proposal",
        submission_status="lost",
        lost_reason="too_expensive",
        lost_stage="proposal",
    )
    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: False)
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="Qualify budget earlier and anchor value with ROI."),
    )

    await FailureAnalysis().handle_loss(
        {"submission_id": submission_id, "lost_reason": "too_expensive"}
    )

    async with agent_session_factory() as db:
        item = (
            await db.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.category == "failure_analysis"
                )
            )
        ).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "failure_analysis.captured")
            )
        ).scalar_one()

    assert "Loss:" in item.title
    assert "too_expensive" in item.tags
    assert "ROI" in item.content
    assert audit.triggered_by == "failure_analysis"


@pytest.mark.asyncio
async def test_compound_engine_run_aggregates_weekly_metrics(agent_session_factory, monkeypatch):
    async with agent_session_factory() as db:
        now = datetime.now(timezone.utc)
        win_opportunity = Opportunity(
            type="freelance",
            title="Clinic CRM Automation",
            status="applied",
            total_score=Decimal("8.50"),
            found_at=now,
            acted_on_at=now,
        )
        loss_opportunity = Opportunity(
            type="competition",
            title="University Startup Challenge",
            status="waiting",
            total_score=Decimal("6.80"),
            found_at=now,
        )
        db.add_all([win_opportunity, loss_opportunity])
        await db.flush()
        db.add_all(
            [
                Submission(
                    opportunity_id=win_opportunity.id,
                    type="proposal",
                    status="won",
                    content="Winning proposal",
                    actual_value=Decimal("80000.00"),
                    created_at=now,
                    updated_at=now,
                ),
                Submission(
                    opportunity_id=loss_opportunity.id,
                    type="proposal",
                    status="lost",
                    content="Losing proposal",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await db.commit()

    monkeypatch.setattr("app.core.llm.llm_client.is_degraded", lambda: False)
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="Double down on higher-ticket healthtech automation work."),
    )

    result = await CompoundEngine().run()

    assert result["metrics"]["wins"] == 1
    assert result["metrics"]["losses"] == 1
    assert result["strategy"] == "Double down on higher-ticket healthtech automation work."

    async with agent_session_factory() as db:
        metric = (await db.execute(select(WeeklyMetric))).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "compound_engine.weekly_report")
            )
        ).scalar_one()

    assert metric.opps_found == 2
    assert metric.proposals_won == 1
    assert Decimal(metric.revenue_thb) == Decimal("80000.00")
    assert audit.triggered_by == "compound_engine"


@pytest.mark.asyncio
async def test_event_bus_emits_typed_domain_event_payload():
    bus = EventBus()
    bus.emit = AsyncMock()

    event = OpportunityScored(
        opportunity_id="opp-123",
        score=Score(85),
        reasoning="High fit and strong upside.",
    )

    await bus.emit_domain_event(event)

    bus.emit.assert_awaited_once()
    emitted_name, payload = bus.emit.await_args.args
    assert emitted_name == "opportunity.scored"
    assert payload["data"]["opportunity_id"] == "opp-123"
    assert payload["data"]["score"] == 85


@pytest.mark.asyncio
async def test_weekly_review_summarizes_wins_and_losses(agent_session_factory, monkeypatch):
    won_opportunity_id, _ = await _seed_submission_bundle(
        agent_session_factory,
        title="Winning Opportunity",
        submission_status="won",
        actual_value=Decimal("30000.00"),
    )
    lost_opportunity_id, _ = await _seed_submission_bundle(
        agent_session_factory,
        title="Lost Opportunity",
        submission_status="lost",
        lost_reason="stronger_competitor",
        lost_stage="final_decision",
    )
    notify = AsyncMock()
    monkeypatch.setattr("app.tasks.weekly_review.send_message", notify)

    async def _fake_analyze_loss(self, submission):
        assert submission.opportunity_id in {won_opportunity_id, lost_opportunity_id}
        return {"key_insight": "Differentiate faster and follow up sooner."}

    monkeypatch.setattr(LearningEngine, "analyze_loss", _fake_analyze_loss)

    result = await run_weekly_review()

    assert result == {
        "opportunities": 2,
        "submissions": 2,
        "wins": 1,
        "losses": 1,
    }
    message = notify.await_args.args[0]
    assert "Winning Opportunity" in message
    assert "Lost Opportunity" in message
    assert "Differentiate faster and follow up sooner." in message
