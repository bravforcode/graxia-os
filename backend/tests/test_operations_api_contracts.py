import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.event_bus import event_bus
from app.models.audit import AuditLog
from app.models.assistant_task import AssistantTask
from app.models.automation_run import AutomationRun
from app.models.contact import Contact
from app.models.network_interaction import NetworkInteraction
from app.models.opportunity import Opportunity
from app.models.scraper_health import ScraperHealth


@pytest_asyncio.fixture()
async def operations_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.api.scrapers.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.api.system.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest_asyncio.fixture()
async def isolated_operations_event_bus():
    event_bus.stop()
    event_bus.reset()
    yield event_bus
    event_bus.stop()
    event_bus.reset()


@pytest.mark.asyncio
async def test_events_api_lists_replays_removes_and_clears_failed_events(
    async_client, isolated_operations_event_bus, monkeypatch
):
    event_bus._stats["job.found"] = 2
    event_bus._stats["email.received"] = 1
    event_bus._failed_events.extend(
        [
            ("job.found", {"job_id": "1"}, "timeout"),
            ("email.received", {"thread_id": "2"}, "handler failed"),
        ]
    )
    event_bus._running = True
    monkeypatch.setattr(event_bus, "replay_event", AsyncMock(return_value=None))

    stats_response = await async_client.get("/api/v1/events/stats")
    assert stats_response.status_code == 200
    assert stats_response.json() == {
        "total_events": 3,
        "by_type": {"job.found": 2, "email.received": 1},
    }

    failed_response = await async_client.get("/api/v1/events/failed")
    assert failed_response.status_code == 200
    failed_payload = failed_response.json()
    assert failed_payload["total"] == 2
    assert failed_payload["events"][0]["error"] == "timeout"

    replay_response = await async_client.post("/api/v1/events/replay/0")
    assert replay_response.status_code == 200
    assert replay_response.json()["success"] is True
    event_bus.replay_event.assert_awaited_once_with("job.found", {"job_id": "1"})

    remove_response = await async_client.delete("/api/v1/events/failed/0")
    assert remove_response.status_code == 200
    assert remove_response.json()["success"] is True
    assert len(event_bus.get_failed_events()) == 1

    clear_response = await async_client.delete("/api/v1/events/failed")
    assert clear_response.status_code == 200
    assert clear_response.json() == {"success": True, "cleared": 1}
    assert event_bus.get_failed_events() == []

    health_response = await async_client.get("/api/v1/events/health")
    assert health_response.status_code == 200
    assert health_response.json()["running"] is True
    assert health_response.json()["failed_events"] == 0


@pytest.mark.asyncio
async def test_scrapers_api_reports_health_and_stats(
    async_client, db_session, operations_session_factory
):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ScraperHealth(
                source_name="linkedin",
                last_attempted_at=now - timedelta(minutes=5),
                last_success_at=now - timedelta(minutes=5),
                consecutive_failures=0,
                total_runs=4,
                total_successes=4,
                success_rate=Decimal("100.00"),
                is_muted=False,
                avg_items_per_run=Decimal("7.50"),
            ),
            ScraperHealth(
                source_name="upwork",
                last_attempted_at=now - timedelta(hours=2),
                consecutive_failures=2,
                total_runs=5,
                total_successes=3,
                success_rate=Decimal("60.00"),
                is_muted=False,
                last_error="captcha",
                avg_items_per_run=Decimal("3.20"),
            ),
            ScraperHealth(
                source_name="fiverr",
                last_attempted_at=now - timedelta(days=2),
                consecutive_failures=4,
                total_runs=4,
                total_successes=0,
                success_rate=Decimal("0.00"),
                is_muted=True,
                muted_until=now + timedelta(hours=12),
                last_error="rate limited",
                avg_items_per_run=Decimal("0.00"),
            ),
        ]
    )
    await db_session.commit()

    health_response = await async_client.get("/api/v1/scrapers/health")
    assert health_response.status_code == 200
    health_payload = health_response.json()
    assert health_payload["total_scrapers"] == 3
    assert health_payload["healthy"] == 1
    assert health_payload["unhealthy"] == 2
    assert health_payload["scrapers"][0]["name"] == "fiverr"
    assert health_payload["scrapers"][0]["status"] == "muted"
    assert health_payload["scrapers"][1]["status"] == "success"
    assert health_payload["scrapers"][2]["status"] == "error"

    detail_response = await async_client.get("/api/v1/scrapers/health/linkedin")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["found"] is True
    assert detail_payload["statistics"]["total_runs"] == 4
    assert detail_payload["latest_status"] == "success"

    missing_response = await async_client.get("/api/v1/scrapers/health/does-not-exist")
    assert missing_response.status_code == 200
    assert missing_response.json()["found"] is False

    stats_response = await async_client.get("/api/v1/scrapers/stats")
    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert stats_payload["total_runs"] == 13
    assert stats_payload["successful_runs"] == 7
    assert stats_payload["failed_runs"] == 6
    assert stats_payload["by_scraper"]["linkedin"]["results"] == 7


