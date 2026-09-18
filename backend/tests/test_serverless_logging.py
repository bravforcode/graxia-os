from pathlib import Path

from app.core import logging_config


def test_vercel_logging_uses_writable_tmp_dir(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("LOG_DIR", raising=False)

    assert logging_config._default_log_dir() == Path("/tmp/graxia-os-logs")
