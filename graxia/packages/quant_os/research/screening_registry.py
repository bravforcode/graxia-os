"""Screening config registry for Direction I (spec §3, A6).

Every screening config is registered BEFORE it runs. ``hash`` dedups
identical configs so N accounting never double-counts. VOID runs are
registered with status="VOID" and still count toward N.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path


def config_hash(mechanism: str, symbol: str, timeframe: str, params: dict, data_range: tuple[str, str]) -> str:
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
    except (json.JSONDecodeError, OSError):
        return []


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
