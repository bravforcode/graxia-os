"""DuckDB persistence for Thaifxbook snapshots.

INV-014 exception (documented per review 2026-08-06):
  We deliberately do NOT reuse ``data.warehouse_loader.Warehouse`` or
  ``data_pipeline/storage/duckdb_store.py``. Reason: quant_os's production
  warehouse (``data/warehouse/quantos.duckdb``) has a documented history of
  6x OHLCV duplication (MEGA_PLAN_v2 F24) and ``duckdb_store.py`` carries known
  bugs (DEEP_AUDIT_FINDINGS.md P2-10/11/12: DELETE+INSERT without transaction,
  no PRIMARY KEY). Thaifxbook is an UNVERIFIED-at-scale third-party feed
  (platform is ~1 month old); writing it into the same file as core trading
  infra risks contaminating production data. This store therefore mirrors the
  myfxbook collector's isolation (its own file) while copying the *safety
  pattern* from Warehouse: explicit transaction(), _safe_ident() identifier
  checks, and PRIMARY KEYs on every table. The pattern is copied WITH
  regression tests (test_store.py) proving atomic writes — not just copied
  by eye. INV-014 targets duplicated *logic that drifts*; here the storage
  domain is intentionally separate and the safety invariants are tested.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import duckdb

from .models import ProfileSnapshot, SentimentSnapshot, TradeRecord

_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_snapshots (
    ts TIMESTAMP NOT NULL,
    asset VARCHAR NOT NULL,
    asset_display VARCHAR,
    long_pct_by_trader DOUBLE,
    short_pct_by_trader DOUBLE,
    traders INTEGER,
    lots DOUBLE,
    floating_pl_usd DOUBLE,
    PRIMARY KEY (ts, asset)
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    account_uuid VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    rank INTEGER,
    trader VARCHAR,
    account_name VARCHAR,
    broker VARCHAR,
    verified BOOLEAN,
    leverage VARCHAR,
    start_date VARCHAR,
    last_sync VARCHAR,
    balance_usd DOUBLE,
    equity_usd DOUBLE,
    deposits_usd DOUBLE,
    withdrawals_usd DOUBLE,
    profit_usd DOUBLE,
    max_balance_usd DOUBLE,
    gain_pct DOUBLE,
    abs_gain_pct DOUBLE,
    daily_pct DOUBLE,
    monthly_pct DOUBLE,
    max_drawdown_pct DOUBLE,
    profit_factor DOUBLE,
    expected_payoff DOUBLE,
    sharpe DOUBLE,
    win_rate_pct DOUBLE,
    total_trades INTEGER,
    ea_pct DOUBLE,
    manual_pct DOUBLE,
    ai_accuracy DOUBLE,
    ai_profitability DOUBLE,
    ai_risk DOUBLE,
    ai_consistency DOUBLE,
    ai_recovery DOUBLE,
    masked BOOLEAN,
    PRIMARY KEY (account_uuid, ts)
);

CREATE TABLE IF NOT EXISTS profile_trades (
    account_uuid VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    seq INTEGER NOT NULL,
    ticket BIGINT,
    symbol VARCHAR,
    side VARCHAR,
    lots DOUBLE,
    pnl_usd DOUBLE,
    close_time VARCHAR,
    open_time VARCHAR,
    open_price DOUBLE,
    close_price DOUBLE,
    pips DOUBLE,
    sl DOUBLE,
    tp DOUBLE,
    comment VARCHAR,
    PRIMARY KEY (account_uuid, ts, seq)
);
"""


