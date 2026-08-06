"""Model invariants: missing != zero."""

from __future__ import annotations

from datetime import datetime

from market_data.thaifxbook.models import ProfileSnapshot, SentimentSnapshot, TradeRecord


def test_sentiment_defaults_none():
    s = SentimentSnapshot(ts=datetime(2026, 8, 6), asset="XAUUSD")
    assert s.long_pct_by_trader is None
    assert s.traders is None
    assert s.floating_pl_usd is None


def test_profile_masked_money_is_none_not_zero():
    p = ProfileSnapshot(account_uuid="u1", ts=datetime(2026, 8, 6), masked=True)
    assert p.balance_usd is None
    assert p.profit_usd is None
    assert p.gain_pct is None


def test_trade_required_fields():
    t = TradeRecord(
        account_uuid="u1",
        ts=datetime(2026, 8, 6),
        seq=0,
        ticket=1,
        symbol="XAUUSDm",
        side="buy",
        lots=0.01,
        pnl_usd=1.0,
        close_time="d",
    )
    assert t.open_price is None  # optional detail
    assert t.comment is None
