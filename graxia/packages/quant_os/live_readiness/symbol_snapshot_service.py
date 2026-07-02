"""
Symbol Snapshot Service - Phase 3.2

Captures full symbol state from MT5 as an immutable dataclass.
All values read from MT5, never computed.
SHA-256 hash for change detection.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal


@dataclass(frozen=True)
class SymbolSnapshot:
    """
    Immutable snapshot of symbol state from MT5.

    All values read from MT5, never computed.
    snapshot_hash is SHA-256 for change detection.
    """
    timestamp_utc: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    spread_points: Decimal
    last: Decimal
    volume: int
    digits: int
    point: Decimal
    contract_size: Decimal
    tick_size: Decimal
    tick_value: Decimal
    stops_level: int
    freeze_level: int
    filling_mode: str
    execution_mode: str
    snapshot_hash: str  # SHA-256


_FILLING_MODE_MAP = {
    0: "FOK",
    1: "IOC",
    2: "RETURN",
}


_EXECUTION_MODE_MAP = {
    0: "SYMBOL_TRADE_EXECUTION_MANUAL",
    1: "SYMBOL_TRADE_EXECUTION_INSTANT",
    2: "SYMBOL_TRADE_EXECUTION_REQUEST",
    3: "SYMBOL_TRADE_EXECUTION_BROKER",
}


def _compute_snapshot_hash(snapshot: SymbolSnapshot) -> str:
    """
    Compute deterministic SHA-256 hash of all SymbolSnapshot fields.
    Uses JSON serialization with sorted keys for determinism.
    """
    d = {
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "symbol": snapshot.symbol,
        "bid": str(snapshot.bid),
        "ask": str(snapshot.ask),
        "spread_points": str(snapshot.spread_points),
        "last": str(snapshot.last),
        "volume": snapshot.volume,
        "digits": snapshot.digits,
        "point": str(snapshot.point),
        "contract_size": str(snapshot.contract_size),
        "tick_size": str(snapshot.tick_size),
        "tick_value": str(snapshot.tick_value),
        "stops_level": snapshot.stops_level,
        "freeze_level": snapshot.freeze_level,
        "filling_mode": snapshot.filling_mode,
        "execution_mode": snapshot.execution_mode,
    }
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def take_symbol_snapshot(readonly_client, symbol: str) -> SymbolSnapshot:
    """
    Capture a full symbol snapshot from MT5 via a read-only client.

    Args:
        readonly_client: Mt5ReadOnlyClient instance (must be initialized).
        symbol: Trading symbol (e.g. "XAUUSD").

    Returns:
        SymbolSnapshot with all fields populated from MT5.

    Raises:
        Mt5UnavailableError: If MT5 is not accessible or symbol is invalid.
    """
    tick_data = readonly_client.get_symbol_info_tick(symbol)
    sym_info = readonly_client.get_symbol_info(symbol)

    filling_mode = _FILLING_MODE_MAP.get(
        sym_info["filling_mode"], str(sym_info["filling_mode"])
    )
    execution_mode = _EXECUTION_MODE_MAP.get(
        sym_info["execution_mode"], str(sym_info["execution_mode"])
    )

    bid = Decimal(str(tick_data["bid"]))
    ask = Decimal(str(tick_data["ask"]))
    spread = ask - bid
    # Convert spread to points
    point = Decimal(str(sym_info["point"]))
    spread_points = spread / point if point > 0 else Decimal("0")

    snapshot = SymbolSnapshot(
        timestamp_utc=datetime.now(UTC),
        symbol=symbol,
        bid=bid,
        ask=ask,
        spread_points=spread_points,
        last=Decimal(str(tick_data["last"])),
        volume=int(tick_data["volume"]),
        digits=sym_info["digits"],
        point=point,
        contract_size=Decimal(str(sym_info["trade_contract_size"])),
        tick_size=Decimal(str(sym_info["trade_tick_size"])),
        tick_value=Decimal(str(sym_info["trade_tick_value"])),
        stops_level=sym_info["stops_level"],
        freeze_level=sym_info["freeze_level"],
        filling_mode=filling_mode,
        execution_mode=execution_mode,
        snapshot_hash="",  # placeholder, computed below
    )

    # Compute hash after all fields are set
    h = _compute_snapshot_hash(snapshot)
    return SymbolSnapshot(
        timestamp_utc=snapshot.timestamp_utc,
        symbol=snapshot.symbol,
        bid=snapshot.bid,
        ask=snapshot.ask,
        spread_points=snapshot.spread_points,
        last=snapshot.last,
        volume=snapshot.volume,
        digits=snapshot.digits,
        point=snapshot.point,
        contract_size=snapshot.contract_size,
        tick_size=snapshot.tick_size,
        tick_value=snapshot.tick_value,
        stops_level=snapshot.stops_level,
        freeze_level=snapshot.freeze_level,
        filling_mode=snapshot.filling_mode,
        execution_mode=snapshot.execution_mode,
        snapshot_hash=h,
    )


def _snapshot_to_dict(snapshot: SymbolSnapshot) -> dict:
    """Convert snapshot to JSON-serializable dict."""
    return {
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "symbol": snapshot.symbol,
        "bid": str(snapshot.bid),
        "ask": str(snapshot.ask),
        "spread_points": str(snapshot.spread_points),
        "last": str(snapshot.last),
        "volume": snapshot.volume,
        "digits": snapshot.digits,
        "point": str(snapshot.point),
        "contract_size": str(snapshot.contract_size),
        "tick_size": str(snapshot.tick_size),
        "tick_value": str(snapshot.tick_value),
        "stops_level": snapshot.stops_level,
        "freeze_level": snapshot.freeze_level,
        "filling_mode": snapshot.filling_mode,
        "execution_mode": snapshot.execution_mode,
        "snapshot_hash": snapshot.snapshot_hash,
    }


def persist_snapshot(snapshot: SymbolSnapshot, directory: str) -> str:
    """
    Persist symbol snapshot as JSON file.

    Args:
        snapshot: SymbolSnapshot to persist.
        directory: Directory to write the file.

    Returns:
        Full path to the written JSON file.
    """
    os.makedirs(directory, exist_ok=True)
    ts = snapshot.timestamp_utc.strftime("%Y%m%d_%H%M%S")
    filename = f"symbol_snapshot_{snapshot.symbol}_{ts}.json"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(_snapshot_to_dict(snapshot), f, indent=2)
    return filepath
