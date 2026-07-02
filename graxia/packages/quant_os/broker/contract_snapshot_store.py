"""JSON-file-based immutable store for ContractSpec snapshots."""

import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

from .contract_spec import ContractSpec, compute_snapshot_hash


def _decimal_encoder(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class ContractSnapshotStore:
    """
    Saves/loads ContractSpec snapshots as immutable JSON files.
    Storage: data/contract_snapshots/<hash>.json
    """

    def __init__(self, base_dir: str = "data/contract_snapshots"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, spec: ContractSpec) -> str:
        """Save spec and return its snapshot_hash."""
        h = compute_snapshot_hash(spec)
        data = {
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
            "snapshot_hash": h,
        }
        path = self._base_dir / f"{h}.json"
        path.write_text(json.dumps(data, indent=2, default=_decimal_encoder))
        return h

    def load(self, snapshot_hash: str) -> ContractSpec:
        """Load a ContractSpec by its snapshot_hash. Raises FileNotFoundError if missing."""
        path = self._base_dir / f"{snapshot_hash}.json"
        if not path.exists():
            raise FileNotFoundError(f"Snapshot {snapshot_hash} not found")
        data = json.loads(path.read_text())
        return ContractSpec(
            broker=data["broker"],
            server=data["server"],
            symbol=data["symbol"],
            account_currency=data["account_currency"],
            digits=data["digits"],
            point=Decimal(data["point"]),
            trade_contract_size=Decimal(data["trade_contract_size"]),
            trade_tick_size=Decimal(data["trade_tick_size"]),
            trade_tick_value=Decimal(data["trade_tick_value"]),
            volume_min=Decimal(data["volume_min"]),
            volume_max=Decimal(data["volume_max"]),
            volume_step=Decimal(data["volume_step"]),
            stops_level_points=data["stops_level_points"],
            freeze_level_points=data["freeze_level_points"],
            currency_base=data["currency_base"],
            currency_profit=data["currency_profit"],
            currency_margin=data["currency_margin"],
            trade_mode=data["trade_mode"],
            filling_mode=data["filling_mode"],
            execution_mode=data["execution_mode"],
            captured_at_utc=datetime.fromisoformat(data["captured_at_utc"]),
            snapshot_hash=data["snapshot_hash"],
        )

    def exists(self, snapshot_hash: str) -> bool:
        """Check if a snapshot exists."""
        return (self._base_dir / f"{snapshot_hash}.json").exists()
