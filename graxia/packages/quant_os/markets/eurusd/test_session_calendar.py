"""Tests for EURUSD session calendar."""
from graxia.packages.quant_os.markets.eurusd.session_calendar import EURUSDSessionCalendar


def test_calendar_creates():
    cal = EURUSDSessionCalendar()
    assert len(cal.get_sessions()) == 4


def test_calendar_london_open():
    cal = EURUSDSessionCalendar()
    assert cal.is_session_open(10)  # 10:00 UTC = London


def test_calendar_asian_open():
    cal = EURUSDSessionCalendar()
    assert cal.is_session_open(3)  # 03:00 UTC = Asian


def test_calendar_no_session():
    cal = EURUSDSessionCalendar()
    assert not cal.is_session_open(22)  # 22:00 UTC = no session


def test_calendar_overlap():
    cal = EURUSDSessionCalendar()
    active = cal.get_active_sessions(14)  # 14:00 UTC = overlap
    names = [s.name for s in active]
    assert "london" in names
    assert "new_york" in names
    assert "overlap_london_ny" in names
