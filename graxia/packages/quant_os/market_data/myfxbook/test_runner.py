"""Runner tests — collect_one is exercised offline against the real fixture."""

import sqlite3
from pathlib import Path

from market_data.myfxbook import runner_impl

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "sniperfpg_12096204.html"
SNIPER = ("Tanon58", "sniperfpg", 12096204)


def test_collect_one_parses_and_filters_sniperfpg(tmp_path) -> None:
    html = REAL_FIXTURE.read_text(encoding="utf-8", errors="replace")
    result = runner_impl.collect_one(html, SNIPER, db_path=None)
    assert result["account_id"] == 12096204
    assert result["error"] is None
    assert result["gain_pct"] is not None
    assert result["filter_pass"] is False
    assert any("drawdown" in r.lower() for r in result["filter_reasons"])


def test_collect_one_persists_to_db(tmp_path) -> None:
    html = REAL_FIXTURE.read_text(encoding="utf-8", errors="replace")
    db_path = str(tmp_path / "myfxbook.db")
    runner_impl.prepare_db(db_path)  # schema created once, before the account loop
    result = runner_impl.collect_one(html, SNIPER, db_path=db_path)
    assert result["error"] is None
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT gain_pct FROM accounts WHERE account_id = 12096204").fetchone()
    assert row is not None and row[0] is not None


def test_collect_one_error_recorded_on_bad_html() -> None:
    result = runner_impl.collect_one("<html>garbage</html>", SNIPER, db_path=None)
    assert result["error"] is not None
    assert result["account_id"] == 12096204
