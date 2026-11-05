import asyncio
import hashlib
import importlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.sql import operators, visitors
from sqlalchemy.sql.elements import BinaryExpression

from app.models.funnel import ConversionEvent
from app.tasks.schedule import BEAT_SCHEDULE


ORG_A = UUID("10000000-0000-0000-0000-000000000001")
ORG_B = UUID("20000000-0000-0000-0000-000000000002")
SHARED_EMAIL = "same-customer@example.test"


class _FakeWinBackAttemptStore:
    def __init__(self):
        self.claims = []
        self.finishes = []

    async def claim_win_back(self, organization_id, order_id, email, now=None):
        digest = hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()
        claim = SimpleNamespace(
            id=order_id,
            organization_id=organization_id,
            order_id=order_id,
            email_digest=digest,
            key=f"win_back:{organization_id}:{digest}:order:{order_id}",
            acquired=True,
        )
        self.claims.append(claim)
        return claim

    async def finish_win_back(self, claim, outcome, provider_reference=None):
        self.finishes.append((claim, outcome, provider_reference))


def test_unsafe_telegram_notifications_are_absent_but_job_discovery_stays_scheduled():
    scheduled_tasks = {entry["task"] for entry in BEAT_SCHEDULE.values()}

    assert "tasks.morning_briefing.run" not in scheduled_tasks
    assert "tasks.follow_up_check.run" not in scheduled_tasks
    assert "tasks.weekly_review.run" not in scheduled_tasks
    assert "tasks.outreach.email" not in scheduled_tasks
    assert BEAT_SCHEDULE["job-discovery-frequent"]["task"] == "tasks.job_discovery.run"


@pytest.mark.parametrize(
    ("module_name", "coroutine_name", "task_name"),
    [
        ("app.tasks.morning_briefing", "send_morning_briefing", "morning_briefing_task"),
        ("app.tasks.follow_up_check", "run_follow_up_check", "follow_up_check_task"),
        ("app.tasks.weekly_review", "run_weekly_review", "weekly_review_task"),
    ],
)
@pytest.mark.asyncio
async def test_already_queued_notification_entry_points_fail_closed_before_work(
    module_name, coroutine_name, task_name, monkeypatch
):
    module = importlib.import_module(module_name)
    database = Mock(side_effect=AssertionError("notification task touched database"))
    telegram_send = AsyncMock(side_effect=AssertionError("notification task sent Telegram"))
    run_record = AsyncMock(side_effect=AssertionError("notification task created a run"))
    monkeypatch.setattr("app.database.AsyncSessionLocal", database)
    monkeypatch.setattr("app.telegram_bot.bot.send_message", telegram_send)
    monkeypatch.setattr("app.tasks.base.create_run", run_record)

    calls = (
        ({}, "tenant_and_authorized_recipient_required"),
        (
            {
                "organization_id": str(ORG_A),
                "telegram_user_id": "12345",
                "telegram_chat_id": "12345",
            },
            "tenant_scoped_delivery_not_enabled",
        ),
    )
    for kwargs, reason in calls:
        coroutine_result = await getattr(module, coroutine_name)(**kwargs)
        task_result = getattr(module, task_name).run(**kwargs)
        assert coroutine_result == {"status": "disabled", "reason": reason}
        assert task_result == {"status": "disabled", "reason": reason}

    database.assert_not_called()
    run_record.assert_not_awaited()
    telegram_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_outreach_task_without_trusted_auth_does_no_database_or_provider_work(
    monkeypatch,
):
    module = importlib.import_module("app.tasks.outreach_tasks")
    database = Mock(side_effect=AssertionError("outreach task touched database"))
    provider_send = AsyncMock(side_effect=AssertionError("outreach sent email"))
    approval_queue = AsyncMock(side_effect=AssertionError("outreach queued approval"))
    monkeypatch.setattr("app.database.AsyncSessionLocal", database)
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )
    monkeypatch.setattr("app.core.control_plane.queue_approval_request", approval_queue)

    agent_result = await module.run_outreach_email()
    task_result = module.outreach_email_task.run()

    assert agent_result == {
        "status": "blocked",
        "reason": "trusted_auth_context_required",
    }
    assert task_result == {
        "status": "disabled",
        "reason": "trusted_auth_context_required",
    }
    database.assert_not_called()
    provider_send.assert_not_awaited()
    approval_queue.assert_not_awaited()


