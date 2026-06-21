"""
Persistent trade ledger. Records every trade with full provenance.
JSON-file storage — ponytail: directory of JSONs is fine for <10k trades/day.
Upgrade to SQLite if query patterns get complex.
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Optional


getcontext().prec = 28  # ponytail: enough for price arithmetic


def _default(obj):
    """JSON serializer for Decimal, datetime, etc."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _load_record(data: dict) -> dict:
    """Restore Decimals and datetimes from JSON dict."""
    for key in ("entry_price", "exit_price", "volume", "pnl", "pnl_pct", "fees", "spread_cost", "slippage_cost"):
        if data.get(key) is not None:
            data[key] = Decimal(data[key])
    for key in ("entry_time", "exit_time", "created_at_utc"):
        if data.get(key) is not None:
            data[key] = datetime.fromisoformat(data[key])
    return data


@dataclass
class TradeRecord:
    trade_id: str
    order_id: str
    symbol: str
    side: str  # BUY/SELL
    entry_price: Decimal
    exit_price: Optional[Decimal]
    volume: Decimal  # lots
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]
    pnl: Optional[Decimal]
    pnl_pct: Optional[Decimal]
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    close_reason: str  # STOP_LOSS, TAKE_PROFIT, MANUAL, EXPIRED
    execution_quality: str  # BAR_ONLY, CONSERVATIVE_BAR, TICK_REPLAY, LIVE_OBSERVED
    strategy_id: str
    contract_snapshot_id: str
    risk_policy_version: str
    dataset_manifest_id: str
    cost_scenario: str  # base, stress_1, stress_2, stress_3
    is_ambiguous: bool = False
    ambiguous_path: Optional[str] = None  # "SL_FIRST" or "TP_FIRST"
    git_commit: str = ""
    created_at_utc: datetime = field(default_factory=datetime.utcnow)


class TradeLedger:
    def __init__(self, ledger_dir: str = "data/trade_ledger"):
        self._dir = Path(ledger_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def record_trade(self, record: TradeRecord) -> str:
        """Persist a trade record. Returns the file path."""
        data = asdict(record)
        file_path = self._dir / f"{record.trade_id}.json"
        file_path.write_text(json.dumps(data, default=_default, indent=2))
        return str(file_path)

    def get_trades(self, symbol: Optional[str] = None, date: Optional[str] = None) -> list[TradeRecord]:
        """Retrieve trades, optionally filtered by symbol/date (YYYY-MM-DD prefix on entry_time)."""
        results = []
        for fp in sorted(self._dir.glob("*.json")):
            data = json.loads(fp.read_text())
            data = _load_record(data)
            if symbol and data.get("symbol") != symbol:
                continue
            if date and data.get("entry_time"):
                if not data["entry_time"].strftime("%Y-%m-%d").startswith(date):
                    continue
            results.append(TradeRecord(**data))
        return results

    def get_summary(self) -> dict:
        """Summary stats: total trades, total PnL, win rate, etc."""
        trades = self.get_trades()
        if not trades:
            return {"total": 0}

        closed = [t for t in trades if t.pnl is not None]
        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl < 0]
        total_pnl = sum((t.pnl for t in closed), Decimal("0"))
        total_fees = sum((t.fees for t in trades), Decimal("0"))

        return {
            "total": len(trades),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed) if closed else 0,
            "total_pnl": str(total_pnl),
            "total_fees": str(total_fees),
            "avg_pnl": str(total_pnl / len(closed)) if closed else "0",
        }

    def ledger_hash(self) -> str:
        """SHA-256 hash of all trade records for integrity verification."""
        h = hashlib.sha256()
        for fp in sorted(self._dir.glob("*.json")):
            h.update(fp.read_text().encode())
        return h.hexdigest()

    def get_ambiguous_trades(self) -> list[TradeRecord]:
        """Every ambiguous trade must be visible — no hiding."""
        return [t for t in self.get_trades() if t.is_ambiguous]

    def count(self) -> int:
        return len(list(self._dir.glob("*.json")))
