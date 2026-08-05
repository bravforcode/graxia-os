"""Report renderer tests."""

from market_data.myfxbook import report


def test_render_markdown_header_and_summary() -> None:
    results = [
        {
            "account_id": 12096204,
            "system": "sniperfpg",
            "member": "Tanon58",
            "gain_pct": 201.89,
            "max_drawdown_pct": 52.02,
            "monthly_pct": 86.24,
            "filter_pass": False,
            "filter_reasons": ["drawdown too high (52.0% > 25.0%)"],
            "martingale_risky": True,
            "martingale_signals": ["tail drawdown 52.0% >= 30%"],
            "error": None,
        }
    ]
    md = report.render_markdown(results, "2026-08-04")
    assert "# Myfxbook Collection — 2026-08-04" in md
    assert "1 accounts, 0 passed filter, 1 martingale-risk" in md
    assert "- FAIL sniperfpg (12096204)" in md
    assert "drawdown too high" in md


def test_render_error_account() -> None:
    results = [
        {
            "account_id": 8072229,
            "system": "pamm-rt",
            "member": "Tanon58",
            "gain_pct": None,
            "max_drawdown_pct": None,
            "monthly_pct": None,
            "filter_pass": False,
            "filter_reasons": [],
            "martingale_risky": False,
            "martingale_signals": [],
            "error": "FetchError: failed to fetch https://x",
        }
    ]
    md = report.render_markdown(results, "2026-08-04")
    assert "- ERROR pamm-rt (8072229)" in md
