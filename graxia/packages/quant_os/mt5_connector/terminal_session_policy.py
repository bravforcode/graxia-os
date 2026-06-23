"""Terminal-session-only policy helpers for repo-owned MT5 runtime paths."""

from __future__ import annotations

from typing import Any

import yaml

from graxia.packages.quant_os.core.config import (
    hash_terminal_session_value,
    reject_broker_credential_config,
)


def load_terminal_session_config(config_path: str) -> dict[str, Any]:
    """Load repo-owned MT5 YAML and fail closed on credential injection."""
    with open(config_path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"MT5 config must be a mapping: {config_path}")
    reject_broker_credential_config(config, context=f"MT5 config {config_path}")
    mt5_cfg = config.get("mt5")
    if not isinstance(mt5_cfg, dict):
        raise ValueError(f"MT5 config missing 'mt5' mapping: {config_path}")
    return config


def redact_account_identity(login: Any, server: Any) -> str:
    """Return log-safe MT5 identity hashes without exposing raw values."""
    login_hash = hash_terminal_session_value(login)
    server_hash = hash_terminal_session_value(server)
    return f"login_sha256={login_hash} server_sha256={server_hash}"
