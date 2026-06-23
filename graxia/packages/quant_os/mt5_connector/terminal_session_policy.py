"""Terminal-session-only policy helpers for repo-owned MT5 runtime paths."""

from __future__ import annotations

from typing import Any

import yaml

try:
    from graxia.packages.quant_os.core.config import (
        reject_broker_credential_config,
        reject_broker_credential_env,
    )
except ModuleNotFoundError:
    from core.config import reject_broker_credential_config, reject_broker_credential_env


def load_terminal_session_config(config_path: str) -> dict[str, Any]:
    """Load repo-owned MT5 YAML and fail closed on credential injection."""
    reject_broker_credential_env()
    with open(config_path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"MT5 config must be a mapping: {config_path}")
    reject_broker_credential_config(config, context=f"MT5 config {config_path}")
    mt5_cfg = config.get("mt5")
    if not isinstance(mt5_cfg, dict):
        raise ValueError(f"MT5 config missing 'mt5' mapping: {config_path}")
    return config
