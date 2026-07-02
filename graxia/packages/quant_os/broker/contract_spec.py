"""Immutable broker-specific contract specification."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


def _decimal_encoder(obj):
    """JSON encoder that handles Decimal and datetime."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@dataclass(frozen=True)
class ContractSpec:
    """
    Immutable broker-specific contract specification.
    Source of truth: MT5 symbol_info(). Never hardcode.
    """

    broker: str  # e.g. "ICMarketsSC"
    server: str  # e.g. "ICMarketsSC-Demo"
    symbol: str  # e.g. "XAUUSD"
    account_currency: str  # e.g. "USD"

    digits: int
    point: Decimal
    trade_contract_size: Decimal
    trade_tick_size: Decimal
    trade_tick_value: Decimal

    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal

    stops_level_points: int
    freeze_level_points: int

    currency_base: str
    currency_profit: str
    currency_margin: str

    trade_mode: int
    filling_mode: int
    execution_mode: int

    captured_at_utc: datetime
    snapshot_hash: str  # SHA-256 of all fields

    def validate(self) -> list[str]:
        """Validate all required fields. Returns list of errors (empty = valid)."""
        errors = []
        if self.trade_contract_size <= 0:
            errors.append("trade_contract_size must be positive")
        if self.trade_tick_size <= 0:
            errors.append("trade_tick_size must be positive")
        if self.trade_tick_value <= 0:
            errors.append("trade_tick_value must be positive")
        if self.volume_min <= 0:
            errors.append("volume_min must be positive")
        if self.volume_max < self.volume_min:
            errors.append("volume_max must be >= volume_min")
        if self.volume_step <= 0:
            errors.append("volume_step must be positive")
        if self.point <= 0:
            errors.append("point must be positive")
        if self.stops_level_points < 0:
            errors.append("stops_level_points must be non-negative")
        if self.freeze_level_points < 0:
            errors.append("freeze_level_points must be non-negative")
        return errors


def compute_snapshot_hash(spec: ContractSpec) -> str:
    """
    Compute deterministic SHA-256 hash of all ContractSpec fields.
    Uses JSON serialization with sorted keys for determinism.
    """
    d = {
        "broker": spec.broker,
        "server": spec.server,
        "symbol": spec.symbol,
        "account_currency": spec.account_currency,
        "digits": spec.digits,
        "point": str(spec.point),
        "trade_contract_size": str(spec.trade_contract_size),
        "trade_tick_size": str(spec.trade_tick_size),
        "trade_tick_value": str(spec.trade_tick_value),
        "volume_min": str(spec.volume_min),
        "volume_max": str(spec.volume_max),
        "volume_step": str(spec.volume_step),
        "stops_level_points": spec.stops_level_points,
        "freeze_level_points": spec.freeze_level_points,
        "currency_base": spec.currency_base,
        "currency_profit": spec.currency_profit,
        "currency_margin": spec.currency_margin,
        "trade_mode": spec.trade_mode,
        "filling_mode": spec.filling_mode,
        "execution_mode": spec.execution_mode,
        "captured_at_utc": spec.captured_at_utc.isoformat(),
    }
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
