"""Migrate JSON state (core/state_store.py) to SQLite (data/state_db.py).

Usage:
    from data.state_migration import migrate
    counts = migrate("state/system_state.json")
    print(counts)  # {'orders': 0, 'positions': 0, 'breakers': 0, 'migrated': True}

Handles:
- Field aliasing (id→order_id, quantity→volume, etc.)
- Status normalization (lowercase→UPPERCASE)
- Missing account field (derives from PnL fields)
- Backup of original JSON
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state_db import AccountState, Order, Position, StateDB

logger = logging.getLogger(__name__)


def migrate(
    json_path: str | Path,
    db: StateDB | None = None,
    db_path: str | Path = "data/state/quantos_state.db",
) -> dict[str, int | bool]:
    """Migrate JSON state to SQLite.

    Args:
        json_path: Path to the JSON state file (e.g., "state/system_state.json").
        db: Existing StateDB instance (creates one if None).
        db_path: Path for the SQLite database (used if db is None).

    Returns:
        Dict with migration counts and success flag.
    """
    json_path = Path(json_path)
    if not json_path.exists():
        logger.info("No JSON state file found at %s — nothing to migrate", json_path)
        return {"orders": 0, "positions": 0, "breakers": 0, "migrated": False}

    try:
        text = json_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read JSON state: %s", exc)
        return {"orders": 0, "positions": 0, "breakers": 0, "migrated": False}

    own_db = db is None
    if own_db:
        db = StateDB(db_path)
    assert db is not None  # narrowed for mypy

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        orders_count = 0
        positions_count = 0
        breakers_count = 0

        # ── Migrate orders ────────────────────────────────────────
        raw_orders = data.get("pending_orders", [])
        for raw in raw_orders:
            try:
                order = Order(
                    order_id=_pick(raw, "order_id", "id", "client_order_id", default=_gen_id()),
                    symbol=raw.get("symbol", "UNKNOWN"),
                    side=str(raw.get("side", "BUY")).upper(),
                    volume=float(_pick(raw, "volume", "quantity", "qty", "size", default=0)),
                    order_type=str(_pick(raw, "order_type", "type", default="MARKET")).upper(),
                    requested_price=_to_float(_pick(raw, "requested_price", "price", default=None)),
                    filled_price=_to_float(_pick(raw, "filled_price", "fill_price", default=None)),
                    status=str(_pick(raw, "status", default="PENDING")).upper(),
                    created_at=str(raw.get("created_at", now_iso)),
                    updated_at=str(raw.get("updated_at", now_iso)),
                    venue=str(raw.get("venue", "")),
                    client_tag=str(_pick(raw, "client_tag", "tag", "idempotency_key", default="")),
                    metadata=json.dumps(raw.get("metadata", {}), default=str),
                )
                db.insert_order(order)
                orders_count += 1
            except Exception as exc:
                logger.warning("Failed to migrate order %s: %s", raw, exc)

        # ── Migrate positions ─────────────────────────────────────
        raw_positions = data.get("positions", [])
        for raw in raw_positions:
            try:
                pos = Position(
                    symbol=raw.get("symbol", "UNKNOWN"),
                    side=str(_pick(raw, "side", "position_type", default="FLAT")).upper(),
                    volume=float(_pick(raw, "volume", "quantity", "qty", default=0)),
                    avg_entry_price=float(_pick(raw, "avg_entry_price", "entry_price", default=0)),
                    unrealized_pnl=float(_pick(raw, "unrealized_pnl", "pnl", default=0)),
                    opened_at=str(raw.get("opened_at", now_iso)),
                    updated_at=str(raw.get("updated_at", now_iso)),
                    stop_loss=_to_float(_pick(raw, "stop_loss", "sl", default=None)),
                    take_profit=_to_float(_pick(raw, "take_profit", "tp", default=None)),
                    metadata=json.dumps(raw.get("metadata", {}), default=str),
                )
                db.upsert_position(pos)
                positions_count += 1
            except Exception as exc:
                logger.warning("Failed to migrate position %s: %s", raw, exc)

        # ── Migrate circuit breakers ──────────────────────────────
        raw_breakers = data.get("circuit_breakers", {})
        if isinstance(raw_breakers, dict):
            for name, active in raw_breakers.items():
                try:
                    if active:
                        db.trip_breaker(name, "migrated from JSON state")
                    breakers_count += 1
                except Exception as exc:
                    logger.warning("Failed to migrate breaker %s: %s", name, exc)

        # ── Derive account from PnL fields if not present ─────────
        if "account" in data:
            raw_acc = data["account"]
            db.update_account(AccountState(
                balance=float(raw_acc.get("balance", 0)),
                equity=float(raw_acc.get("equity", 0)),
                margin_used=float(raw_acc.get("margin_used", 0)),
                margin_available=float(raw_acc.get("margin_available", 0)),
                currency=str(raw_acc.get("currency", "USD")),
                leverage=float(raw_acc.get("leverage", 100)),
            ))
        else:
            # Derive minimal account from top-level PnL
            peak = float(data.get("peak_equity", 0))
            db.update_account(AccountState(balance=peak, equity=peak))

        # ── Backup original JSON ──────────────────────────────────
        backup_name = f"{json_path.name}.migrated.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        backup_path = json_path.parent / backup_name
        shutil.copy2(str(json_path), str(backup_path))
        logger.info("Backed up JSON state to %s", backup_path)

        return {
            "orders": orders_count,
            "positions": positions_count,
            "breakers": breakers_count,
            "migrated": True,
        }

    finally:
        if own_db:
            db.close()


# ======================================================================
# Helpers
# ======================================================================


def _pick(d: dict, *keys: str, default: Any = None) -> Any:
    """Return the first value found in dict for the given keys."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _to_float(val: Any) -> float | None:
    """Convert value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _gen_id() -> str:
    """Generate a short unique ID for orders without one."""
    import uuid
    return f"migrated-{uuid.uuid4().hex[:8]}"