def test_job_discovery_task_keeps_agent_ingestion_without_telegram_sends(monkeypatch):
    module = importlib.import_module("app.tasks.job_discovery")
    result = {"discovered": 7, "new": 6, "duplicates": 1, "errors": []}
    agent = SimpleNamespace(run=AsyncMock(return_value=result))
    telegram_send = AsyncMock(side_effect=AssertionError("job discovery sent Telegram"))
    monkeypatch.setattr(module, "job_hunter_agent", agent)
    monkeypatch.setattr("app.telegram_bot.bot.send_message", telegram_send)
    monkeypatch.setattr(
        module,
        "execute_managed_async_task",
        lambda **kwargs: asyncio.run(kwargs["coroutine_factory"]()),
    )
    monkeypatch.setattr("app.tasks.base._acquire_task_lock", lambda *_args: True)
    monkeypatch.setattr("app.tasks.base._release_task_lock", lambda *_args: None)

    task_result = module.job_discovery_task.run()
    assert task_result == result
    agent.run.assert_awaited_once()
    telegram_send.assert_not_awaited()

    agent.run.side_effect = RuntimeError("offline scraper failure")
    with pytest.raises(RuntimeError, match="offline scraper failure"):
        asyncio.run(module.run_job_discovery())
    telegram_send.assert_not_awaited()


def _assert_recent_event_query_is_organization_scoped(statement):
    where = statement.whereclause
    assert where is not None
    assert any(
        isinstance(node, BinaryExpression)
        and getattr(node.left, "name", None) == "organization_id"
        and getattr(getattr(node.left, "table", None), "name", None)
        == ConversionEvent.__tablename__
        and node.operator in (operators.in_op, operators.eq)
        for node in visitors.iterate(where)
    )


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _OfflineSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.statements = []
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(next(self.responses))

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None


def test_celery_win_back_suppression_is_per_organization_without_provider_calls(
    monkeypatch,
):
    module = importlib.import_module("app.tasks.funnel_automation_tasks")
    inactive = [
        SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_A, order_id=UUID(int=1)),
        SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_B, order_id=UUID(int=2)),
    ]
    recent_events = [(ORG_A, {"email": SHARED_EMAIL})]
    db = _OfflineSession([inactive, recent_events])
    attempts = _FakeWinBackAttemptStore()
    service = SimpleNamespace(
        trigger_win_back=AsyncMock(
            return_value={"status": "sent", "id": "offline-accepted"}
        )
    )
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(
        "app.services.automation_email_service.AutomationEmailService",
        lambda _db: service,
    )
    monkeypatch.setattr(
        "app.services.delivery_email_attempts.DeliveryEmailAttemptStore",
        lambda: attempts,
    )

    module.send_win_back_emails.run()

    _assert_recent_event_query_is_organization_scoped(db.statements[1])
    service.trigger_win_back.assert_awaited_once()
    assert service.trigger_win_back.await_args.kwargs["organization_id"] == ORG_B
    email_digest = hashlib.sha256(SHARED_EMAIL.encode("utf-8")).hexdigest()
    assert service.trigger_win_back.await_args.kwargs["idempotency_key"] == (
        f"win_back:{ORG_B}:{email_digest}:order:{UUID(int=2)}"
    )
    assert db.added == []
    assert [(item[0].organization_id, item[1], item[2]) for item in attempts.finishes] == [
        (ORG_B, "sent", "offline-accepted")
    ]


def test_celery_win_back_suppressed_result_is_not_recorded_or_counted(
    monkeypatch, caplog
):
    module = importlib.import_module("app.tasks.funnel_automation_tasks")
    inactive = [SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_A, order_id=UUID(int=3))]
    db = _OfflineSession([inactive, []])
    attempts = _FakeWinBackAttemptStore()
    service = SimpleNamespace(
        trigger_win_back=AsyncMock(return_value={"status": "suppressed", "id": None})
    )
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(
        "app.services.automation_email_service.AutomationEmailService",
        lambda _db: service,
    )
    monkeypatch.setattr(
        "app.services.delivery_email_attempts.DeliveryEmailAttemptStore",
        lambda: attempts,
    )

    with caplog.at_level("INFO", logger="graxia.tasks.funnel_automation"):
        module.send_win_back_emails.run()

    service.trigger_win_back.assert_awaited_once()
    assert db.added == []
    assert [(item[1], item[2]) for item in attempts.finishes] == [("suppressed", None)]
    assert "Win-back emails sent: 0/1" in caplog.text