class ThaifxbookStore:
    """DuckDB store with atomic batch writes and explicit PKs."""

    def __init__(self, db_path: str) -> None:
        # NOTE: no PRAGMA foreign_keys — DuckDB does not support the SQLite
        # syntax (the P0-4 bug class from the legacy duckdb_store.py). PKs are
        # the integrity mechanism here.
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._init_tables()

    # -- safety -----------------------------------------------------------

    def _safe_ident(self, name: str) -> str:
        if not _SQL_IDENT_RE.match(name):
            raise ValueError(f"unsafe SQL identifier: {name!r}")
        return name

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Explicit BEGIN/COMMIT/ROLLBACK — copied pattern from Warehouse."""
        self._conn.begin()
        try:
            yield
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    # -- schema -----------------------------------------------------------

    def _init_tables(self) -> None:
        self._conn.execute("BEGIN TRANSACTION")
        try:
            for stmt in _SCHEMA.split(";\n"):
                stmt = stmt.strip()
                if stmt:
                    self._conn.execute(stmt)
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    # -- writes (each batch atomic) ----------------------------------------

    def upsert_sentiment_snapshots(self, rows: Sequence[SentimentSnapshot]) -> int:
        if not rows:
            return 0
        cols = [
            "ts",
            "asset",
            "asset_display",
            "long_pct_by_trader",
            "short_pct_by_trader",
            "traders",
            "lots",
            "floating_pl_usd",
        ]
        safe = ", ".join(self._safe_ident(c) for c in cols)
        with self.transaction():
            self._conn.executemany(
                f"INSERT INTO sentiment_snapshots ({safe}) VALUES (?,?,?,?,?,?,?,?) "
                f"ON CONFLICT (ts, asset) DO UPDATE SET "
                f"asset_display=excluded.asset_display, "
                f"long_pct_by_trader=excluded.long_pct_by_trader, "
                f"short_pct_by_trader=excluded.short_pct_by_trader, "
                f"traders=excluded.traders, lots=excluded.lots, "
                f"floating_pl_usd=excluded.floating_pl_usd",
                [
                    (
                        r.ts,
                        r.asset,
                        r.asset_display,
                        r.long_pct_by_trader,
                        r.short_pct_by_trader,
                        r.traders,
                        r.lots,
                        r.floating_pl_usd,
                    )
                    for r in rows
                ],
            )
        return len(rows)

    def upsert_profile_snapshots(self, rows: Sequence[ProfileSnapshot]) -> int:
        if not rows:
            return 0
        cols = [
            "account_uuid",
            "ts",
            "rank",
            "trader",
            "account_name",
            "broker",
            "verified",
            "leverage",
            "start_date",
            "last_sync",
            "balance_usd",
            "equity_usd",
            "deposits_usd",
            "withdrawals_usd",
            "profit_usd",
            "max_balance_usd",
            "gain_pct",
            "abs_gain_pct",
            "daily_pct",
            "monthly_pct",
            "max_drawdown_pct",
            "profit_factor",
            "expected_payoff",
            "sharpe",
            "win_rate_pct",
            "total_trades",
            "ea_pct",
            "manual_pct",
            "ai_accuracy",
            "ai_profitability",
            "ai_risk",
            "ai_consistency",
            "ai_recovery",
            "masked",
        ]
        safe = ", ".join(self._safe_ident(c) for c in cols)
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols[2:])
        with self.transaction():
            self._conn.executemany(
                f"INSERT INTO profile_snapshots ({safe}) VALUES ({placeholders}) "
                f"ON CONFLICT (account_uuid, ts) DO UPDATE SET {updates}",
                [
                    (
                        r.account_uuid,
                        r.ts,
                        r.rank,
                        r.trader,
                        r.account_name,
                        r.broker,
                        r.verified,
                        r.leverage,
                        r.start_date,
                        r.last_sync,
                        r.balance_usd,
                        r.equity_usd,
                        r.deposits_usd,
                        r.withdrawals_usd,
                        r.profit_usd,
                        r.max_balance_usd,
                        r.gain_pct,
                        r.abs_gain_pct,
                        r.daily_pct,
                        r.monthly_pct,
                        r.max_drawdown_pct,
                        r.profit_factor,
                        r.expected_payoff,
                        r.sharpe,
                        r.win_rate_pct,
                        r.total_trades,
                        r.ea_pct,
                        r.manual_pct,
                        r.ai_accuracy,
                        r.ai_profitability,
                        r.ai_risk,
                        r.ai_consistency,
                        r.ai_recovery,
                        r.masked,
                    )
                    for r in rows
                ],
            )
        return len(rows)

    def upsert_profile_trades(self, rows: Sequence[TradeRecord]) -> int:
        if not rows:
            return 0
        cols = [
            "account_uuid",
            "ts",
            "seq",
            "ticket",
            "symbol",
            "side",
            "lots",
            "pnl_usd",
            "close_time",
            "open_time",
            "open_price",
            "close_price",
            "pips",
            "sl",
            "tp",
            "comment",
        ]
        safe = ", ".join(self._safe_ident(c) for c in cols)
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols[3:])
        with self.transaction():
            self._conn.executemany(
                f"INSERT INTO profile_trades ({safe}) VALUES ({placeholders}) "
                f"ON CONFLICT (account_uuid, ts, seq) DO UPDATE SET {updates}",
                [
                    (
                        r.account_uuid,
                        r.ts,
                        r.seq,
                        r.ticket,
                        r.symbol,
                        r.side,
                        r.lots,
                        r.pnl_usd,
                        r.close_time,
                        r.open_time,
                        r.open_price,
                        r.close_price,
                        r.pips,
                        r.sl,
                        r.tp,
                        r.comment,
                    )
                    for r in rows
                ],
            )
        return len(rows)

    # -- reads --------------------------------------------------------------

    def count_rows(self, table: str) -> int:
        safe = self._safe_ident(table)
        return int(self._conn.execute(f"SELECT COUNT(*) FROM {safe}").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ThaifxbookStore:
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.close()
