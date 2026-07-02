"""
Shadow trade reporting for Telegram delivery.

Queries DuckDB shadow_trades table and generates daily/weekly
expectancy reports formatted as Telegram HTML.

Usage::

    from monitoring.shadow_report import ShadowReport

    report = ShadowReport()
    daily = report.generate_daily_report()
    report.send_to_telegram(daily)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TradeStats:
    """Aggregated trade statistics for a period."""

    total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    payoff_ratio: float = 0.0
    expectancy: float = 0.0
    net_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    open_positions: int = 0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_session: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ShadowReport:
    """Query DuckDB shadow_trades and produce Telegram-ready reports.

    Args:
        db_path: Path to DuckDB file.  Falls back to env ``DUCKDB_PATH``
            then ``data/market_data.duckdb``.
        bot_token: Telegram bot token.  Falls back to env ``TELEGRAM_BOT_TOKEN``.
        chat_id: Telegram chat id.  Falls back to env ``TELEGRAM_CHAT_ID``.
    """

    def __init__(
        self,
        db_path: str = "",
        bot_token: str = "",
        chat_id: str = "",
    ) -> None:
        self._db_path = (
            db_path
            or os.getenv("DUCKDB_PATH", "")
            or "data/market_data.duckdb"
        )
        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _connect(self, read_only: bool = True) -> Any:
        """Open a DuckDB connection."""
        import duckdb

        return duckdb.connect(self._db_path, read_only=read_only)

    def _table_exists(self, con: Any, table: str = "shadow_trades") -> bool:
        """Check if a table exists in the database."""
        try:
            result = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = ?",
                [table],
            ).fetchone()
            return result[0] > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Trade stats query
    # ------------------------------------------------------------------

    def _fetch_stats(self, con: Any, date_filter: str, params: List[Any]) -> TradeStats:
        """Run aggregate queries and return TradeStats."""
        stats = TradeStats()

        # Total trades
        row = con.execute(
            f"SELECT COUNT(*) FROM shadow_trades WHERE {date_filter}", params
        ).fetchone()
        stats.total = row[0] if row else 0

        if stats.total == 0:
            return stats

        # Wins / losses (closed trades only)
        closed_filter = f"{date_filter} AND status = 'CLOSED'"
        row = con.execute(
            f"SELECT COUNT(*) FROM shadow_trades WHERE {closed_filter}", params
        ).fetchone()
        closed_count = row[0] if row else 0

        row = con.execute(
            f"SELECT COUNT(*) FROM shadow_trades WHERE {closed_filter} AND pnl_after_costs > 0",
            params,
        ).fetchone()
        stats.wins = row[0] if row else 0
        stats.losses = closed_count - stats.wins

        if closed_count > 0:
            stats.win_rate = stats.wins / closed_count

        # Avg win / avg loss
        row = con.execute(
            f"SELECT AVG(pnl_after_costs) FROM shadow_trades "
            f"WHERE {closed_filter} AND pnl_after_costs > 0",
            params,
        ).fetchone()
        stats.avg_win = row[0] if row and row[0] else 0.0

        row = con.execute(
            f"SELECT AVG(pnl_after_costs) FROM shadow_trades "
            f"WHERE {closed_filter} AND pnl_after_costs <= 0",
            params,
        ).fetchone()
        stats.avg_loss = abs(row[0]) if row and row[0] else 0.0

        # Payoff ratio
        stats.payoff_ratio = (
            stats.avg_win / stats.avg_loss if stats.avg_loss > 0 else 0.0
        )

        # Expectancy per trade
        stats.expectancy = (
            (stats.win_rate * stats.avg_win)
            - ((1 - stats.win_rate) * stats.avg_loss)
        )

        # Net PnL
        row = con.execute(
            f"SELECT COALESCE(SUM(pnl_after_costs), 0) FROM shadow_trades "
            f"WHERE {closed_filter}",
            params,
        ).fetchone()
        stats.net_pnl = row[0] if row else 0.0

        # Best / worst
        row = con.execute(
            f"SELECT MAX(pnl_after_costs), MIN(pnl_after_costs) "
            f"FROM shadow_trades WHERE {closed_filter}",
            params,
        ).fetchone()
        if row:
            stats.best_trade = row[0] if row[0] else 0.0
            stats.worst_trade = row[1] if row[1] else 0.0

        # Open positions
        open_filter = f"{date_filter} AND status = 'OPEN'"
        row = con.execute(
            f"SELECT COUNT(*) FROM shadow_trades WHERE {open_filter}", params
        ).fetchone()
        stats.open_positions = row[0] if row else 0

        return stats

    def _fetch_strategy_breakdown(
        self, con: Any, date_filter: str, params: List[Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Break down stats by strategy / signal source."""
        breakdown: Dict[str, Dict[str, Any]] = {}
        closed_filter = f"{date_filter} AND status = 'CLOSED'"

        try:
            rows = con.execute(
                f"SELECT "
                f"  COALESCE(ledger_hash, 'unknown') AS strategy, "
                f"  COUNT(*) AS total, "
                f"  SUM(CASE WHEN pnl_after_costs > 0 THEN 1 ELSE 0 END) AS wins, "
                f"  COALESCE(SUM(pnl_after_costs), 0) AS net_pnl "
                f"FROM shadow_trades "
                f"WHERE {closed_filter} "
                f"GROUP BY strategy "
                f"ORDER BY net_pnl DESC",
                params,
            ).fetchall()

            for row in rows:
                strategy = row[0]
                total = row[1]
                wins = row[2]
                net_pnl = row[3]
                breakdown[strategy] = {
                    "total": total,
                    "win_rate": wins / total if total > 0 else 0.0,
                    "net_pnl": net_pnl,
                }
        except Exception as exc:
            logger.warning("strategy_breakdown_error: %s", exc)

        return breakdown

    def _fetch_session_breakdown(
        self, con: Any, date_filter: str, params: List[Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Break down stats by trading session (Asian/London/NY)."""
        breakdown: Dict[str, Dict[str, Any]] = {}
        closed_filter = f"{date_filter} AND status = 'CLOSED'"

        try:
            rows = con.execute(
                f"SELECT "
                f"  CASE "
                f"    WHEN EXTRACT(HOUR FROM CAST(timestamp_utc AS TIMESTAMP)) BETWEEN 0 AND 7 THEN 'Asian' "
                f"    WHEN EXTRACT(HOUR FROM CAST(timestamp_utc AS TIMESTAMP)) BETWEEN 7 AND 12 THEN 'London' "
                f"    WHEN EXTRACT(HOUR FROM CAST(timestamp_utc AS TIMESTAMP)) BETWEEN 12 AND 17 THEN 'NY' "
                f"    ELSE 'Off-hours' "
                f"  END AS session, "
                f"  COUNT(*) AS total, "
                f"  SUM(CASE WHEN pnl_after_costs > 0 THEN 1 ELSE 0 END) AS wins, "
                f"  COALESCE(SUM(pnl_after_costs), 0) AS net_pnl "
                f"FROM shadow_trades "
                f"WHERE {closed_filter} "
                f"GROUP BY session "
                f"ORDER BY net_pnl DESC",
                params,
            ).fetchall()

            for row in rows:
                session = row[0]
                total = row[1]
                wins = row[2]
                net_pnl = row[3]
                breakdown[session] = {
                    "total": total,
                    "win_rate": wins / total if total > 0 else 0.0,
                    "net_pnl": net_pnl,
                }
        except Exception as exc:
            logger.warning("session_breakdown_error: %s", exc)

        return breakdown

    def _compute_sharpe(
        self, con: Any, date_filter: str, params: List[Any]
    ) -> float:
        """Compute annualized Sharpe ratio from daily returns."""
        try:
            rows = con.execute(
                f"SELECT "
                f"  DATE(timestamp_utc) AS trade_date, "
                f"  SUM(pnl_after_costs) AS daily_pnl "
                f"FROM shadow_trades "
                f"WHERE {date_filter} AND status = 'CLOSED' "
                f"GROUP BY trade_date "
                f"ORDER BY trade_date",
                params,
            ).fetchall()

            if len(rows) < 2:
                return 0.0

            returns = [r[1] for r in rows]
            mean_r = sum(returns) / len(returns)
            if mean_r == 0:
                return 0.0

            variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            std_r = variance ** 0.5
            if std_r == 0:
                return 0.0

            return (mean_r / std_r) * (252 ** 0.5)
        except Exception as exc:
            logger.warning("sharpe_computation_error: %s", exc)
            return 0.0

    def _compute_max_drawdown(
        self, con: Any, date_filter: str, params: List[Any]
    ) -> float:
        """Compute max drawdown from cumulative PnL."""
        try:
            rows = con.execute(
                f"SELECT SUM(pnl_after_costs) AS daily_pnl "
                f"FROM shadow_trades "
                f"WHERE {date_filter} AND status = 'CLOSED' "
                f"GROUP BY DATE(timestamp_utc) "
                f"ORDER BY DATE(timestamp_utc)",
                params,
            ).fetchall()

            if not rows:
                return 0.0

            cumulative = 0.0
            peak = 0.0
            max_dd = 0.0

            for row in rows:
                cumulative += row[0]
                if cumulative > peak:
                    peak = cumulative
                dd = peak - cumulative
                if dd > max_dd:
                    max_dd = dd

            return max_dd
        except Exception as exc:
            logger.warning("max_drawdown_error: %s", exc)
            return 0.0

    def _compute_profit_factor(
        self, con: Any, date_filter: str, params: List[Any]
    ) -> float:
        """Compute profit factor (gross wins / gross losses)."""
        try:
            row = con.execute(
                f"SELECT "
                f"  COALESCE(SUM(CASE WHEN pnl_after_costs > 0 THEN pnl_after_costs ELSE 0 END), 0), "
                f"  COALESCE(SUM(CASE WHEN pnl_after_costs < 0 THEN ABS(pnl_after_costs) ELSE 0 END), 0) "
                f"FROM shadow_trades "
                f"WHERE {date_filter} AND status = 'CLOSED'",
                params,
            ).fetchone()

            gross_wins = row[0]
            gross_losses = row[1]

            if gross_losses == 0:
                return float("inf") if gross_wins > 0 else 0.0
            return gross_wins / gross_losses
        except Exception as exc:
            logger.warning("profit_factor_error: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_daily_report(self, target_date: Optional[datetime] = None) -> str:
        """Generate a daily expectancy report as Telegram HTML.

        Args:
            target_date: Date to report on.  Defaults to today (UTC).

        Returns:
            HTML-formatted string ready for Telegram ``parse_mode=HTML``.
        """
        if target_date is None:
            target_date = datetime.now(UTC)

        date_str = target_date.strftime("%Y-%m-%d")
        con = self._connect(read_only=True)

        try:
            if not self._table_exists(con):
                return self._empty_report(date_str, "shadow_trades table not found")

            date_filter = "DATE(timestamp_utc) = ?"
            params: List[Any] = [date_str]

            stats = self._fetch_stats(con, date_filter, params)
            strategy = self._fetch_strategy_breakdown(con, date_filter, params)

            stats.by_strategy = strategy

            return self._format_daily(date_str, stats)
        finally:
            con.close()

    def generate_weekly_report(
        self, end_date: Optional[datetime] = None
    ) -> str:
        """Generate a weekly expectancy report as Telegram HTML.

        Args:
            end_date: Last day of the week.  Defaults to today (UTC).

        Returns:
            HTML-formatted string ready for Telegram ``parse_mode=HTML``.
        """
        if end_date is None:
            end_date = datetime.now(UTC)

        start_date = end_date - timedelta(days=6)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        con = self._connect(read_only=True)

        try:
            if not self._table_exists(con):
                return self._empty_report(
                    f"{start_str} to {end_str}", "shadow_trades table not found"
                )

            date_filter = "DATE(timestamp_utc) BETWEEN ? AND ?"
            params: List[Any] = [start_str, end_str]

            stats = self._fetch_stats(con, date_filter, params)
            stats.sharpe_ratio = self._compute_sharpe(con, date_filter, params)
            stats.max_drawdown = self._compute_max_drawdown(con, date_filter, params)
            stats.profit_factor = self._compute_profit_factor(con, date_filter, params)
            stats.by_strategy = self._fetch_strategy_breakdown(con, date_filter, params)
            stats.by_session = self._fetch_session_breakdown(con, date_filter, params)

            return self._format_weekly(start_str, end_str, stats)
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pnl_color(value: float) -> str:
        """Return colored string for Telegram."""
        if value > 0:
            return f"+${value:,.2f}"
        elif value < 0:
            return f"-${abs(value):,.2f}"
        return "$0.00"

    @staticmethod
    def _pct(value: float) -> str:
        """Format as percentage."""
        return f"{value:.1%}"

    def _empty_report(self, period: str, reason: str) -> str:
        """Return an HTML message for no-data scenarios."""
        return (
            f"📊 <b>Shadow Report</b>\n"
            f"📅 {period}\n\n"
            f"⚠️ {reason}\n\n"
            f"<i>No data available.</i>"
        )

    def _format_daily(self, date_str: str, stats: TradeStats) -> str:
        """Format daily stats as Telegram HTML."""
        pnl_str = self._pnl_color(stats.net_pnl)
        wr_str = self._pct(stats.win_rate)
        exp_str = self._pnl_color(stats.expectancy)

        lines = [
            "📊 <b>Shadow Daily Report</b>",
            f"📅 {date_str}",
            "",
            f"📈 <b>Trades:</b> {stats.total}",
            f"✅ <b>Win Rate:</b> {wr_str} ({stats.wins}W / {stats.losses}L)",
            "",
            f"💰 <b>Avg Win:</b> ${stats.avg_win:,.2f}",
            f"💸 <b>Avg Loss:</b> ${stats.avg_loss:,.2f}",
            f"⚖️ <b>Payoff Ratio:</b> {stats.payoff_ratio:.2f}",
            "",
            f"🎯 <b>Expectancy/Trade:</b> {exp_str}",
            f"💵 <b>Net P&L:</b> {pnl_str}",
            "",
            f"🏆 <b>Best:</b> ${stats.best_trade:+,.2f}",
            f"💔 <b>Worst:</b> ${stats.worst_trade:+,.2f}",
            f"📍 <b>Open Positions:</b> {stats.open_positions}",
        ]

        if stats.by_strategy:
            lines.append("")
            lines.append("📋 <b>By Strategy:</b>")
            for strat, data in stats.by_strategy.items():
                short_hash = strat[:8] if len(strat) > 8 else strat
                wr = self._pct(data["win_rate"])
                pnl = self._pnl_color(data["net_pnl"])
                lines.append(
                    f"  <code>{short_hash}</code>: "
                    f"{data['total']}T | {wr} WR | {pnl}"
                )

        return "\n".join(lines)

    def _format_weekly(
        self, start_str: str, end_str: str, stats: TradeStats
    ) -> str:
        """Format weekly stats as Telegram HTML."""
        pnl_str = self._pnl_color(stats.net_pnl)
        wr_str = self._pct(stats.win_rate)
        exp_str = self._pnl_color(stats.expectancy)
        dd_str = f"${stats.max_drawdown:,.2f}"

        pf_str = (
            f"{stats.profit_factor:.2f}"
            if stats.profit_factor != float("inf")
            else "∞"
        )

        lines = [
            "📊 <b>Shadow Weekly Report</b>",
            f"📅 {start_str} → {end_str}",
            "",
            f"📈 <b>Trades:</b> {stats.total}",
            f"✅ <b>Win Rate:</b> {wr_str} ({stats.wins}W / {stats.losses}L)",
            "",
            f"💰 <b>Avg Win:</b> ${stats.avg_win:,.2f}",
            f"💸 <b>Avg Loss:</b> ${stats.avg_loss:,.2f}",
            f"⚖️ <b>Payoff Ratio:</b> {stats.payoff_ratio:.2f}",
            "",
            f"🎯 <b>Expectancy/Trade:</b> {exp_str}",
            f"💵 <b>Net P&L:</b> {pnl_str}",
            "",
            f"📉 <b>Max Drawdown:</b> {dd_str}",
            f"📊 <b>Sharpe Ratio:</b> {stats.sharpe_ratio:.2f}",
            f"🔢 <b>Profit Factor:</b> {pf_str}",
            "",
            f"🏆 <b>Best:</b> ${stats.best_trade:+,.2f}",
            f"💔 <b>Worst:</b> ${stats.worst_trade:+,.2f}",
            f"📍 <b>Open Positions:</b> {stats.open_positions}",
        ]

        if stats.by_strategy:
            lines.append("")
            lines.append("📋 <b>By Strategy:</b>")
            for strat, data in stats.by_strategy.items():
                short_hash = strat[:8] if len(strat) > 8 else strat
                wr = self._pct(data["win_rate"])
                pnl = self._pnl_color(data["net_pnl"])
                lines.append(
                    f"  <code>{short_hash}</code>: "
                    f"{data['total']}T | {wr} WR | {pnl}"
                )

        if stats.by_session:
            lines.append("")
            lines.append("🌍 <b>By Session:</b>")
            for session, data in stats.by_session.items():
                wr = self._pct(data["win_rate"])
                pnl = self._pnl_color(data["net_pnl"])
                lines.append(
                    f"  {session}: {data['total']}T | {wr} WR | {pnl}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Telegram delivery
    # ------------------------------------------------------------------

    def send_to_telegram(self, report_text: str) -> bool:
        """Send a report to Telegram via httpx.

        Args:
            report_text: HTML-formatted message body.

        Returns:
            ``True`` on success, ``False`` on error.
        """
        if not self._bot_token or not self._chat_id:
            logger.error("Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": report_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info("telegram_send_ok length=%d", len(report_text))
                    return True
                logger.error(
                    "telegram_send_failed status=%d body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False
        except Exception as exc:
            logger.exception("telegram_send_error: %s", exc)
            return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI: generate and send the daily shadow report."""
    import argparse

    parser = argparse.ArgumentParser(description="Shadow trade daily report")
    parser.add_argument(
        "--weekly", action="store_true", help="Generate weekly report instead"
    )
    parser.add_argument("--db-path", default="", help="DuckDB path override")
    parser.add_argument("--send", action="store_true", help="Send to Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no send")
    args = parser.parse_args()

    report = ShadowReport(db_path=args.db_path)

    if args.weekly:
        text = report.generate_weekly_report()
    else:
        text = report.generate_daily_report()

    print(text)

    if args.send and not args.dry_run:
        ok = report.send_to_telegram(text)
        if ok:
            print("\n[OK] Sent to Telegram.")
        else:
            print("\n[FAIL] Telegram send failed.")


if __name__ == "__main__":
    main()