@pytest.mark.parametrize("task_path", ["celery", "runtime"])
def test_win_back_batch_skips_unicode_blank_recipient_and_processes_next(
    task_path, monkeypatch
):
    import app.services.automation_email_service as automation_email_service

    candidates = [
        SimpleNamespace(customer_email="\u2003 \t", organization_id=ORG_A, order_id=UUID(int=7)),
        SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_A, order_id=UUID(int=8)),
    ]
    db = _OfflineSession([candidates, []])
    attempts = _FakeWinBackAttemptStore()
    service = SimpleNamespace(
        trigger_win_back=AsyncMock(return_value={"status": "sent", "id": "offline-accepted"})
    )
    sql = str(
        automation_email_service.win_back_candidates_statement(datetime.now(UTC))
    ).lower()
    assert "trim(" in sql

    if task_path == "celery":
        module = importlib.import_module("app.tasks.funnel_automation_tasks")
        monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)
        monkeypatch.setattr(
            "app.services.automation_email_service.AutomationEmailService",
            lambda _db: service,
        )
        monkeypatch.setattr(
            "app.services.delivery_email_attempts.DeliveryEmailAttemptStore",
            lambda: attempts,
        )
        module.send_win_back_emails.run()
    else:
        module = importlib.import_module("app.tasks.funnel_automation_runtime")
        monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db)
        monkeypatch.setattr(module, "AutomationEmailService", lambda _db: service)
        monkeypatch.setattr(module, "DeliveryEmailAttemptStore", lambda: attempts)
        sent = asyncio.run(module.scan_win_backs())
        assert sent == 1

    assert len(attempts.claims) == 1
    assert attempts.claims[0].order_id == UUID(int=8)
    service.trigger_win_back.assert_awaited_once()
    assert service.trigger_win_back.await_args.kwargs["customer_email"] == SHARED_EMAIL
    assert [(item[1], item[2]) for item in attempts.finishes] == [
        ("sent", "offline-accepted")
    ]


@pytest.mark.asyncio
async def test_win_back_idempotency_key_uses_claim_cycle_org_and_digest(monkeypatch):
    from app.services.automation_email_service import AutomationEmailService

    service = AutomationEmailService(db=object())
    send = AsyncMock(return_value={"status": "sent", "id": "offline-accepted"})
    monkeypatch.setattr(service, "_send", send)

    await service.trigger_win_back(
        organization_id=ORG_A,
        customer_email=f" {SHARED_EMAIL.upper()} ",
        customer_name="Customer",
        idempotency_key=f"win_back:{ORG_A}:{hashlib.sha256(SHARED_EMAIL.encode()).hexdigest()}:order:cycle_a",
    )
    await service.trigger_win_back(
        organization_id=ORG_A,
        customer_email=SHARED_EMAIL,
        customer_name="Customer",
        idempotency_key=f"win_back:{ORG_A}:{hashlib.sha256(SHARED_EMAIL.encode()).hexdigest()}:order:cycle_a",
    )
    await service.trigger_win_back(
        organization_id=ORG_A,
        customer_email=SHARED_EMAIL,
        customer_name="Customer",
        idempotency_key=f"win_back:{ORG_A}:{hashlib.sha256(SHARED_EMAIL.encode()).hexdigest()}:receipt:prior_receipt",
    )
    await service.trigger_win_back(
        organization_id=ORG_B,
        customer_email=SHARED_EMAIL,
        customer_name="Customer",
        idempotency_key=f"win_back:{ORG_B}:{hashlib.sha256(SHARED_EMAIL.encode()).hexdigest()}:order:cycle_b",
    )

    keys = [call.kwargs["idempotency_key"] for call in send.await_args_list]
    digest = hashlib.sha256(SHARED_EMAIL.casefold().encode("utf-8")).hexdigest()
    assert keys == [
        f"win_back:{ORG_A}:{digest}:order:cycle_a",
        f"win_back:{ORG_A}:{digest}:order:cycle_a",
        f"win_back:{ORG_A}:{digest}:receipt:prior_receipt",
        f"win_back:{ORG_B}:{digest}:order:cycle_b",
    ]
    assert all(SHARED_EMAIL not in key for key in keys)


