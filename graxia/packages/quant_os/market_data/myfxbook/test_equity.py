"""Equity curve parser tests."""

from market_data.myfxbook import equity

TABLE_HTML = """
<html><body>
<table>
<tr><th>Month</th><th>Equity</th></tr>
<tr><td>2026-01</td><td>2,000.00</td></tr>
<tr><td>2026-02</td><td>2,500.00</td></tr>
<tr><td>2026-03</td><td>1,800.00</td></tr>
</table>
</body></html>
"""


def test_parses_monthly_table() -> None:
    points = equity.parse_monthly_equity_points(TABLE_HTML, account_id=42)
    assert len(points) == 3
    assert points[0].account_id == 42
    assert points[0].month == "2026-01"
    assert points[0].equity == 2000.0
    assert points[2].equity == 1800.0


def test_empty_when_no_table() -> None:
    assert equity.parse_monthly_equity_points("<html><body>nope</body></html>", 1) == []


def test_ignores_dates_outside_table() -> None:
    # meta dates and JS strings must never become EquityPoints
    html = (
        '<meta content="2026-08-04"><script>var d = "2026-07-01";</script>'
        "<table><tr><td>2026-01</td><td>2,000.00</td></tr></table>"
    )
    points = equity.parse_monthly_equity_points(html, 1)
    assert len(points) == 1
    assert points[0].month == "2026-01"
    assert points[0].equity == 2000.0


def test_parses_widget_json() -> None:
    payload = '{"data": [{"month": "2026-07", "equity": 7128.01}, {"month": "2026-08", "equity": 8000.0}]}'
    points = equity.parse_widget_equity_json(payload, account_id=7)
    assert len(points) == 2
    assert points[1].month == "2026-08"
    assert points[1].equity == 8000.0


def test_widget_json_malformed_returns_empty() -> None:
    assert equity.parse_widget_equity_json("not json", 1) == []
