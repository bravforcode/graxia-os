"""Transaction-safety regression tests for ThaifxbookStore.

Required by the P0 review gate (2026-08-06): the Warehouse transaction() /
_safe_ident() pattern is copied deliberately (INV-014 exception documented in
store.py) and MUST be proven by tests, not just by code review:
  1. a failing batch rolls back atomically (no partial writes),
  2. PRIMARY KEYs prevent duplicate accumulation,
  3. upserts overwrite (ON CONFLICT) instead of duplicating,
  4. _safe_ident rejects injection-style identifiers,
  5. schema init is itself atomic.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from market_data.thaifxbook.models import ProfileSnapshot, SentimentSnapshot, TradeRecord
from market_data.thaifxbook.store import ThaifxbookStore


@pytest.fixture()
def store(tmp_path):
    s = ThaifxbookStore(str(tmp_path / "test.duckdb"))
    yield s
    s.close()


def _sent(ts, asset="XAUUSD", traders=1):
    return SentimentSnapshot(
        ts=ts,
        asset=asset,
        asset_display=asset + "/USD",
        long_pct_by_trader=60.0,
        short_pct_by_trader=40.0,
        traders=traders,
        lots=1.0,
        floating_pl_usd=-100.0,
    )


def test_pk_prevents_duplicate_rows(store):
    ts = datetime(2026, 8, 6, 12, 0)
    store.upsert_sentiment_snapshots([_sent(ts)])
    store.upsert_sentiment_snapshots([_sent(ts)])
    assert store.count_rows("sentiment_snapshots") == 1, "same (ts, asset) must not duplicate"


def test_upsert_overwrites_existing_row(store):
    ts = datetime(2026, 8, 6, 12, 0)
    store.upsert_sentiment_snapshots([_sent(ts, traders=1)])
    store.upsert_sentiment_snapshots([_sent(ts, traders=7)])
    rows = store._conn.execute("SELECT traders FROM sentiment_snapshots WHERE asset='XAUUSD'").fetchall()
    assert rows == [(7,)], "ON CONFLICT DO UPDATE must overwrite traders"


def test_failing_batch_rolls_back_atomically(store):
    """One bad row => the whole batch must be absent (no partial write)."""
    ts = datetime(2026, 8, 6, 12, 0)
    good = _sent(ts, asset="EURUSD")
    bad = _sent(None, asset="GBPUSD")  # ts=None violates NOT NULL -> mid-batch error
    with pytest.raises(duckdb.Error):
        store.upsert_sentiment_snapshots([good, bad])
    assert store.count_rows("sentiment_snapshots") == 0, "rollback must hide partial writes"


def test_transaction_context_rolls_back_on_error(store):
    ts = datetime(2026, 8, 6, 12, 0)
    with pytest.raises(RuntimeError), store.transaction():
        store._conn.execute(
            "INSERT INTO sentiment_snapshots (ts, asset, traders) VALUES (?,?,?)",
            [ts, "XAUUSD", 5],
        )
        raise RuntimeError("boom")
    assert store.count_rows("sentiment_snapshots") == 0, "no commit after exception"


def test_transaction_context_commits_on_success(store):
    ts = datetime(2026, 8, 6, 12, 0)
    with store.transaction():
        store._conn.execute(
            "INSERT INTO sentiment_snapshots (ts, asset, traders) VALUES (?,?,?)",
            [ts, "XAUUSD", 5],
        )
    assert store.count_rows("sentiment_snapshots") == 1


def test_safe_ident_rejects_injection(store):
    with pytest.raises(ValueError):
        store._safe_ident("sentiment_snapshots; DROP TABLE sentiment_snapshots")
    with pytest.raises(ValueError):
        store._safe_ident("profile_snapshots --")


def test_trades_pk_dedupes_by_seq(store):
    ts = datetime(2026, 8, 6, 12, 0)
    t = TradeRecord(
        account_uuid="u1",
        ts=ts,
        seq=0,
        ticket=100,
        symbol="XAUUSDm",
        side="buy",
        lots=0.01,
        pnl_usd=1.0,
        close_time="2026-08-06",
    )
    store.upsert_profile_trades([t])
    store.upsert_profile_trades([t])
    assert store.count_rows("profile_trades") == 1


def test_profile_pk_keyed_on_uuid_and_ts(store):
    ts = datetime(2026, 8, 6, 12, 0)
    a = ProfileSnapshot(account_uuid="u1", ts=ts, account_name="A")
    b = ProfileSnapshot(account_uuid="u2", ts=ts, account_name="B")
    c = ProfileSnapshot(account_uuid="u1", ts=datetime(2026, 8, 7, 12, 0), account_name="C")
    store.upsert_profile_snapshots([a, b, c])
    assert store.count_rows("profile_snapshots") == 3
