"""Provenance tracking for contract specs and swap assumptions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum


class AssumptionQuality(Enum):
    OBSERVED = "OBSERVED"
    DOCUMENTED_ASSUMPTION = "DOCUMENTED_ASSUMPTION"
    ASSUMED = "ASSUMED"


@dataclass(frozen=True)
class ContractProvenance:
    contract_snapshot_id: str
    contract_valid_from_utc: str
    contract_valid_to_utc: str
    contract_quality: AssumptionQuality
    symbol: str
    trade_contract_size: float
    trade_tick_size: float
    trade_tick_value: float
    volume_step: float
    volume_min: float
    stops_level_points: float


@dataclass(frozen=True)
class SwapProvenance:
    swap_model_id: str
    swap_quality: AssumptionQuality
    rollover_timezone: str
    swap_long_daily: float
    swap_short_daily: float
    rollover_day: int


@dataclass(frozen=True)
class RunProvenance:
    contract: ContractProvenance
    swap: SwapProvenance

    def provenance_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


def create_default_provenance(seed: str = "default") -> RunProvenance:
    return RunProvenance(
        contract=ContractProvenance(
            contract_snapshot_id=f"contract_{seed}",
            contract_valid_from_utc="2024-01-01T00:00:00Z",
            contract_valid_to_utc="2025-12-31T23:59:59Z",
            contract_quality=AssumptionQuality.DOCUMENTED_ASSUMPTION,
            symbol="XAUUSD",
            trade_contract_size=100.0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            volume_step=0.01,
            volume_min=0.01,
            stops_level_points=10.0,
        ),
        swap=SwapProvenance(
            swap_model_id=f"swap_{seed}",
            swap_quality=AssumptionQuality.ASSUMED,
            rollover_timezone="America/New_York",
            swap_long_daily=-2.83,
            swap_short_daily=0.56,
            rollover_day=2,
        ),
    )