@pytest.mark.asyncio
async def test_runtime_win_back_suppression_is_per_organization_without_provider_calls(
    monkeypatch,
):
    module = importlib.import_module("app.tasks.funnel_automation_runtime")
    inactive = [
        SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_A, order_id=UUID(int=4)),
        SimpleNamespace(customer_email=SHARED_EMAIL, organization_id=ORG_B, order_id=UUID(int=5)),
    ]
    recent_events = [(ORG_A, {"email": SHARED_EMAIL})]
    db = _OfflineSession([inactive, recent_events])
    attempts = _FakeWinBackAttemptStore()
    service = SimpleNamespace(
        trigger_win_back=AsyncMock(return_value={"id": "offline-receipt"})
    )
    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(module, "AutomationEmailService", lambda _db: service)
    monkeypatch.setattr(module, "DeliveryEmailAttemptStore", lambda: attempts)
    monkeypatch.setattr(module, "email_accepted", lambda _result: True)

    sent = await module.scan_win_backs()

    _assert_recent_event_query_is_organization_scoped(db.statements[1])
    assert sent == 1
    service.trigger_win_back.assert_awaited_once()
    assert service.trigger_win_back.await_args.kwargs["organization_id"] == ORG_B
    email_digest = hashlib.sha256(SHARED_EMAIL.encode("utf-8")).hexdigest()
    assert service.trigger_win_back.await_args.kwargs["idempotency_key"] == (
        f"win_back:{ORG_B}:{email_digest}:order:{UUID(int=5)}"
    )
    assert db.added == []
    assert [(item[0].organization_id, item[1], item[2]) for item in attempts.finishes] == [
        (ORG_B, "sent", "offline-receipt")
    ]


@pytest.mark.asyncio
async def test_welcome_idempotency_key_is_org_scoped_and_hashed(monkeypatch):
    from app.services.automation_email_service import AutomationEmailService

    service = AutomationEmailService(db=object())
    send = AsyncMock(return_value={"status": "sent", "id": "offline-accepted"})
    monkeypatch.setattr(service, "_send", send)

    await service.trigger_welcome(
        organization_id=ORG_A,
        customer_email=f" {SHARED_EMAIL.upper()} ",
        customer_name="Customer",
    )
    await service.trigger_welcome(
        organization_id=ORG_A,
        customer_email=SHARED_EMAIL,
        customer_name="Customer",
    )
    await service.trigger_welcome(
        organization_id=ORG_B,
        customer_email=SHARED_EMAIL,
        customer_name="Customer",
    )

    keys = [call.kwargs["idempotency_key"] for call in send.await_args_list]
    digest = hashlib.sha256(SHARED_EMAIL.casefold().encode("utf-8")).hexdigest()
    assert keys == [
        f"welcome:{ORG_A}:{digest}",
        f"welcome:{ORG_A}:{digest}",
        f"welcome:{ORG_B}:{digest}",
    ]
    assert all(SHARED_EMAIL not in key for key in keys)


@pytest.mark.parametrize("task_path", ["celery", "runtime"])
@pytest.mark.parametrize("metadata_kind", ["legacy", "digest"])
def test_win_back_dedup_normalizes_legacy_and_digest_events(
    task_path, metadata_kind, monkeypatch
):
    candidate_email = f" \t{SHARED_EMAIL.upper()} "
    digest = hashlib.sha256(SHARED_EMAIL.casefold().encode("utf-8")).hexdigest()
    metadata = (
        {"email": SHARED_EMAIL}
        if metadata_kind == "legacy"
        else {"email_digest": digest}
    )
    inactive = [
        SimpleNamespace(customer_email=candidate_email, organization_id=ORG_A, order_id=UUID(int=6))
    ]
    db = _OfflineSession([inactive, [(ORG_A, metadata)]])
    service = SimpleNamespace(
        trigger_win_back=AsyncMock(
            return_value={"status": "sent", "id": "offline-accepted"}
        )
    )
    attempts = _FakeWinBackAttemptStore()

    if task_path == "celery":
        module = importlib.import_module("app.tasks.funnel_automation_tasks")
        monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)
        monkeypatch.setattr(
            "app.services.automation_email_service.AutomationEmailService",
            lambda _db: service,
        )
        monkeypatch.setattr(
            "app.services.delivery_email_attempts.DeliveryEmailAttemptStore",
            lambda: attempts,
        )
        module.send_win_back_emails.run()
    else:
        module = importlib.import_module("app.tasks.funnel_automation_runtime")
        monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db)
        monkeypatch.setattr(module, "AutomationEmailService", lambda _db: service)
        monkeypatch.setattr(module, "DeliveryEmailAttemptStore", lambda: attempts)
        monkeypatch.setattr(module, "email_accepted", lambda _result: True)
        assert asyncio.run(module.scan_win_backs()) == 0

    _assert_recent_event_query_is_organization_scoped(db.statements[1])
    service.trigger_win_back.assert_not_awaited()
    assert db.added == []
