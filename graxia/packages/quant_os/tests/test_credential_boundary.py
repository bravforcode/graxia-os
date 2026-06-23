"""
Credential boundary tests — verify no login/password/server fields
leak into config files, dataclasses, or environment loading.
"""
import os
import inspect
import pytest
import yaml

from mt5_connector.connection import MT5Connection
from gold_bot.core.config import BotConfig


def _load_yaml(path: str) -> dict:
    """Load YAML, skip if file missing."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ── 1 ────────────────────────────────────────────────────────────────────

def test_config_yaml_no_credential_keys():
    cfg = _load_yaml("mt5_connector/config.yaml")
    mt5_block = cfg.get("mt5", {})
    for key in ("login", "password", "server"):
        assert key not in mt5_block, f"mt5.{key} must not appear in config.yaml"


# ── 2 ────────────────────────────────────────────────────────────────────

def test_config_template_warns_no_credentials():
    with open("mt5_connector/config_template.yaml", "r", encoding="utf-8") as fh:
        content = fh.read()
    assert "Do not store login" in content, (
        "config_template.yaml must warn against storing login credentials"
    )


# ── 3 ────────────────────────────────────────────────────────────────────

def test_connection_accepts_only_path_and_timeout():
    sig = inspect.signature(MT5Connection.connect)
    params = list(sig.parameters.keys())
    assert params == ["self", "path", "timeout"], (
        f"connect() signature must be (self, path, timeout), got {params}"
    )


# ── 4 ────────────────────────────────────────────────────────────────────

def test_gold_bot_config_no_credential_fields():
    fields = {f.name for f in __import__("dataclasses").fields(BotConfig)}
    banned = {"mt5_login", "mt5_password", "mt5_server"}
    leaked = banned & fields
    assert not leaked, f"BotConfig still contains credential fields: {leaked}"


# ── 5 ────────────────────────────────────────────────────────────────────

def test_env_var_credentials_rejected(monkeypatch):
    """Env vars MT5_LOGIN / MT5_PASSWORD / MT5_SERVER must not populate BotConfig."""
    monkeypatch.setenv("MT5_LOGIN", "12345")
    monkeypatch.setenv("MT5_PASSWORD", "hunter2")
    monkeypatch.setenv("MT5_SERVER", "SomeServer")

    cfg = BotConfig()

    # The credential fields were removed from BotConfig entirely, so the
    # attributes must not exist.  If they somehow were reintroduced, this
    # test catches it and asserts they are still at safe defaults.
    assert not hasattr(cfg, "mt5_login") or cfg.mt5_login == 0, "mt5_login populated from env"
    assert not hasattr(cfg, "mt5_password") or cfg.mt5_password == "", "mt5_password populated from env"
    assert not hasattr(cfg, "mt5_server") or cfg.mt5_server == "", "mt5_server populated from env"
