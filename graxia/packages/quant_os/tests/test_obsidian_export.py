"""
Tests for Obsidian Trade Journal Exporter (execution/obsidian_export.py).

Covers:
- Daily export creates file with correct structure
- Frontmatter presence and correctness
- Trade table formatting
- Individual trade card export
- Weekly review export
- Atomic write behavior
- Directory creation
- Empty trade list handling
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.execution.obsidian_export import (
    ObsidianExporter,
    TradeCard,
)

# ── Fixtures ──────────────────────────────────────────────────────


@dataclass
class FakeTrade:
    """Minimal trade record for testing."""

    trade_id: str
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal | None
    volume: Decimal
    pnl: Decimal
    fees: Decimal
    entry_time: datetime | None
    exit_time: datetime | None
    close_reason: str
    strategy_id: str
    execution_quality: str = ""


def _make_trade(
    trade_id: str = "t-001",
    symbol: str = "XAUUSD",
    side: str = "LONG",
    entry: float = 2345.50,
    exit_p: float = 2351.20,
    pnl: float = 85.00,
    fees: float = 2.50,
    strategy: str = "mtm",
    close_reason: str = "Take Profit hit",
) -> FakeTrade:
    """Create a FakeTrade with sensible defaults."""
    return FakeTrade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        entry_price=Decimal(str(entry)),
        exit_price=Decimal(str(exit_p)),
        volume=Decimal("0.1"),
        pnl=Decimal(str(pnl)),
        fees=Decimal(str(fees)),
        entry_time=datetime(2026, 7, 3, 8, 15, tzinfo=UTC),
        exit_time=datetime(2026, 7, 3, 14, 30, tzinfo=UTC),
        close_reason=close_reason,
        strategy_id=strategy,
    )


@pytest.fixture
def mock_ledger():
    """Create a mock ledger returning test trades."""
    ledger = MagicMock()
    ledger.get_trades.return_value = [
        _make_trade("t-001", "XAUUSD", "LONG", 2345.50, 2351.20, 85.00, 2.50),
        _make_trade("t-002", "XAUUSD", "SHORT", 2355.00, 2360.00, -75.00, 2.50),
        _make_trade("t-003", "EURUSD", "LONG", 1.0850, 1.0900, 50.00, 1.00),
    ]
    return ledger


@pytest.fixture
def exporter(tmp_path: Path, mock_ledger) -> ObsidianExporter:
    """Create an exporter with tmp_path vault and mock ledger."""
    return ObsidianExporter(str(tmp_path), ledger=mock_ledger)


@pytest.fixture
def empty_exporter(tmp_path: Path) -> ObsidianExporter:
    """Create an exporter with no ledger."""
    return ObsidianExporter(str(tmp_path))


# ── Daily Export ──────────────────────────────────────────────────


class TestExportDaily:
    def test_export_daily_creates_file(self, exporter: ObsidianExporter):
        """export_daily should create a markdown file."""
        path = exporter.export_daily("2026-07-03")
        assert path.exists()
        assert path.suffix == ".md"
        assert "2026-07" in str(path)

    def test_export_daily_has_frontmatter(self, exporter: ObsidianExporter):
        """Daily export should have YAML frontmatter."""
        path = exporter.export_daily("2026-07-03")
        content = path.read_text(encoding="utf-8")

        assert content.startswith("---\n")
        assert "date: 2026-07-03" in content
        assert "type: trading/daily" in content
        assert "tags: [trading, daily]" in content

    def test_export_daily_has_trade_table(self, exporter: ObsidianExporter):
        """Daily export should contain a trade table."""
        path = exporter.export_daily("2026-07-03")
        content = path.read_text(encoding="utf-8")

        assert "| Symbol | Side | Entry | Exit | P&L | Strategy |" in content
        assert "XAUUSD" in content
        assert "EURUSD" in content

    def test_export_daily_has_summary_metrics(self, exporter: ObsidianExporter):
        """Daily export should include summary table with metrics."""
        path = exporter.export_daily("2026-07-03")
        content = path.read_text(encoding="utf-8")

        assert "| Trades | 3 |" in content
        assert "| Wins |" in content
        assert "| Losses |" in content
        assert "Win Rate" in content
        assert "Net P&L" in content

    def test_export_daily_empty_trades(self, empty_exporter: ObsidianExporter):
        """Daily export with no trades should create file gracefully."""
        path = empty_exporter.export_daily("2026-07-03")
        content = path.read_text(encoding="utf-8")

        assert path.exists()
        assert "| Trades | 0 |" in content
        assert "No trades recorded" in content

    def test_export_daily_default_date(self, exporter: ObsidianExporter):
        """export_daily with no date should use today."""
        path = exporter.export_daily()
        assert path.exists()
        # Should contain today's date
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        content = path.read_text(encoding="utf-8")
        assert today in content


# ── Trade Card Export ─────────────────────────────────────────────


class TestExportTrade:
    def test_export_trade_creates_file(self, exporter: ObsidianExporter):
        """export_trade should create a trade card file."""
        path = exporter.export_trade("t-001")
        assert path.exists()
        assert "XAUUSD-LONG" in path.name

    def test_export_trade_has_entry_exit(self, exporter: ObsidianExporter):
        """Trade card should have Entry and Exit sections."""
        path = exporter.export_trade("t-001")
        content = path.read_text(encoding="utf-8")

        assert "## Entry" in content
        assert "## Exit" in content
        assert "2345.50" in content
        assert "2351.20" in content

    def test_export_trade_has_frontmatter(self, exporter: ObsidianExporter):
        """Trade card should have YAML frontmatter with trade metadata."""
        path = exporter.export_trade("t-001")
        content = path.read_text(encoding="utf-8")

        assert content.startswith("---\n")
        assert "type: trading/trade" in content
        assert "symbol: XAUUSD" in content
        assert "side: LONG" in content
        assert "strategy: mtm" in content

    def test_export_trade_has_performance(self, exporter: ObsidianExporter):
        """Trade card should have Performance section with P&L."""
        path = exporter.export_trade("t-001")
        content = path.read_text(encoding="utf-8")

        assert "## Performance" in content
        assert "+$85.00" in content
        assert "6h 15m" in content

    def test_export_trade_not_found(self, exporter: ObsidianExporter):
        """export_trade should raise ValueError for unknown trade."""
        with pytest.raises(ValueError, match="not found"):
            exporter.export_trade("nonexistent-id")

    def test_export_trade_close_reason(self, exporter: ObsidianExporter):
        """Trade card should include close reason."""
        path = exporter.export_trade("t-001")
        content = path.read_text(encoding="utf-8")

        assert "Take Profit hit" in content


# ── Weekly Export ─────────────────────────────────────────────────


class TestExportWeekly:
    def test_export_weekly_creates_file(self, exporter: ObsidianExporter):
        """export_weekly should create a weekly review file."""
        path = exporter.export_weekly("2026-W27")
        assert path.exists()
        assert "weekly" in str(path)

    def test_export_weekly_has_metrics(self, exporter: ObsidianExporter):
        """Weekly review should have summary metrics."""
        path = exporter.export_weekly("2026-W27")
        content = path.read_text(encoding="utf-8")

        assert "Weekly Review" in content
        assert "Total Trades" in content
        assert "Win Rate" in content
        assert "Net P&L" in content

    def test_export_weekly_has_frontmatter(self, exporter: ObsidianExporter):
        """Weekly review should have YAML frontmatter."""
        path = exporter.export_weekly("2026-W27")
        content = path.read_text(encoding="utf-8")

        assert content.startswith("---\n")
        assert "type: trading/weekly" in content
        assert "week: 2026-W27" in content

    def test_export_weekly_empty(self, empty_exporter: ObsidianExporter):
        """Weekly export with no trades should handle gracefully."""
        path = empty_exporter.export_weekly("2026-W27")
        content = path.read_text(encoding="utf-8")

        assert path.exists()
        assert "No trading activity" in content


# ── Atomic Write ──────────────────────────────────────────────────


class TestAtomicWrite:
    def test_atomic_write_creates_file(self, tmp_path: Path):
        """_atomic_write should create the target file."""
        exporter = ObsidianExporter(str(tmp_path))
        target = tmp_path / "test.md"
        exporter._atomic_write(target, "# Hello\n")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# Hello\n"

    def test_atomic_write_no_temp残留(self, tmp_path: Path):
        """_atomic_write should not leave temp files behind."""
        exporter = ObsidianExporter(str(tmp_path))
        target = tmp_path / "test.md"
        exporter._atomic_write(target, "content")

        tmp_files = list(tmp_path.glob(".obsidian_*"))
        assert len(tmp_files) == 0

    def test_atomic_write_overwrites(self, tmp_path: Path):
        """_atomic_write should overwrite existing file content."""
        exporter = ObsidianExporter(str(tmp_path))
        target = tmp_path / "test.md"
        exporter._atomic_write(target, "old content")
        exporter._atomic_write(target, "new content")

        assert target.read_text(encoding="utf-8") == "new content"


# ── Directory Creation ────────────────────────────────────────────


class TestDirectoryCreation:
    def test_creates_directories(self, tmp_path: Path):
        """Export should create nested directories as needed."""
        exporter = ObsidianExporter(str(tmp_path), ledger=None)
        path = exporter.export_daily("2026-07-03")

        assert path.parent.exists()
        assert "trading" in str(path)
        assert "2026-07" in str(path)

    def test_creates_weekly_directory(self, tmp_path: Path):
        """Weekly export should create weekly/ directory."""
        exporter = ObsidianExporter(str(tmp_path), ledger=None)
        path = exporter.export_weekly("2026-W27")

        assert path.parent.exists()
        assert "weekly" in str(path)


# ── Summary Computation ───────────────────────────────────────────


class TestSummaryComputation:
    def test_summary_win_rate(self, exporter: ObsidianExporter):
        """Win rate should be computed correctly."""
        trades = [
            _make_trade(pnl=100.0),
            _make_trade(pnl=-50.0),
            _make_trade(pnl=75.0),
        ]
        summary = exporter._compute_daily_summary(trades, "2026-07-03")
        assert summary.wins == 2
        assert summary.losses == 1
        assert summary.win_rate == pytest.approx(2 / 3)

    def test_summary_pnl(self, exporter: ObsidianExporter):
        """Net P&L should subtract fees from gross."""
        trades = [
            _make_trade(pnl=100.0, fees=5.0),
            _make_trade(pnl=-30.0, fees=3.0),
        ]
        summary = exporter._compute_daily_summary(trades, "2026-07-03")
        assert summary.pnl_gross == Decimal("70")
        assert summary.pnl_net == Decimal("62")
        assert summary.fees == Decimal("8")

    def test_summary_empty_trades(self, exporter: ObsidianExporter):
        """Empty trade list should produce zeroed summary."""
        summary = exporter._compute_daily_summary([], "2026-07-03")
        assert summary.trades == 0
        assert summary.win_rate == 0.0
        assert summary.pnl_net == Decimal("0")


# ── Markdown Formatting ──────────────────────────────────────────


class TestMarkdownFormatting:
    def test_trade_card_format(self):
        """TradeCard formatting should include all key sections."""
        from graxia.packages.quant_os.execution.obsidian_export import ObsidianExporter

        card = TradeCard(
            trade_id="t-001",
            symbol="XAUUSD",
            side="LONG",
            entry_price=Decimal("2345.50"),
            exit_price=Decimal("2351.20"),
            volume=Decimal("0.1"),
            pnl=Decimal("85.00"),
            fees=Decimal("2.50"),
            entry_time=datetime(2026, 7, 3, 8, 15, tzinfo=UTC),
            exit_time=datetime(2026, 7, 3, 14, 30, tzinfo=UTC),
            close_reason="Take Profit hit",
            strategy_id="mtm",
            regime="TREND_UP",
            metadata={},
        )

        exporter = ObsidianExporter("/tmp")
        md = exporter._format_trade_markdown(card)

        assert "# XAUUSD LONG" in md
        assert "2345.50" in md
        assert "2351.20" in md
        assert "+$85.00" in md
        assert "6h 15m" in md
        assert "Take Profit hit" in md
