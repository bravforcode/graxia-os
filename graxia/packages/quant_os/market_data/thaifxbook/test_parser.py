"""Parser tests against real saved Thaifxbook fixtures (2026-08-06)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from market_data.thaifxbook.parser import (
    parse_money,
    parse_outlook,
    parse_profile,
    parse_trades,
)

FIXTURES = Path(__file__).parent / "fixtures"
TS = datetime(2026, 8, 6, 12, 0)


@pytest.fixture(scope="module")
def outlook_html():
    return (FIXTURES / "outlook_20260806.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def profile_html():
    return (FIXTURES / "profile_putdejudom_20260806.html").read_text(encoding="utf-8")


# -- money ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,132.92", 1132.92),
        ("$$40.52", 40.52),  # platform double-$ quirk
        ("-$1.1M", -1_100_000.0),
        ("+$292", 292.0),
        ("-$20.9K", -20_900.0),
        ("¢93,792.61", 937.9261),  # cent account -> USD
        ("+$0", 0.0),
        ("***", None),  # masked
        ("—", None),
        ("", None),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


# -- outlook ----------------------------------------------------------------


def test_outlook_row_count_and_headers(outlook_html):
    rows = parse_outlook(outlook_html, TS)
    assert len(rows) >= 22, "linked rows (>=3 traders) expected"
    assert rows[0].asset == "XAUUSD"


def test_outlook_xau_values(outlook_html):
    rows = parse_outlook(outlook_html, TS)
    xau = next(r for r in rows if r.asset == "XAUUSD")
    assert xau.long_pct_by_trader == 61.0
    assert xau.short_pct_by_trader == 39.0
    assert xau.traders == 161
    assert xau.lots == 373.26
    assert xau.floating_pl_usd == -1_100_000.0  # -$1.1M


def test_outlook_timestamps_set(outlook_html):
    rows = parse_outlook(outlook_html, TS)
    assert all(r.ts == TS for r in rows)


# -- profile ----------------------------------------------------------------


def test_profile_identity(profile_html):
    p = parse_profile(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    assert p.trader == "Put Dejudom"
    assert p.account_name == "PutDejudomTraderUltimateHeadShot1"
    assert p.broker == "Exness"
    assert p.verified is True


def test_profile_economics_match_platform(profile_html):
    p = parse_profile(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    # exact matches to platform-displayed values (validated in Phase 0)
    assert p.balance_usd == pytest.approx(1431.05)
    assert p.equity_usd == pytest.approx(1431.05)
    assert p.deposits_usd == pytest.approx(298.13)
    assert p.withdrawals_usd == pytest.approx(0.0)
    assert p.profit_usd == pytest.approx(1132.92)
    assert p.gain_pct == pytest.approx(380.01)
    assert p.abs_gain_pct == pytest.approx(380.01)
    assert p.daily_pct == pytest.approx(35.85)
    assert p.monthly_pct == pytest.approx(380.01)
    assert p.max_drawdown_pct == pytest.approx(0.11)


def test_profile_metrics_match_platform(profile_html):
    p = parse_profile(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    assert p.profit_factor == pytest.approx(709.07)
    assert p.sharpe == pytest.approx(1.64)
    assert p.win_rate_pct == pytest.approx(96.55)
    assert p.total_trades == 29
    assert p.ea_pct == pytest.approx(41.379, abs=0.01)
    assert p.manual_pct == pytest.approx(58.621, abs=0.01)
    assert p.ai_accuracy == pytest.approx(9.7)
    assert p.ai_profitability == pytest.approx(10.0)
    assert p.ai_risk == pytest.approx(10.0)
    assert p.ai_consistency == pytest.approx(5.5)
    assert p.ai_recovery == pytest.approx(10.0)
    assert p.masked is False


# -- trades -----------------------------------------------------------------


def test_trades_count_and_sum(profile_html):
    trades = parse_trades(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    assert len(trades) == 29
    assert sum(t.pnl_usd for t in trades) == pytest.approx(1132.92)


def test_trades_deduped_by_ticket(profile_html):
    trades = parse_trades(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    tickets = [t.ticket for t in trades]
    assert len(tickets) == len(set(tickets)), "58 payload objects must dedupe to 29"


def test_trade_detail_fields(profile_html):
    trades = parse_trades(profile_html, "ff65308c-aeda-4cc9-ac85-ce469e98dbaa", TS)
    t = trades[0]
    assert t.symbol == "XAUUSDm"
    assert t.side == "buy"
    assert t.lots == pytest.approx(0.01)
    assert t.pnl_usd == pytest.approx(0.82)
    assert t.open_price is not None
    assert t.close_price is not None
    assert t.pips is not None
