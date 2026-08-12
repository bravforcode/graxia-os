"""
Expectancy Analysis — SQL-driven trade performance analytics.

Queries the shadow_trades table in DuckDB and produces a formatted report
covering win rate, expectancy, Sharpe ratio, max drawdown, profit factor,
and breakdowns by strategy and trading session.

Usage:
    python -m analysis.expectancy --db data/shadow_trades.duckdb
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional, Tuple

import duckdb

# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

SQL_STATS = """
WITH closed AS (
    SELECT
        trade_id,
        symbol,
        side,
        entry_price,
        exit_price,
        quantity,
        pnl,
        pnl_pct,
        strategy,
        signal_id,
        opened_at,
        closed_at,
        close_reason
    FROM shadow_trades
    WHERE status = 'CLOSED'
),
summary AS (
    SELECT
        COUNT(*)                                              AS total_trades,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)             AS wins,
        SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END)            AS losses,
        AVG(CASE WHEN pnl > 0 THEN pnl END)                  AS avg_win,
        AVG(CASE WHEN pnl <= 0 THEN ABS(pnl) END)            AS avg_loss,
        SUM(pnl)                                              AS net_profit,
        SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END)           AS gross_profit,
        SUM(CASE WHEN pnl <= 0 THEN ABS(pnl) ELSE 0 END)     AS gross_loss
    FROM closed
)
SELECT
    total_trades,
    wins,
    losses,
    ROUND(wins * 100.0 / NULLIF(total_trades, 0), 2)   AS win_rate_pct,
    ROUND(avg_win, 4)                                   AS avg_win,
    ROUND(avg_loss, 4)                                  AS avg_loss,
    ROUND(avg_win / NULLIF(avg_loss, 0), 4)             AS payoff_ratio,
    ROUND(net_profit, 4)                                AS net_profit,
    ROUND(gross_profit, 4)                              AS gross_profit,
    ROUND(gross_loss, 4)                                AS gross_loss,
    ROUND(
        gross_profit / NULLIF(gross_loss, 0), 4
    )                                                   AS profit_factor,
    ROUND(
        (wins * 100.0 / NULLIF(total_trades, 0) / 100.0
         * avg_win)
        - ((1 - wins * 100.0 / NULLIF(total_trades, 0) / 100.0)
           * avg_loss),
        4
    )                                                   AS expectancy
FROM summary;
"""

SQL_SHARPE = """
WITH closed AS (
    SELECT
        pnl / NULLIF(entry_price * quantity, 0) AS ret
    FROM shadow_trades
    WHERE status = 'CLOSED'
),
stats AS (
    SELECT
        AVG(ret)   AS mean_ret,
        STDDEV(ret) AS std_ret,
        COUNT(*)   AS n
    FROM closed
    WHERE ret IS NOT NULL
)
SELECT
    n,
    ROUND(mean_ret, 8)                                    AS mean_return,
    ROUND(std_ret, 8)                                     AS std_return,
    ROUND(
        mean_ret / NULLIF(std_ret, 0) * SQRT(252),
        4
    )                                                     AS sharpe_ratio
FROM stats;
"""

SQL_MAX_DRAWDOWN = """
WITH closed AS (
    SELECT
        trade_id,
        pnl,
        opened_at
    FROM shadow_trades
    WHERE status = 'CLOSED'
    ORDER BY opened_at
),
equity AS (
    SELECT
        trade_id,
        opened_at,
        SUM(pnl) OVER (ORDER BY opened_at) AS cumulative_pnl
    FROM closed
),
peak AS (
    SELECT
        trade_id,
        opened_at,
        cumulative_pnl,
        MAX(cumulative_pnl) OVER (ORDER BY opened_at) AS peak_pnl
    FROM equity
)
SELECT
    ROUND(MIN(cumulative_pnl - peak_pnl), 4)              AS max_drawdown,
    ROUND(
        MIN(
            (cumulative_pnl - peak_pnl)
            / NULLIF(peak_pnl, 0) * 100.0
        ),
        4
    )                                                     AS max_drawdown_pct