@pytest.mark.asyncio
async def test_system_api_reports_health_costs_weights_audit_strategy_and_triggers(
    async_client, db_session, monkeypatch, operations_session_factory
):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ScraperHealth(
                source_name="linkedin",
                last_attempted_at=now - timedelta(minutes=10),
                last_success_at=now - timedelta(minutes=10),
                consecutive_failures=0,
                total_runs=3,
                total_successes=3,
                success_rate=Decimal("100.00"),
                is_muted=False,
                avg_items_per_run=Decimal("5.00"),
            ),
            AuditLog(
                action="strategy.generated",
                details={"strategy": "Double down on high-fit enterprise automation work."},
                triggered_by="strategy_agent",
                success=True,
            ),
            AuditLog(
                action="opportunity.scored",
                details={"score": 8.6},
                triggered_by="scorer",
                success=True,
                was_fallback=True,
            ),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(
        "app.api.system.get_runtime_state",
        lambda: {"is_ready": True, "mode": "full", "issues": []},
    )
    monkeypatch.setattr("app.api.system.llm_client.is_degraded", lambda: False)
    monkeypatch.setattr("app.api.system.llm_client.is_cost_paused", lambda: False)
    monkeypatch.setattr(
        "app.api.system.llm_client.get_call_count_today", AsyncMock(return_value=7)
    )
    monkeypatch.setattr("app.api.system.llm_client.get_cost_today_usd", lambda: 0.42)
    monkeypatch.setattr("app.api.system.llm_client.get_cost_month_usd", lambda: 4.2)
    monkeypatch.setattr(
        "app.api.system.llm_client.get_router_summary",
        lambda: {"routing_enabled": True, "max_single_call_cost_usd": 0.25},
    )
    monkeypatch.setattr(
        "app.api.system.identity.get_weight_history",
        AsyncMock(
            return_value=[
                {
                    "id": "w2",
                    "version": 2,
                    "weights": {"money": 0.3},
                    "previous_weights": {"money": 0.25},
                    "changed_by": "learning_engine",
                    "change_reason": "learned from outcomes",
                    "confidence_at_change": 0.82,
                    "data_points_analyzed": 10,
                    "is_current": True,
                    "applied_at": now.isoformat(),
                    "rolled_back_at": None,
                },
                {
                    "id": "w1",
                    "version": 1,
                    "weights": {"money": 0.25},
                    "previous_weights": None,
                    "changed_by": "user",
                    "change_reason": "initial",
                    "confidence_at_change": None,
                    "data_points_analyzed": None,
                    "is_current": False,
                    "applied_at": (now - timedelta(days=1)).isoformat(),
                    "rolled_back_at": None,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "app.api.system.identity.rollback_scoring_weights",
        AsyncMock(return_value={"restored_version": 1, "weights": {"money": 0.25}}),
    )
    reloaded = {"called": False}
    monkeypatch.setattr(
        "app.api.system.identity.reload",
        lambda: reloaded.__setitem__("called", True),
    )
    monkeypatch.setattr("app.api.system.event_bus.get_event_stats", lambda: {"job.found": 4})

    created_runs = []

    async def fake_create_run(**kwargs):
        run_id = uuid4()
        created_runs.append((run_id, kwargs))
        return SimpleNamespace(id=run_id)

    monkeypatch.setattr("app.api.system.create_run", fake_create_run)
    monkeypatch.setattr("app.api.system.mark_run_started", AsyncMock(return_value=None))
    monkeypatch.setattr("app.api.system.mark_run_completed", AsyncMock(return_value=None))
    monkeypatch.setattr("app.api.system.mark_run_failed", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.tasks.daily_scan.run_daily_scan",
        AsyncMock(return_value={"discovered": 3}),
    )
    monkeypatch.setattr(
        "app.agents.briefer.briefer_agent.send_morning_brief",
        AsyncMock(return_value="brief sent"),
    )

    health_response = await async_client.get("/api/v1/system/health")
    assert health_response.status_code == 200
    health_payload = health_response.json()
    assert health_payload["status"] == "full"
    assert health_payload["gemini_calls_today"] == 7
    assert health_payload["scraper_summary"] == {"healthy": 1, "total": 1}
    assert health_payload["event_stats"] == {"job.found": 4}

    costs_response = await async_client.get("/api/v1/system/costs")
    assert costs_response.status_code == 200
    assert costs_response.json()["cost_today_usd"] == 0.42
    assert costs_response.json()["routing_enabled"] is True

    scraper_health_response = await async_client.get("/api/v1/system/scraper-health")
    assert scraper_health_response.status_code == 200
    assert scraper_health_response.json()[0]["source_name"] == "linkedin"

    weights_response = await async_client.get("/api/v1/system/weights")
    assert weights_response.status_code == 200
    assert weights_response.json()["current"]["version"] == 2

    rollback_response = await async_client.post("/api/v1/system/weights/rollback")
    assert rollback_response.status_code == 200
    assert rollback_response.json()["status"] == "rolled_back"
    assert rollback_response.json()["restored_version"] == 1

    audit_response = await async_client.get("/api/v1/system/audit-log", params={"was_fallback": True})
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert len(audit_payload) == 1
    assert audit_payload[0]["action"] == "opportunity.scored"

    reload_response = await async_client.post("/api/v1/system/reload-identity")
    assert reload_response.status_code == 200
    assert reload_response.json() == {"status": "reloaded"}
    assert reloaded["called"] is True

    strategy_response = await async_client.get("/api/v1/system/strategy")
    assert strategy_response.status_code == 200
    assert strategy_response.json()["status"] == "ok"
    assert "enterprise automation" in strategy_response.json()["strategy"]

    scan_response = await async_client.post("/api/v1/system/scan")
    assert scan_response.status_code == 200
    assert scan_response.json()["status"] == "scan_triggered"

    brief_response = await async_client.post("/api/v1/system/brief")
    assert brief_response.status_code == 200
    assert brief_response.json()["status"] == "brief_triggered"

    await asyncio.sleep(0)

    assert len(created_runs) == 2
    assert created_runs[0][1]["task_type"] == "daily_scan"
    assert created_runs[1][1]["task_type"] == "morning_brief"


@pytest.mark.asyncio
async def test_system_stats_are_derived_from_real_tables(
    async_client, db_session, operations_session_factory
):
    now = datetime.now(timezone.utc)
    contact = Contact(
        name="Maya Chen",
        contact_type="lead",
        email="maya@example.com",
        value_score=8,
        created_at=now,
        updated_at=now,
    )
    db_session.add(contact)
    await db_session.flush()
    db_session.add_all(
        [
            Opportunity(
                type="freelance",
                title="Workflow automation build",
                status="found",
                source_hash="stats-opportunity",
                found_at=now,
                updated_at=now,
            ),
            AutomationRun(
                name="Daily scan",
                task_type="daily_scan",
                trigger_source="test",
                status="completed",
                completed_at=now,
                updated_at=now,
            ),
            AutomationRun(
                name="Brief",
                task_type="morning_brief",
                trigger_source="test",
                status="failed",
                error_message="timeout",
                completed_at=now,
                updated_at=now,
            ),
            AssistantTask(
                title="Send proposal",
                status="completed",
                priority=8,
                assigned_to="user",
                created_at=now,
                updated_at=now,
            ),
            NetworkInteraction(
                contact_id=contact.id,
                interaction_type="email_outreach_initial",
                interaction_at=now,
            ),
            AuditLog(
                action="llm.call",
                event_type="ai",
                event_category="llm",
                ai_model_used="test-model",
                success=True,
                created_at=now,
            ),
        ]
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/system/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_leads"] == 1
    assert payload["opportunities_found"] == 1
    assert payload["leads_scanned"] == 2
    assert payload["ai_actions"] == 3
    assert payload["completed_24h"] == 1
    assert payload["failed_24h"] == 1
    assert payload["outreach_sent_24h"] == 1
    assert payload["history"][-1]["success"] == 1
    assert payload["history"][-1]["failed"] == 1
