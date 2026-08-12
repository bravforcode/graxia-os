"""Tests for EURUSD event calendar."""
from graxia.packages.quant_os.markets.eurusd.event_calendar import EURUSDEventCalendar


def test_calendar_creates():
    cal = EURUSDEventCalendar()
    assert len(cal.get_events()) > 0


def test_calendar_high_impact():
    cal = EURUSDEventCalendar()
    high = cal.get_high_impact()
    assert len(high) >= 6
    names = {e.event_name for e in high}
    assert "NFP" in names
    assert "FOMC" in names
    assert "ECB_RATE" in names


def test_calendar_by_currency():
    cal = EURUSDEventCalendar()
    usd = cal.get_by_currency("USD")
    eur = cal.get_by_currency("EUR")
    assert len(usd) > 0
    assert len(eur) > 0