FROM peak;
"""

SQL_BY_STRATEGY = """
WITH closed AS (
    SELECT
        strategy,
        pnl,
        entry_price,
        quantity
    FROM shadow_trades
    WHERE status = 'CLOSED'
)
SELECT
    strategy,
    COUNT(*)                                              AS trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)             AS wins,
    ROUND(
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0
        / NULLIF(COUNT(*), 0),
        2
    )                                                     AS win_rate_pct,
    ROUND(AVG(pnl), 4)                                    AS avg_pnl,
    ROUND(SUM(pnl), 4)                                    AS total_pnl,
    ROUND(
        SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END)
        / NULLIF(SUM(CASE WHEN pnl <= 0 THEN ABS(pnl) ELSE 0 END), 0),
        4
    )                                                     AS profit_factor
FROM closed
GROUP BY strategy
ORDER BY total_pnl DESC;
"""

SQL_BY_SESSION = """
WITH closed AS (
    SELECT
        pnl,
        opened_at,
        CASE
            WHEN EXTRACT(HOUR FROM opened_at) >= 0
                 AND EXTRACT(HOUR FROM opened_at) < 7
            THEN 'Asian'
            WHEN EXTRACT(HOUR FROM opened_at) >= 7
                 AND EXTRACT(HOUR FROM opened_at) < 13
            THEN 'London'
            WHEN EXTRACT(HOUR FROM opened_at) >= 13
                 AND EXTRACT(HOUR FROM opened_at) < 21
            THEN 'NewYork'
            ELSE 'Asian'
        END AS session
    FROM shadow_trades
    WHERE status = 'CLOSED'
)
SELECT
    session,
    COUNT(*)                                              AS trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)             AS wins,
    ROUND(
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0
        / NULLIF(COUNT(*), 0),
        2
    )                                                     AS win_rate_pct,
    ROUND(AVG(pnl), 4)                                    AS avg_pnl,
    ROUND(SUM(pnl), 4)                                    AS total_pnl
FROM closed
GROUP BY session
ORDER BY
    CASE session
        WHEN 'Asian' THEN 1
        WHEN 'London' THEN 2
        WHEN 'NewYork' THEN 3
    END;
