"""Load RiskPolicy from a config JSON file or dict.

Usage:
    from risk.risk_policy_loader import load_risk_policy

    # From file
    policy = load_risk_policy("config/risk_policy.json")

    # From dict
    policy = load_risk_policy({"risk_per_trade_bps": 10, "max_daily_loss_bps": 50})

    # Defaults (no args)
    policy = load_risk_policy()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .risk_policy import RiskPolicy


def load_risk_policy(source: str | Path | dict[str, Any] | None = None) -> RiskPolicy:
    """Create a RiskPolicy from a JSON file, a dict, or defaults.

    Args:
        source: One of:
            - ``str`` or ``Path``: path to a JSON file containing policy fields.
            - ``dict``: raw field values (any missing keys fall back to defaults).
            - ``None``: return a default RiskPolicy.

    Returns:
        A frozen ``RiskPolicy`` instance.

    Raises:
        FileNotFoundError: if *source* is a path that doesn't exist.
        ValueError: if JSON cannot be decoded or contains unknown fields.
    """
    if source is None:
        return RiskPolicy()

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Risk policy config not found: {path}")
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    elif isinstance(source, dict):
        raw = dict(source)
    else:
        raise TypeError(f"Unsupported source type: {type(source)!r}")

    # Filter to only known RiskPolicy fields (ignore extra keys gracefully)
    import dataclasses
    valid_fields = {f.name for f in dataclasses.fields(RiskPolicy)}
    filtered = {k: v for k, v in raw.items() if k in valid_fields}

    unknown = set(raw.keys()) - valid_fields
    if unknown:
        import logging
        logging.getLogger(__name__).warning(
            "Unknown keys in risk policy config (ignored): %s", sorted(unknown)
        )

    return RiskPolicy(**filtered)


def load_risk_policy_from_config(config_path: str | Path | None = None) -> RiskPolicy:
    """Convenience alias: load RiskPolicy from a config file path.

    This is the primary entry point for production code that loads risk policy
    from a JSON config file. Falls back to defaults if no path provided.

    Args:
        config_path: Path to JSON config file. If None, returns default RiskPolicy.

    Returns:
        A frozen ``RiskPolicy`` instance.
    """
    return load_risk_policy(config_path)
