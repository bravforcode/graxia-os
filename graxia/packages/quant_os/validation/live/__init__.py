"""Micro-lot live testing module — validates execution quality with real money."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LiveTestConfig:
    """Configuration for micro-lot live testing."""

    symbol: str = "XAUUSD"
    lot_size: float = 0.01
    max_loss_usd: float = 10.0
    duration_days: int = 7
    check_interval_sec: int = 60
    max_slippage_bps: float = 15.0
    min_fill_rate: float = 0.90


@dataclass
class TradeRecord:
    """Record of a single live test trade."""

    timestamp: str
    symbol: str
    side: str  # "BUY" or "SELL"
    lot_size: float
    expected_price: float
    actual_price: float
    slippage_bps: float
    pnl_usd: float
    filled: bool
    error: str = ""


@dataclass
class LiveTestResult:
    """Result of micro-lot live testing."""

    symbol: str
    start_time: str
    end_time: str
    total_trades: int = 0
    filled_trades: int = 0
    fill_rate: float = 0.0
    avg_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    total_pnl_usd: float = 0.0
    max_drawdown_usd: float = 0.0
    override_incidents: int = 0
    passed: bool = False
    trades: list[TradeRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_trades": self.total_trades,
            "filled_trades": self.filled_trades,
            "fill_rate": round(self.fill_rate, 4),
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "max_slippage_bps": round(self.max_slippage_bps, 2),
            "total_pnl_usd": round(self.total_pnl_usd, 2),
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "override_incidents": self.override_incidents,
            "passed": self.passed,
            "errors": self.errors,
        }


class MicroLotTester:
    """Micro-lot live testing with MT5 integration."""

    def __init__(self, config: LiveTestConfig, output_dir: Path = Path("reports/validation/live")):
        self.config = config
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trades: list[TradeRecord] = []
        self.override_count = 0

    def run_single_trade(self, side: str, expected_price: float) -> TradeRecord:
        """Execute a single micro-lot trade and measure execution quality."""
        try:
            from ...broker.mt5 import MT5Adapter

            adapter = MT5Adapter()
            result = adapter.place_order(
                symbol=self.config.symbol,
                side=side,
                lot_size=self.config.lot_size,
                sl_points=100,  # 100 points SL
                tp_points=200,  # 200 points TP
            )

            if result and result.get("filled"):
                actual_price = result.get("fill_price", expected_price)
                slippage_bps = abs(actual_price - expected_price) / expected_price * 10000

                trade = TradeRecord(
                    timestamp=datetime.now().isoformat(),
                    symbol=self.config.symbol,
                    side=side,
                    lot_size=self.config.lot_size,
                    expected_price=expected_price,
                    actual_price=actual_price,
                    slippage_bps=slippage_bps,
                    pnl_usd=result.get("pnl", 0.0),
                    filled=True,
                )
            else:
                trade = TradeRecord(
                    timestamp=datetime.now().isoformat(),
                    symbol=self.config.symbol,
                    side=side,
                    lot_size=self.config.lot_size,
                    expected_price=expected_price,
                    actual_price=0.0,
                    slippage_bps=0.0,
                    pnl_usd=0.0,
                    filled=False,
                    error=result.get("error", "Unknown error") if result else "No result",
                )

        except Exception as e:
            trade = TradeRecord(
                timestamp=datetime.now().isoformat(),
                symbol=self.config.symbol,
                side=side,
                lot_size=self.config.lot_size,
                expected_price=expected_price,
                actual_price=0.0,
                slippage_bps=0.0,
                pnl_usd=0.0,
                filled=False,
                error=str(e),
            )

        self.trades.append(trade)
        return trade

    def evaluate(self) -> LiveTestResult:
        """Evaluate all trades and determine if live test passed."""
        if not self.trades:
            return LiveTestResult(
                symbol=self.config.symbol,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                errors=["No trades recorded"],
            )

        filled = [t for t in self.trades if t.filled]
        slippages = [t.slippage_bps for t in filled]
        pnls = [t.pnl_usd for t in self.trades]

        fill_rate = len(filled) / len(self.trades) if self.trades else 0.0
        avg_slip = sum(slippages) / len(slippages) if slippages else 0.0
        max_slip = max(slippages) if slippages else 0.0
        total_pnl = sum(pnls)

        # Max drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnls:
            cumulative += pnl
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        # Gate checks
        passed = (
            fill_rate >= self.config.min_fill_rate
            and avg_slip < self.config.max_slippage_bps
            and self.override_count == 0
        )

        result = LiveTestResult(
            symbol=self.config.symbol,
            start_time=self.trades[0].timestamp if self.trades else "",
            end_time=self.trades[-1].timestamp if self.trades else "",
            total_trades=len(self.trades),
            filled_trades=len(filled),
            fill_rate=fill_rate,
            avg_slippage_bps=avg_slip,
            max_slippage_bps=max_slip,
            total_pnl_usd=total_pnl,
            max_drawdown_usd=max_dd,
            override_incidents=self.override_count,
            passed=passed,
            trades=self.trades,
        )

        # Save result
        self._save_result(result)
        return result

    def _save_result(self, result: LiveTestResult) -> None:
        """Save live test result to JSON."""
        import json

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"{timestamp}_live_test_{self.config.symbol}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info("live_test.saved", path=str(path))


def run_micro_lot_validation(
    symbol: str = "XAUUSD",
    lot_size: float = 0.01,
    max_loss_usd: float = 10.0,
    output_dir: Path = Path("reports/validation/live"),
) -> dict:
    """Run micro-lot validation and return results as dict."""
    config = LiveTestConfig(
        symbol=symbol,
        lot_size=lot_size,
        max_loss_usd=max_loss_usd,
    )
    tester = MicroLotTester(config, output_dir)

    # Note: In production, this would connect to MT5 and execute trades
    # For now, return a placeholder result indicating manual testing needed
    result = LiveTestResult(
        symbol=symbol,
        start_time=datetime.now().isoformat(),
        end_time=datetime.now().isoformat(),
        errors=["Manual MT5 connection required - run with --live flag"],
    )
    return result.to_dict()
