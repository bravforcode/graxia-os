"""Trade ledger — JSON-file trade records with full provenance."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Not JSON serializable: {type(obj)}")


@dataclass
class TradeRecord:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal | None = None
    volume: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    pnl_pct: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    spread_cost: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    close_reason: str = ""
    execution_quality: str = ""
    strategy_id: str = ""
    contract_snapshot_id: str = ""
    risk_policy_version: str = ""
    dataset_manifest_id: str = ""
    cost_scenario: str = ""
    git_commit: str = ""


def _to_serializable(record: TradeRecord) -> dict:
    d = asdict(record)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _from_serializable(data: dict) -> TradeRecord:
    for k in ("entry_price", "exit_price", "volume", "pnl", "pnl_pct",
              "fees", "spread_cost", "slippage_cost"):
        if data.get(k) is not None:
            data[k] = Decimal(str(data[k]))
    for k in ("entry_time", "exit_time"):
        if data.get(k):
            data[k] = datetime.fromisoformat(data[k])
    return TradeRecord(**data)


class TradeLedger:
    __slots__ = ("_records", "_dir")

    def __init__(self, ledger_dir: str = "") -> None:
        self._records: list[TradeRecord] = []
        self._dir = Path(ledger_dir) if ledger_dir else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load_existing()

    def _load_existing(self) -> None:
        if not self._dir:
            return
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                self._records.append(_from_serializable(data))
            except Exception:
                pass

    def record_trade(self, record: TradeRecord) -> str:
        if not record.trade_id:
            object.__setattr__(record, "trade_id", f"t-{uuid.uuid4().hex[:8]}")
        if not record.entry_time:
            object.__setattr__(record, "entry_time", datetime.now(timezone.utc))
        self._records.append(record)
        if self._dir:
            path = self._dir / f"{record.trade_id}.json"
            path.write_text(json.dumps(_to_serializable(record), indent=2, default=_json_default))
        return record.trade_id

    def get_trades(self, symbol: str | None = None, date: str | None = None) -> list[TradeRecord]:
        result = self._records
        if symbol:
            result = [r for r in result if r.symbol == symbol]
        if date:
            result = [r for r in result if r.entry_time and r.entry_time.strftime("%Y-%m-%d") == date]
        return list(result)

    def get_summary(self) -> dict:
        return {
            "total_trades": len(self._records),
            "total_pnl": sum(r.pnl for r in self._records),
            "total_fees": sum(r.fees for r in self._records),
        }

    def ledger_hash(self) -> str:
        combined = "".join(r.trade_id for r in self._records)
        return hashlib.sha256(combined.encode()).hexdigest()

    def get_ambiguous_trades(self) -> list[TradeRecord]:
        return [r for r in self._records if r.close_reason == "AMBIGUOUS"]

    def count(self) -> int:
        return len(self._records)
