"""Slippage tracker — measures execution quality vs expected prices."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SlippageRecord:
    """Single slippage measurement."""

    timestamp: str
    symbol: str
    side: str
    expected_price: float
    actual_price: float
    slippage_bps: float
    lot_size: float
    latency_ms: float = 0.0


@dataclass
class SlippageStats:
    """Aggregated slippage statistics."""

    symbol: str
    n_trades: int = 0
    avg_slippage_bps: float = 0.0
    median_slippage_bps: float = 0.0
    p95_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    avg_latency_ms: float = 0.0
    fill_rate: float = 0.0
    within_tolerance: bool = False  # avg < 1.5x expected

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "n_trades": self.n_trades,
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "median_slippage_bps": round(self.median_slippage_bps, 2),
            "p95_slippage_bps": round(self.p95_slippage_bps, 2),
            "max_slippage_bps": round(self.max_slippage_bps, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "fill_rate": round(self.fill_rate, 4),
            "within_tolerance": self.within_tolerance,
        }


class SlippageTracker:
    """Tracks and analyzes slippage across live trades."""

    def __init__(self, expected_slippage_bps: float = 10.0, output_dir: Path = Path("reports/validation/live")):
        self.expected_slippage_bps = expected_slippage_bps
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[SlippageRecord] = []

    def record(
        self,
        symbol: str,
        side: str,
        expected_price: float,
        actual_price: float,
        lot_size: float,
        latency_ms: float = 0.0,
    ) -> SlippageRecord:
        """Record a single trade's slippage."""
        slippage_bps = abs(actual_price - expected_price) / expected_price * 10000 if expected_price > 0 else 0.0

        rec = SlippageRecord(
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            side=side,
            expected_price=expected_price,
            actual_price=actual_price,
            slippage_bps=slippage_bps,
            lot_size=lot_size,
            latency_ms=latency_ms,
        )
        self.records.append(rec)
        return rec

    def get_stats(self, symbol: str | None = None) -> SlippageStats:
        """Compute slippage statistics."""
        filtered = [r for r in self.records if symbol is None or r.symbol == symbol]

        if not filtered:
            return SlippageStats(symbol=symbol or "ALL")

        slippages = [r.slippage_bps for r in filtered]
        latencies = [r.latency_ms for r in filtered]

        slippages.sort()
        n = len(slippages)

        avg_slip = sum(slippages) / n
        median_slip = slippages[n // 2]
        p95_slip = slippages[int(n * 0.95)] if n > 20 else max(slippages)
        max_slip = max(slippages)
        avg_lat = sum(latencies) / n if latencies else 0.0

        return SlippageStats(
            symbol=symbol or "ALL",
            n_trades=n,
            avg_slippage_bps=avg_slip,
            median_slippage_bps=median_slip,
            p95_slippage_bps=p95_slip,
            max_slippage_bps=max_slip,
            avg_latency_ms=avg_lat,
            fill_rate=1.0,  # All recorded trades were filled
            within_tolerance=avg_slip < self.expected_slippage_bps * 1.5,
        )

    def save(self) -> Path:
        """Save all records to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"{timestamp}_slippage_report.json"

        stats = self.get_stats()
        data = {
            "timestamp": timestamp,
            "stats": stats.to_dict(),
            "records": [
                {
                    "timestamp": r.timestamp,
                    "symbol": r.symbol,
                    "side": r.side,
                    "expected_price": r.expected_price,
                    "actual_price": r.actual_price,
                    "slippage_bps": round(r.slippage_bps, 2),
                    "lot_size": r.lot_size,
                    "latency_ms": round(r.latency_ms, 2),
                }
                for r in self.records
            ],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("slippage.saved", path=str(path), n_records=len(self.records))
        return path
