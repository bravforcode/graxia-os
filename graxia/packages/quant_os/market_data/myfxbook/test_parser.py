"""Parser tests — synthetic HTML mirroring the real Myfxbook template plus the real fixture."""

from pathlib import Path

import pytest

from market_data.myfxbook import parser

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "sniperfpg_12096204.html"

STATS_HTML = """
<html><body>
<p><b>Gain :</b></p><p><b>+201.89%</b></p>
<p><b>Abs. Gain:</b></p><p><b>+191.67%</b></p>
<p>Daily</p><p>2.11%</p>
<p>Monthly:</p><p>86.24%</p>
<p>Drawdown:</p><p>52.02%</p>
<p>Balance:</p><p>USC7,128.01</p>
</body></html>
"""

URL = "https://www.myfxbook.com/members/Tanon58/sniperfpg/12096204"


def test_parses_real_fixture_gain_and_drawdown() -> None:
    html = REAL_FIXTURE.read_text(encoding="utf-8", errors="replace")
    summary = parser.parse_account_summary(html, account_id=12096204, member="Tanon58", system="sniperfpg", url=URL)
    assert summary.account_id == 12096204
    assert summary.gain_pct is not None
    assert summary.gain_pct == pytest.approx(201.89, abs=0.05)
    assert summary.max_drawdown_pct is not None
    assert summary.max_drawdown_pct == pytest.approx(52.02, abs=0.05)
    assert summary.balance is not None
    assert summary.balance > 0


def test_parses_synthetic_stats_block() -> None:
    summary = parser.parse_account_summary(STATS_HTML, account_id=1, member="m", system="s", url="u")
    assert summary.gain_pct == 201.89
    assert summary.abs_gain_pct == 191.67
    assert summary.daily_pct == 2.11
    assert summary.monthly_pct == 86.24
    assert summary.max_drawdown_pct == 52.02
    assert summary.balance == 7128.01


def test_missing_values_become_none() -> None:
    summary = parser.parse_account_summary(
        "<html><body>no stats here</body></html>", account_id=1, member="m", system="s", url="u"
    )
    assert summary.gain_pct is None
    assert summary.profit_factor is None
    assert summary.total_trades is None


def test_strip_tags_flattens_markup() -> None:
    assert parser._strip_tags("<p><b>Gain :</b></p><p><b>+1.5%</b></p>") == "\n\nGain :\n\n\n\n+1.5%\n\n"


def test_gain_does_not_match_abs_gain() -> None:
    # 'Abs. Gain' appears BEFORE 'Gain' — the line anchor must keep them apart.
    # (\b would NOT: a space before 'Gain' is still a word boundary.)
    html = "<p><b>Abs. Gain:</b></p><p><b>+191.67%</b></p>" "<p><b>Gain :</b></p><p><b>+201.89%</b></p>"
    summary = parser.parse_account_summary(html, account_id=1, member="m", system="s", url="u")
    assert summary.gain_pct == 201.89
    assert summary.abs_gain_pct == 191.67


def test_script_content_ignored() -> None:
    html = "<html><script>var gain = 999.99; var x = 88;</script>" "<p><b>Gain :</b></p><p><b>+1.50%</b></p></html>"
    summary = parser.parse_account_summary(html, account_id=1, member="m", system="s", url="u")
    assert summary.gain_pct == 1.50