"""

MIN_TRADES_WARNING: int = 30


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_row(vals: Tuple[Any, ...], widths: List[int]) -> str:
    """Format a tuple of values into a fixed-width table row."""
    parts = []
    for v, w in zip(vals, widths):
        if v is None:
            parts.append("".ljust(w))
        elif isinstance(v, float):
            parts.append(f"{v:>{w}.4f}")
        elif isinstance(v, int):
            parts.append(f"{v:>{w}}")
        else:
            parts.append(f"{str(v):>{w}}")
    return " | ".join(parts)


def _print_table(
    headers: List[str],
    rows: List[Tuple[Any, ...]],
    widths: Optional[List[int]] = None,
) -> None:
    """Print a formatted ASCII table."""
    if widths is None:
        widths = []
        for i, h in enumerate(headers):
            col_max = max(len(h), *(len(str(r[i])) for r in rows) if rows else [0])
            widths.append(max(col_max, 6) + 2)

    sep = "+".join("-" * w for w in widths)
    print(f"+{sep}+")
    print(f"|{_fmt_row(tuple(headers), widths)}|")
    print(f"+{sep}+")
    for row in rows:
        print(f"|{_fmt_row(row, widths)}|")
    print(f"+{sep}+")


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

def run_expectancy_analysis(db_path: str = "data/shadow_trades.duckdb") -> None:
    """
    Run the full expectancy analysis and print a formatted report.

    Args:
        db_path: Path to the DuckDB database file.
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        print(f"[ERROR] Cannot open database: {db_path}\n{exc}", file=sys.stderr)
        sys.exit(1)

    # ── Minimum trades check ────────────────────────────────────────────
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM shadow_trades WHERE status = 'CLOSED'"
        ).fetchone()
        total = count_row[0] if count_row else 0
    except Exception as exc:
        print(f"[ERROR] Cannot query shadow_trades: {exc}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    if total < MIN_TRADES_WARNING:
        print(
            f"[WARNING] Only {total} closed trades found. "
            f"Minimum recommended: {MIN_TRADES_WARNING}. "
            f"Results may not be statistically significant.\n",
            file=sys.stderr,
        )

    # ── Header ──────────────────────────────────────────────────────────
    print("=" * 72)
    print("  EXPECTANCY ANALYSIS REPORT")
    print(f"  Database: {db_path}")
    print(f"  Total closed trades: {total}")
    print("=" * 72)
    print()

    # ── Core stats ──────────────────────────────────────────────────────
    print("─── CORE STATISTICS ───────────────────────────────────────")
    try:
        row = conn.execute(SQL_STATS).fetchone()
        if row is None:
            print("  No data available.\n")
        else:
            (
                total_trades, wins, losses, win_rate_pct,
                avg_win, avg_loss, payoff_ratio, net_profit,
                gross_profit, gross_loss, profit_factor, expectancy,
            ) = row
            print(f"  Total trades:     {total_trades}")
            print(f"  Wins / Losses:    {wins} / {losses}")
            print(f"  Win rate:         {win_rate_pct}%")
            print(f"  Avg win:          {avg_win}")
            print(f"  Avg loss:         {avg_loss}")
            print(f"  Payoff ratio:     {payoff_ratio}")
            print(f"  Net profit:       {net_profit}")
            print(f"  Profit factor:    {profit_factor}")
            print(f"  Expectancy:       {expectancy}")
            print()
    except Exception as exc:
        print(f"  [ERROR] {exc}\n")

    # ── Sharpe ratio ────────────────────────────────────────────────────
    print("─── SHARPE RATIO ──────────────────────────────────────────")
    try:
        row = conn.execute(SQL_SHARPE).fetchone()
        if row is None or row[0] == 0:
            print("  No return data available.\n")
        else:
            n, mean_ret, std_ret, sharpe = row
            print(f"  Sample size (n):  {n}")
            print(f"  Mean return:      {mean_ret}")
            print(f"  Std deviation:    {std_ret}")
            print(f"  Sharpe ratio:     {sharpe}")
            print()
    except Exception as exc:
        print(f"  [ERROR] {exc}\n")

    # ── Max drawdown ────────────────────────────────────────────────────
    print("─── MAX DRAWDOWN ──────────────────────────────────────────")
    try:
        row = conn.execute(SQL_MAX_DRAWDOWN).fetchone()
        if row is None or row[0] is None:
            print("  No equity data available.\n")
        else:
            dd_abs, dd_pct = row
            print(f"  Max drawdown:     {dd_abs}")
            print(f"  Max drawdown %:   {dd_pct}%")
            print()
    except Exception as exc:
        print(f"  [ERROR] {exc}\n")

    # ── By strategy ─────────────────────────────────────────────────────
    print("─── BY STRATEGY ───────────────────────────────────────────")
    try:
        rows = conn.execute(SQL_BY_STRATEGY).fetchall()
        if not rows:
            print("  No strategy data available.\n")
        else:
            headers = ["Strategy", "Trades", "Wins", "Win%", "AvgPnL", "TotalPnL", "PF"]
            _print_table(headers, rows)
            print()
    except Exception as exc:
        print(f"  [ERROR] {exc}\n")

    # ── By session ──────────────────────────────────────────────────────
    print("─── BY SESSION (UTC) ──────────────────────────────────────")
    try:
        rows = conn.execute(SQL_BY_SESSION).fetchall()
        if not rows:
            print("  No session data available.\n")
        else:
            headers = ["Session", "Trades", "Wins", "Win%", "AvgPnL", "TotalPnL"]
            _print_table(headers, rows)
            print()
    except Exception as exc:
        print(f"  [ERROR] {exc}\n")

    print("=" * 72)
    print("  END OF REPORT")
    print("=" * 72)

    conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for expectancy analysis."""
    parser = argparse.ArgumentParser(
        description="Expectancy analysis for shadow trades."
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default="data/shadow_trades.duckdb",
        help="Path to DuckDB database (default: data/shadow_trades.duckdb)",
    )
    args = parser.parse_args()
    run_expectancy_analysis(db_path=args.db_path)


if __name__ == "__main__":
    main()
