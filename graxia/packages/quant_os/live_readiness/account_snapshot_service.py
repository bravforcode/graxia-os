"""
Account Snapshot Service - Phase 3.2

Captures full account state from MT5 as an immutable dataclass.
All values read from MT5, never computed.
SHA-256 hash for change detection.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class AccountSnapshot:
    """
    Immutable snapshot of account state from MT5.

    All values read from MT5, never computed.
    snapshot_hash is SHA-256 for change detection.
    """

    timestamp_utc: datetime
    account_number_redacted: str  # e.g. "****1234"
    server: str
    currency: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    leverage: int
    margin_level: float | None
    profit: Decimal
    open_positions_count: int
    open_orders_count: int
    snapshot_hash: str  # SHA-256


def _compute_snapshot_hash(snapshot: "AccountSnapshot") -> str:
    """
    Compute deterministic SHA-256 hash of all AccountSnapshot fields.
    Uses JSON serialization with sorted keys for determinism.
    """
    d = {
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "account_number_redacted": snapshot.account_number_redacted,
        "server": snapshot.server,
        "currency": snapshot.currency,
        "balance": str(snapshot.balance),
        "equity": str(snapshot.equity),
        "margin": str(snapshot.margin),
        "free_margin": str(snapshot.free_margin),
        "leverage": snapshot.leverage,
        "margin_level": snapshot.margin_level,
        "profit": str(snapshot.profit),
        "open_positions_count": snapshot.open_positions_count,
        "open_orders_count": snapshot.open_orders_count,
    }
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redact_account_number(login: int) -> str:
    """Mask account number to show only last 4 digits."""
    login_str = str(login)
    if len(login_str) > 4:
        return "*" * (len(login_str) - 4) + login_str[-4:]
    return login_str


def take_account_snapshot(readonly_client) -> AccountSnapshot:
    """
    Capture a full account snapshot from MT5 via a read-only client.

    Args:
        readonly_client: Mt5ReadOnlyClient instance (must be initialized).

    Returns:
        AccountSnapshot with all fields populated from MT5.

    Raises:
        Mt5UnavailableError: If MT5 is not accessible.
    """
    acct = readonly_client.get_account_info_redacted()
    positions = readonly_client.get_positions()
    orders = readonly_client.get_orders()

    snapshot = AccountSnapshot(
        timestamp_utc=datetime.now(UTC),
        account_number_redacted=acct["login_redacted"],
        server=acct["server"],
        currency=acct["currency"],
        balance=Decimal(str(acct["balance"])),
        equity=Decimal(str(acct["equity"])),
        margin=Decimal(str(acct["margin"])),
        free_margin=Decimal(str(acct["margin_free"])),
        leverage=acct["leverage"],
        margin_level=acct["margin_level"],
        profit=Decimal(str(acct["profit"])),
        open_positions_count=len(positions),
        open_orders_count=len(orders),
        snapshot_hash="",  # placeholder, computed below
    )

    # Compute hash after all fields are set
    h = _compute_snapshot_hash(snapshot)
    return AccountSnapshot(
        timestamp_utc=snapshot.timestamp_utc,
        account_number_redacted=snapshot.account_number_redacted,
        server=snapshot.server,
        currency=snapshot.currency,
        balance=snapshot.balance,
        equity=snapshot.equity,
        margin=snapshot.margin,
        free_margin=snapshot.free_margin,
        leverage=snapshot.leverage,
        margin_level=snapshot.margin_level,
        profit=snapshot.profit,
        open_positions_count=snapshot.open_positions_count,
        open_orders_count=snapshot.open_orders_count,
        snapshot_hash=h,
    )


def _snapshot_to_dict(snapshot: AccountSnapshot) -> dict:
    """Convert snapshot to JSON-serializable dict."""
    return {
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "account_number_redacted": snapshot.account_number_redacted,
        "server": snapshot.server,
        "currency": snapshot.currency,
        "balance": str(snapshot.balance),
        "equity": str(snapshot.equity),
        "margin": str(snapshot.margin),
        "free_margin": str(snapshot.free_margin),
        "leverage": snapshot.leverage,
        "margin_level": snapshot.margin_level,
        "profit": str(snapshot.profit),
        "open_positions_count": snapshot.open_positions_count,
        "open_orders_count": snapshot.open_orders_count,
        "snapshot_hash": snapshot.snapshot_hash,
    }


def persist_snapshot(snapshot: AccountSnapshot, directory: str) -> str:
    """
    Persist account snapshot as JSON file.

    Args:
        snapshot: AccountSnapshot to persist.
        directory: Directory to write the file.

    Returns:
        Full path to the written JSON file.
    """
    os.makedirs(directory, exist_ok=True)
    ts = snapshot.timestamp_utc.strftime("%Y%m%d_%H%M%S")
    filename = f"account_snapshot_{snapshot.account_number_redacted}_{ts}.json"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(_snapshot_to_dict(snapshot), f, indent=2)
    return filepath
