"""SQLite persistence layer for the autonomous trading loop.

Stores trade decisions, execution logs, daily stats, and system health
for crash recovery and audit trails.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    entry REAL NOT NULL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    reasoning TEXT NOT NULL DEFAULT '',
    red_flags TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '',
    snapshot_ts TEXT,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    llm_provider TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    order_id TEXT NOT NULL DEFAULT '',
    broker_order_id TEXT,
    error TEXT NOT NULL DEFAULT '',
    approval_required INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    trades_today INTEGER NOT NULL DEFAULT 0,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    open_positions INTEGER NOT NULL DEFAULT 0,
    max_drawdown REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    uptime_seconds REAL NOT NULL DEFAULT 0.0,
    total_decisions INTEGER NOT NULL DEFAULT 0,
    total_trades INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    kill_switch_active INTEGER NOT NULL DEFAULT 0
);
"""


class TradeStore:
    """SQLite persistence for autonomous trading loop."""

    def __init__(self, db_path: str = "data/autonomous_trades.db") -> None:
        self._db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    def save_decision(self, decision: dict[str, Any]) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO decisions
               (symbol, direction, confidence, entry, sl, tp, reasoning,
                red_flags, timestamp, timeframe, snapshot_ts, latency_ms, llm_provider)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.get("symbol", ""),
                decision.get("direction", ""),
                decision.get("confidence", 0.0),
                decision.get("entry", 0.0),
                decision.get("sl", 0.0),
                decision.get("tp", 0.0),
                decision.get("reasoning", ""),
                decision.get("red_flags", ""),
                decision.get("timestamp", datetime.now(tz=UTC).isoformat()),
                decision.get("timeframe", ""),
                decision.get("snapshot_ts", ""),
                decision.get("latency_ms", 0.0),
                decision.get("llm_provider", ""),
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.debug("persistence_decision_saved", row_id=row_id, symbol=decision.get("symbol"))
        return row_id or 0

    def save_execution(self, execution: dict[str, Any]) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO executions
               (decision_id, symbol, direction, confidence, entry, stop_loss,
                take_profit, success, order_id, broker_order_id, error,
                approval_required, mode, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution.get("decision_id"),
                execution.get("symbol", ""),
                execution.get("direction", ""),
                execution.get("confidence", 0.0),
                execution.get("entry", 0.0),
                execution.get("stop_loss", 0.0),
                execution.get("take_profit", 0.0),
                int(execution.get("success", False)),
                execution.get("order_id", ""),
                execution.get("broker_order_id"),
                execution.get("error", ""),
                int(execution.get("approval_required", False)),
                execution.get("mode", ""),
                execution.get("timestamp", datetime.now(tz=UTC).isoformat()),
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.debug("persistence_execution_saved", row_id=row_id)
        return row_id or 0

    def get_daily_stats(self, date: str) -> dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM daily_stats WHERE date = ?", (date,)).fetchone()
        if row:
            return dict(row)
        return {
            "date": date,
            "trades_today": 0,
            "realized_pnl": 0.0,
            "open_positions": 0,
            "max_drawdown": 0.0,
        }

    def save_health(self, health: dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO health
               (timestamp, uptime_seconds, total_decisions, total_trades,
                errors, kill_switch_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                health.get("timestamp", datetime.now(tz=UTC).isoformat()),
                health.get("uptime_seconds", 0.0),
                health.get("total_decisions", 0),
                health.get("total_trades", 0),
                health.get("errors", 0),
                int(health.get("kill_switch_active", False)),
            ),
        )
        conn.commit()

    def get_recent_decisions(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM decisions WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_execution_log(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
