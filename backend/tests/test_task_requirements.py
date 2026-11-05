import asyncio

from app.config import settings
from app.tasks import base
from app.tasks.requirements import TASK_REQUIREMENTS, missing_settings


def test_missing_settings_lists_empty_keys(monkeypatch):
    monkeypatch.setitem(TASK_REQUIREMENTS, "tasks.demo.run", ("RESEND_API_KEY",))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "", raising=False)
    assert missing_settings("tasks.demo.run") == ["RESEND_API_KEY"]


def test_present_settings_are_not_missing(monkeypatch):
    monkeypatch.setitem(TASK_REQUIREMENTS, "tasks.demo.run", ("RESEND_API_KEY",))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test", raising=False)
    assert missing_settings("tasks.demo.run") == []


def test_unknown_task_has_no_requirements():
    assert missing_settings("tasks.not_registered.run") == []


def test_registered_keys_exist_on_settings():
    for task, keys in TASK_REQUIREMENTS.items():
        for key in keys:
            assert hasattr(settings, key), f"{task} requires unknown setting {key}"


def test_managed_run_skips_without_creating_run(monkeypatch):
    monkeypatch.setitem(TASK_REQUIREMENTS, "tasks.demo.run", ("RESEND_API_KEY",))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "", raising=False)
    created = []

    async def fake_create_run(**kwargs):
        created.append(kwargs)

    monkeypatch.setattr(base, "create_run", fake_create_run)

    async def never_called():
        raise AssertionError("coroutine must not run when config is missing")

    result = asyncio.run(base._execute_managed_run("tasks.demo.run", "default", never_called, "scheduler"))
    assert result == {"status": "skipped", "reason": "missing_config", "missing": ["RESEND_API_KEY"]}
    assert created == []
