"""Screening config registry for Direction I (spec §3, A6).

Every screening config is registered BEFORE it runs. ``hash`` dedups
identical configs so N accounting never double-counts. VOID runs are
registered with status="VOID" (via update_config_status) and still count
toward N. Fail-closed: an unreadable log raises instead of being reset,
because a silently-truncated ledger would undercount N for DSR.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path


class ScreeningLogError(RuntimeError):
    """Raised when the screening log exists but cannot be read — fail-closed."""


def config_hash(mechanism: str, symbol: str, timeframe: str, params: dict, data_range: tuple[str, str]) -> str:
    # Normalize inputs so spelling/case variants hash identically (review #6);
    # same convention as research/partition_registry.check_partition.
    mechanism = mechanism.lower().replace(" ", "_")
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    canonical = "|".join(
        [mechanism, symbol, timeframe, json.dumps(params, sort_keys=True), f"{data_range[0]}..{data_range[1]}"]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_configs(log_path: str | Path) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("configs", [])
    except (json.JSONDecodeError, OSError) as exc:
        raise ScreeningLogError(f"unreadable screening log {path}: {exc} — fail-closed, refusing to overwrite") from exc


def _write_log(path: Path, configs: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {"schema_version": "1.0", "direction": "I", "configs": configs, "count": len(configs)},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def register_config(
    log_path: str | Path,
    *,
    mechanism: str,
    symbol: str,
    timeframe: str,
    params: dict,
    data_range: tuple[str, str],
    status: str = "pending",
) -> dict:
    path = Path(log_path)
    configs = load_configs(path)
    h = config_hash(mechanism, symbol, timeframe, params, data_range)
    for cfg in configs:
        if cfg.get("hash") == h:
            return cfg  # already registered — do not double count
    entry = {
        "config_id": uuid.uuid4().hex[:12],
        "hash": h,
        "mechanism": mechanism,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": params,
        "data_range": list(data_range),
        "status": status,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    configs.append(entry)
    _write_log(path, configs)
    return entry


def update_config_status(log_path: str | Path, config_id: str, status: str) -> dict:
    """Transition a registered config's status (pending -> done/VOID, review #2).

    The screening runner calls this after each BacktestEngine.run() so the
    ledger reflects reality (VOID runs still count toward N). Unknown
    config_id raises KeyError — never silently ignored.
    """
    path = Path(log_path)
    configs = load_configs(path)
    for cfg in configs:
        if cfg.get("config_id") == config_id:
            cfg["status"] = status
            cfg["status_updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            _write_log(path, configs)
            return cfg
    raise KeyError(f"config_id={config_id} not found in {path}")
