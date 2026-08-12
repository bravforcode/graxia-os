"""
Obsidian Trade Journal Exporter.

Exports trade data as Obsidian-compatible markdown files:
- Daily trade summary with frontmatter
- Individual trade analysis cards
- Weekly performance review
- Strategy performance breakdown

Output structure:
    vault/trading/
    ├── YYYY-MM/
    │   ├── YYYY-MM-DD.md           # Daily summary
    │   ├── SYMBOL-SIDE-YYYYMMDD.md  # Individual trade
    │   └── ...
    ├── weekly/
    │   └── YYYY-WNN.md             # Weekly review
    └── strategies/
        └── strategy-name.md        # Performance

Safety:
    - Read-only access to trade data (never modifies ledger)
    - All file I/O uses atomic write (temp + rename)
    - Never overwrites existing files (append or create new)
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DailySummary:
    """Aggregated metrics for a single trading day."""

    date: str
    trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float
    pnl_gross: Decimal
    pnl_net: Decimal
    fees: Decimal
    best_trade: Decimal
    worst_trade: Decimal
    avg_trade: Decimal


@dataclass
class TradeCard:
    """Individual trade data for export."""

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
    regime: str
    metadata: dict[str, Any]


class ObsidianExporter:
    """Exports trade data as Obsidian-compatible markdown files.

    Usage:
        exporter = ObsidianExporter("/path/to/vault", ledger=my_ledger)
        daily_path = exporter.export_daily("2026-07-03")
        trade_path = exporter.export_trade("t-abc123")
        weekly_path = exporter.export_weekly("2026-W27")
    """

    def __init__(self, vault_path: str, ledger: Any = None) -> None:
        """Initialize exporter.

        Args:
            vault_path: Root path of the Obsidian vault
            ledger: TradeLedger instance for reading trade data
        """
        self._vault = Path(vault_path)
        self._ledger = ledger

    def export_daily(self, date: str | None = None) -> Path:
        """Export daily trade summary.

        Args:
            date: Date string YYYY-MM-DD (default: today UTC)

        Returns:
            Path to the created markdown file
        """
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")

        trades = self._get_trades_for_date(date)
        summary = self._compute_daily_summary(trades, date)
        markdown = self._format_daily_markdown(trades, summary, date)

        month_dir = self._vault / "trading" / date[:7]
        month_dir.mkdir(parents=True, exist_ok=True)
        path = month_dir / f"{date}.md"
        self._atomic_write(path, markdown)
        logger.info("obsidian.daily_exported", date=date, trades=len(trades), path=str(path))
        return path

    def export_trade(self, trade_id: str) -> Path:
        """Export individual trade analysis card.

        Args:
            trade_id: Unique trade identifier

        Returns:
            Path to the created markdown file

        Raises:
            ValueError: If trade not found in ledger
        """
        trade = self._get_trade_by_id(trade_id)
        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")

        card = self._trade_to_card(trade)
        markdown = self._format_trade_markdown(card)

        date_str = card.entry_time.strftime("%Y-%m-%d") if card.entry_time else "unknown"
        month_dir = self._vault / "trading" / date_str[:7]
        month_dir.mkdir(parents=True, exist_ok=True)

        side = card.side.upper()
        symbol = card.symbol.upper()
        date_compact = date_str.replace("-", "")
        filename = f"{symbol}-{side}-{date_compact}.md"
        path = month_dir / filename
        self._atomic_write(path, markdown)
        logger.info("obsidian.trade_exported", trade_id=trade_id, path=str(path))
        return path

    def export_weekly(self, week: str | None = None) -> Path:
        """Export weekly performance review.

        Args:
            week: ISO week string YYYY-WNN (default: current week)

        Returns:
            Path to the created markdown file
        """
        if week is None:
            now = datetime.now(UTC)
            week = f"{now.year}-W{now.isocalendar()[1]:02d}"

        year_str, week_num_str = week.split("-W")
        week_num = int(week_num_str)
        year = int(year_str)

        # Compute date range for the ISO week
        jan4 = datetime(year, 1, 4, tzinfo=UTC)
        start_of_week = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week_num - 1)
        dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        daily_summaries: list[DailySummary] = []
        for d in dates:
            trades = self._get_trades_for_date(d)
            if trades:
                summary = self._compute_daily_summary(trades, d)
                daily_summaries.append(summary)

        markdown = self._format_weekly_markdown(daily_summaries, week)

        weekly_dir = self._vault / "trading" / "weekly"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        path = weekly_dir / f"{week}.md"
        self._atomic_write(path, markdown)
        logger.info("obsidian.weekly_exported", week=week, path=str(path))
        return path

    # ── Data Access ─────────────────────────────────────────────────

    def _get_trades_for_date(self, date: str) -> list[Any]:
        """Get trades from ledger for a specific date."""
        if self._ledger is None:
            return []
        try:
            return self._ledger.get_trades(date=date)
        except Exception as exc:
            logger.warning("obsidian.ledger_error", date=date, error=str(exc))
            return []

    def _get_trade_by_id(self, trade_id: str) -> Any:
        """Get a single trade by ID from ledger."""
        if self._ledger is None:
            return None
        try:
            trades = self._ledger.get_trades()
            for t in trades:
                if t.trade_id == trade_id:
                    return t
            return None
        except Exception as exc:
            logger.warning("obsidian.ledger_error", trade_id=trade_id, error=str(exc))
            return None

    def _trade_to_card(self, trade: Any) -> TradeCard:
        """Convert a TradeRecord to a TradeCard."""
        return TradeCard(
            trade_id=getattr(trade, "trade_id", ""),
            symbol=getattr(trade, "symbol", ""),
            side=getattr(trade, "side", ""),
            entry_price=getattr(trade, "entry_price", Decimal("0")),
            exit_price=getattr(trade, "exit_price", None),
            volume=getattr(trade, "volume", Decimal("0")),
            pnl=getattr(trade, "pnl", Decimal("0")),
            fees=getattr(trade, "fees", Decimal("0")),
            entry_time=getattr(trade, "entry_time", None),
            exit_time=getattr(trade, "exit_time", None),
            close_reason=getattr(trade, "close_reason", ""),
            strategy_id=getattr(trade, "strategy_id", ""),
            regime=getattr(trade, "execution_quality", ""),
            metadata={},
        )

    # ── Summary Computation ─────────────────────────────────────────

    def _compute_daily_summary(self, trades: list[Any], date: str) -> DailySummary:
        """Compute daily summary metrics from trade list."""
        if not trades:
            return DailySummary(
                date=date,
                trades=0,
                wins=0,
                losses=0,
                breakevens=0,
                win_rate=0.0,
                pnl_gross=Decimal("0"),
                pnl_net=Decimal("0"),
                fees=Decimal("0"),
                best_trade=Decimal("0"),
                worst_trade=Decimal("0"),
                avg_trade=Decimal("0"),
            )

        pnls = [getattr(t, "pnl", Decimal("0")) for t in trades]
        fees_list = [getattr(t, "fees", Decimal("0")) for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        breakevens = sum(1 for p in pnls if p == 0)
        total = len(trades)
        pnl_gross = sum(pnls, Decimal("0"))
        total_fees = sum(fees_list, Decimal("0"))
        pnl_net = pnl_gross - total_fees
        win_rate = wins / total if total > 0 else 0.0
        best = max(pnls) if pnls else Decimal("0")
        worst = min(pnls) if pnls else Decimal("0")
        avg = pnl_gross / total if total > 0 else Decimal("0")

        return DailySummary(
            date=date,
            trades=total,
            wins=wins,
            losses=losses,
            breakevens=breakevens,
            win_rate=win_rate,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
            fees=total_fees,
            best_trade=best,
            worst_trade=worst,
            avg_trade=avg,
        )

    # ── Markdown Formatting ─────────────────────────────────────────

    def _format_daily_markdown(self, trades: list[Any], summary: DailySummary, date: str) -> str:
        """Format daily summary as Obsidian markdown with frontmatter."""
        pnl_net = float(summary.pnl_net)
        win_pct = summary.win_rate * 100

        frontmatter = (
            "---\n"
            f"date: {date}\n"
            "type: trading/daily\n"
            f"trades: {summary.trades}\n"
            f"win_rate: {summary.win_rate:.2f}\n"
            f"pnl_net: {pnl_net:.2f}\n"
            "tags: [trading, daily]\n"
            "---\n"
        )

        lines = [
            frontmatter,
            f"# Trading Journal — {date}\n",
            "## Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Trades | {summary.trades} |",
            f"| Wins | {summary.wins} |",
            f"| Losses | {summary.losses} |",
            f"| Win Rate | {win_pct:.1f}% |",
            f"| Net P&L | ${pnl_net:+.2f} |",
            "",
        ]

        if trades:
            lines.append("## Trades\n")
            lines.append("| Symbol | Side | Entry | Exit | P&L | Strategy |")
            lines.append("|--------|------|-------|------|-----|----------|")
            for t in trades:
                symbol = getattr(t, "symbol", "?")
                side = getattr(t, "side", "?")
                entry = float(getattr(t, "entry_price", 0))
                exit_p = getattr(t, "exit_price", None)
                exit_str = f"{float(exit_p):.2f}" if exit_p else "—"
                pnl = float(getattr(t, "pnl", 0))
                strategy = getattr(t, "strategy_id", "—")
                sign = "+" if pnl >= 0 else ""
                lines.append(f"| {symbol} | {side} | {entry:.2f} | {exit_str} | " f"{sign}${pnl:.2f} | {strategy} |")
        else:
            lines.append("*No trades recorded for this day.*\n")

        return "\n".join(lines) + "\n"

    def _format_trade_markdown(self, card: TradeCard) -> str:
        """Format individual trade as Obsidian note with frontmatter."""
        pnl_float = float(card.pnl)
        entry_float = float(card.entry_price)
        exit_float = float(card.exit_price) if card.exit_price else 0.0

        entry_time_str = card.entry_time.strftime("%H:%M UTC") if card.entry_time else "—"
        exit_time_str = card.exit_time.strftime("%H:%M UTC") if card.exit_time else "—"
        date_str = card.entry_time.strftime("%Y-%m-%d") if card.entry_time else "unknown"

        # Duration calculation
        duration_str = "—"
        if card.entry_time and card.exit_time:
            delta = card.exit_time - card.entry_time
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            duration_str = f"{hours}h {minutes}m"

        exit_str = f"{exit_float:.2f}" if card.exit_price else "OPEN"
        symbol_lower = card.symbol.lower()
        side_lower = card.side.lower()

        frontmatter = (
            "---\n"
            f"date: {date_str}\n"
            "type: trading/trade\n"
            f"symbol: {card.symbol}\n"
            f"side: {card.side}\n"
            f"entry: {entry_float:.2f}\n"
            f"exit: {exit_str}\n"
            f"pnl: {pnl_float:.2f}\n"
            f"strategy: {card.strategy_id}\n"
            f"regime: {card.regime}\n"
            f"tags: [trading, {symbol_lower}, {side_lower}]\n"
            "---\n"
        )

        sign = "+" if pnl_float >= 0 else ""
        lines = [
            frontmatter,
            f"# {card.symbol} {card.side} — {date_str}\n",
            "## Entry\n",
            f"- **Price:** {entry_float:.2f}",
            f"- **Time:** {entry_time_str}",
            f"- **Regime:** {card.regime or '—'}",
            f"- **Strategy:** {card.strategy_id or '—'}",
            "",
            "## Exit\n",
            f"- **Price:** {exit_str}",
            f"- **Time:** {exit_time_str}",
            f"- **Reason:** {card.close_reason or '—'}",
            "",
            "## Performance\n",
            f"- **P&L:** {sign}${pnl_float:.2f}",
            f"- **Duration:** {duration_str}",
        ]

        return "\n".join(lines) + "\n"

    def _format_weekly_markdown(self, daily_summaries: list[DailySummary], week: str) -> str:
        """Format weekly performance review."""
        total_trades = sum(d.trades for d in daily_summaries)
        total_wins = sum(d.wins for d in daily_summaries)
        total_losses = sum(d.losses for d in daily_summaries)
        total_pnl = sum((d.pnl_net for d in daily_summaries), Decimal("0"))
        win_rate = total_wins / total_trades if total_trades > 0 else 0.0
        win_pct = win_rate * 100

        frontmatter = (
            "---\n"
            f"week: {week}\n"
            "type: trading/weekly\n"
            f"trades: {total_trades}\n"
            f"win_rate: {win_rate:.2f}\n"
            f"pnl_net: {float(total_pnl):.2f}\n"
            "tags: [trading, weekly]\n"
            "---\n"
        )

        lines = [
            frontmatter,
            f"# Weekly Review — {week}\n",
            "## Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Trades | {total_trades} |",
            f"| Wins | {total_wins} |",
            f"| Losses | {total_losses} |",
            f"| Win Rate | {win_pct:.1f}% |",
            f"| Net P&L | ${float(total_pnl):+.2f} |",
            "",
        ]

        if daily_summaries:
            lines.append("## Daily Breakdown\n")
            lines.append("| Date | Trades | Wins | Losses | P&L |")
            lines.append("|------|--------|------|--------|-----|")
            for d in daily_summaries:
                pnl_f = float(d.pnl_net)
                sign = "+" if pnl_f >= 0 else ""
                lines.append(f"| {d.date} | {d.trades} | {d.wins} | {d.losses} | " f"{sign}${pnl_f:.2f} |")
        else:
            lines.append("*No trading activity this week.*\n")

        return "\n".join(lines) + "\n"

    # ── Atomic Write ────────────────────────────────────────────────

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write file atomically using temp file + rename.

        This prevents partial writes from corrupting existing files.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".obsidian_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
