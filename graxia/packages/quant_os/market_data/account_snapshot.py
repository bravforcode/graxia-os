"""
Account Snapshot for Quant OS

Captures and redacts account information for logging and reporting.
No sensitive data (login, password, server details) is stored in artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class AccountSnapshot:
    """
    Immutable, redacted account snapshot.

    Sensitive fields are masked before storage.
    Suitable for logging and audit trails.
    """
    snapshot_id: str
    captured_at_utc: datetime
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    profit: float
    leverage: int
    currency: str
    server_redacted: str
    login_redacted: str
    open_positions: int
    pending_orders: int

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "snapshot_id": self.snapshot_id,
            "captured_at_utc": self.captured_at_utc.isoformat(),
            "balance": self.balance,
            "equity": self.equity,
            "margin": self.margin,
            "margin_free": self.margin_free,
            "margin_level": self.margin_level,
            "profit": self.profit,
            "leverage": self.leverage,
            "currency": self.currency,
            "server_redacted": self.server_redacted,
            "login_redacted": self.login_redacted,
            "open_positions": self.open_positions,
            "pending_orders": self.pending_orders,
        }


def create_account_snapshot(
    balance: float,
    equity: float,
    margin: float = 0.0,
    margin_free: float = 0.0,
    margin_level: float = 0.0,
    profit: float = 0.0,
    leverage: int = 100,
    currency: str = "USD",
    server: str = "",
    login: str = "",
    open_positions: int = 0,
    pending_orders: int = 0,
    snapshot_id: str = "",
) -> AccountSnapshot:
    """
    Create a redacted account snapshot.

    Server and login are masked: only last 2 chars visible.
    """
    now = datetime.now(timezone.utc)
    sid = snapshot_id or f"snap-{now.strftime('%Y%m%d%H%M%S')}"

    server_redacted = _redact(server) if server else "***"
    login_redacted = _redact(login) if login else "***"

    return AccountSnapshot(
        snapshot_id=sid,
        captured_at_utc=now,
        balance=balance,
        equity=equity,
        margin=margin,
        margin_free=margin_free,
        margin_level=margin_level,
        profit=profit,
        leverage=leverage,
        currency=currency,
        server_redacted=server_redacted,
        login_redacted=login_redacted,
        open_positions=open_positions,
        pending_orders=pending_orders,
    )


def _redact(value: str) -> str:
    """Redact a string, showing only last 2 characters."""
    if len(value) <= 2:
        return "**"
    return "*" * (len(value) - 2) + value[-2:]
