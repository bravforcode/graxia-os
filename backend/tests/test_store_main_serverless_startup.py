from api import store_main


def test_embedded_scheduler_disabled_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(store_main.settings, "SCHEDULER_EMBEDDED", True)

    assert store_main._should_start_embedded_scheduler() is False


def test_embedded_scheduler_enabled_for_non_vercel_runtime(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(store_main.settings, "SCHEDULER_EMBEDDED", True)

    assert store_main._should_start_embedded_scheduler() is True
