"""Store tests against a tmp_path SQLite file."""

from market_data.myfxbook import store
from market_data.myfxbook.models import AccountSummary, EquityPoint


def test_upsert_and_read_account(tmp_path) -> None:
    conn = store.connect(str(tmp_path / "test.db"))
    store.init_schema(conn)
    summary = AccountSummary(
        account_id=12096204,
        member="Tanon58",
        system="sniperfpg",
        url="u",
        gain_pct=201.89,
        max_drawdown_pct=52.02,
        last_updated="2026-08-04",
    )
    store.upsert_account(conn, summary)
    row = store.get_account(conn, 12096204)
    assert row is not None
    assert row["gain_pct"] == 201.89
    assert row["max_drawdown_pct"] == 52.02


def test_upsert_is_idempotent(tmp_path) -> None:
    conn = store.connect(str(tmp_path / "test.db"))
    store.init_schema(conn)
    store.upsert_account(conn, AccountSummary(account_id=1, member="m", system="s", url="u", gain_pct=10.0))
    store.upsert_account(conn, AccountSummary(account_id=1, member="m", system="s", url="u", gain_pct=20.0))
    rows = store.list_accounts(conn)
    assert len(rows) == 1
    assert rows[0]["gain_pct"] == 20.0


def test_insert_equity_points(tmp_path) -> None:
    conn = store.connect(str(tmp_path / "test.db"))
    store.init_schema(conn)
    points = [
        EquityPoint(account_id=1, month="2026-01", equity=100.0),
        EquityPoint(account_id=1, month="2026-02", equity=110.0),
    ]
    assert store.insert_equity_points(conn, points) == 2
    cur = conn.execute("SELECT COUNT(*) FROM equity_points WHERE account_id = 1")
    assert cur.fetchone()[0] == 2


def test_meta_schema_version(tmp_path) -> None:
    conn = store.connect(str(tmp_path / "test.db"))
    store.init_schema(conn)
    cur = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    assert cur.fetchone()[0] == str(store.SCHEMA_VERSION)
