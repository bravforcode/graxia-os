"""Tests for myfxbook models — frozen dataclasses with None defaults."""

from dataclasses import FrozenInstanceError

import pytest

from market_data.myfxbook.models import AccountSummary, EquityPoint, TradeRecord


def test_account_summary_defaults_are_none() -> None:
    summary = AccountSummary(account_id=12096204, member="Tanon58", system="sniperfpg", url="https://x")
    assert summary.account_id == 12096204
    assert summary.member == "Tanon58"
    assert summary.gain_pct is None
    assert summary.verified is None
    assert summary.last_updated == ""


def test_account_summary_is_frozen() -> None:
    summary = AccountSummary(account_id=1, member="m", system="s", url="u")
    with pytest.raises(FrozenInstanceError):
        summary.gain_pct = 1.0  # type: ignore[misc]


def test_equity_point_holds_month_and_value() -> None:
    point = EquityPoint(account_id=1, month="2026-07", equity=7128.01)
    assert point.month == "2026-07"
    assert point.equity == pytest.approx(7128.01)


def test_trade_record_fields() -> None:
    trade = TradeRecord(
        account_id=1,
        trade_id="t1",
        open_time="2026-07-01 10:00",
        close_time="2026-07-01 14:00",
        symbol="XAUUSD",
        direction="long",
        lots=0.1,
        entry=2300.0,
        exit=2310.0,
        pnl=10.0,
    )
    assert trade.symbol == "XAUUSD"
    assert trade.direction == "long"
