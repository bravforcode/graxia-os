"""SQLite persistence for collected Myfxbook data. Stdlib only."""

import datetime
import sqlite3

from market_data.myfxbook.models import AccountSummary, EquityPoint

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    member TEXT NOT NULL,
    system TEXT NOT NULL,
    url TEXT NOT NULL,
    name TEXT,
    verified INTEGER,
    gain_pct REAL, abs_gain_pct REAL, daily_pct REAL, monthly_pct REAL,
    max_drawdown_pct REAL, balance REAL, currency TEXT,
    profit_factor REAL, sharpe REAL, win_rate_pct REAL,
    total_trades INTEGER, tracked_months INTEGER,
    last_updated TEXT NOT NULL,
    filter_pass INTEGER NOT NULL DEFAULT 0,
    filter_reasons TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS equity_points (
    account_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    equity REAL NOT NULL,
    PRIMARY KEY (account_id, month)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def _b(value: bool | None) -> int | None:
    return None if value is None else int(value)


def upsert_account(conn: sqlite3.Connection, summary: AccountSummary) -> None:
    stamp = summary.last_updated or datetime.date.today().isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO accounts (
            account_id, member, system, url, name, verified,
            gain_pct, abs_gain_pct, daily_pct, monthly_pct, max_drawdown_pct,
            balance, currency, profit_factor, sharpe, win_rate_pct,
            total_trades, tracked_months, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary.account_id,
            summary.member,
            summary.system,
            summary.url,
            summary.name,
            _b(summary.verified),
            summary.gain_pct,
            summary.abs_gain_pct,
            summary.daily_pct,
            summary.monthly_pct,
            summary.max_drawdown_pct,
            summary.balance,
            summary.currency,
            summary.profit_factor,
            summary.sharpe,
            summary.win_rate_pct,
            summary.total_trades,
            summary.tracked_months,
            stamp,
        ),
    )
    conn.commit()


def insert_equity_points(conn: sqlite3.Connection, points: list[EquityPoint]) -> int:
    for point in points:
        conn.execute(
            "INSERT OR REPLACE INTO equity_points (account_id, month, equity) VALUES (?, ?, ?)",
            (point.account_id, point.month, point.equity),
        )
    conn.commit()
    return len(points)


def list_accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM accounts ORDER BY last_updated DESC").fetchall()
    return [dict(row) for row in rows]


def get_account(conn: sqlite3.Connection, account_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    return dict(row) if row else None
