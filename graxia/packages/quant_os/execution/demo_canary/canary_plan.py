"""Immutable Demo Canary Plan. No mutation after creation."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import hashlib
import json

PEPPERSTONE_DEMO_ONLY = "PEPPERSTONE_DEMO_ONLY"
EXECUTION_LIFECYCLE_VALIDATION = "EXECUTION_LIFECYCLE_VALIDATION"

@dataclass(frozen=True)
class DemoCanaryPlan:
    """
    Immutable canary plan.

    Once created and hashed, no field may be changed.
    The generic first canary has NO strategy origin.
    """
    schema_version: str = "1.0"
    canary_id: str = ""
    environment: str = PEPPERSTONE_DEMO_ONLY
    purpose: str = EXECUTION_LIFECYCLE_VALIDATION
    symbol: str = "XAUUSD"
    side: str = "BUY"
    volume: Decimal = Decimal("0.01")
    entry_method: str = "MARKET"
    decision_time_utc: datetime = None
    expiry_utc: datetime = None
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")
    strategy_hash: Optional[str] = None

    def __post_init__(self):
        if self.environment != PEPPERSTONE_DEMO_ONLY:
            raise ValueError(f"Canary must use {PEPPERSTONE_DEMO_ONLY}")
        if self.symbol != "XAUUSD":
            raise ValueError("First canary must be XAUUSD only")
        if self.strategy_hash is not None:
            raise ValueError("Generic first canary must not have a strategy origin")
        if self.volume <= 0:
            raise ValueError("Volume must be positive")

    @property
    def plan_hash(self) -> str:
        """Deterministic SHA-256 over canonical JSON."""
        raw = json.dumps({
            "schema_version": self.schema_version,
            "canary_id": self.canary_id,
            "environment": self.environment,
            "purpose": self.purpose,
            "symbol": self.symbol,
            "side": self.side,
            "volume": str(self.volume),
            "entry_method": self.entry_method,
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "strategy_hash": self.strategy_hash,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def is_expired(self) -> bool:
        if self.expiry_utc is None:
            return False
        now = datetime.now(timezone.utc)
        return now > self.expiry_utc
