"""Structured record arrays from vectorbt pattern for efficient trade storage"""

import json
from dataclasses import dataclass


@dataclass
class TradeRecord:
    """Memory-efficient trade record"""

    id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    exit_price: float | None
    quantity: float
    entry_time: float  # timestamp
    exit_time: float | None
    pnl: float = 0.0
    fees: float = 0.0
    exit_reason: str = ""
    strategy_id: str = ""


class TradeRecords:
    """
    Efficient trade storage using structured approach.

    Usage:
        records = TradeRecords()
        records.add(TradeRecord(...))

        # Query
        winners = records.filter(pnl > 0)
        by_strategy = records.group_by("strategy_id")

        # Export
        records.to_csv("trades.csv")
        records.to_json("trades.json")
    """

    def __init__(self):
        self._records: list[TradeRecord] = []

    def add(self, record: TradeRecord):
        """Add a trade record"""
        self._records.append(record)

    def filter(self, **kwargs) -> list[TradeRecord]:
        """Filter records by field values"""
        result = self._records
        for key, value in kwargs.items():
            result = [r for r in result if getattr(r, key, None) == value]
        return result

    def group_by(self, field: str) -> dict[str, list[TradeRecord]]:
        """Group records by field value"""
        groups = {}
        for record in self._records:
            key = str(getattr(record, field, "unknown"))
            if key not in groups:
                groups[key] = []
            groups[key].append(record)
        return groups

    def to_list(self) -> list[dict]:
        """Convert to list of dicts"""
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "side": r.side,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "quantity": r.quantity,
                "entry_time": r.entry_time,
                "exit_time": r.exit_time,
                "pnl": r.pnl,
                "fees": r.fees,
                "exit_reason": r.exit_reason,
                "strategy_id": r.strategy_id,
            }
            for r in self._records
        ]

    def to_csv(self, filepath: str):
        """Export to CSV"""
        if not self._records:
            return

        headers = list(self.to_list()[0].keys())
        with open(filepath, "w") as f:
            f.write(",".join(headers) + "\n")
            for record in self._records:
                row = [str(getattr(record, h, "")) for h in headers]
                f.write(",".join(row) + "\n")

    def to_json(self, filepath: str):
        """Export to JSON"""
        with open(filepath, "w") as f:
            json.dump(self.to_list(), f, indent=2)

    @property
    def count(self) -> int:
        return len(self._records)

    @property
    def total_pnl(self) -> float:
        return sum(r.pnl for r in self._records)

    @property
    def win_rate(self) -> float:
        if not self._records:
            return 0.0
        wins = sum(1 for r in self._records if r.pnl > 0)
        return wins / len(self._records)
