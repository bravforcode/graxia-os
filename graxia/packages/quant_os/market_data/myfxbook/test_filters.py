"""Quality filter tests — SniperFPG's real numbers anchor the reject path."""

from market_data.myfxbook import filters
from market_data.myfxbook.models import AccountSummary

GOOD = AccountSummary(
    account_id=1,
    member="m",
    system="s",
    url="u",
    verified=True,
    tracked_months=24,
    max_drawdown_pct=18.0,
    profit_factor=2.1,
    total_trades=1200,
)

SNIPER_FPG = AccountSummary(
    account_id=12096204,
    member="Tanon58",
    system="sniperfpg",
    url="u",
    verified=True,
    tracked_months=6,
    max_drawdown_pct=52.02,
    profit_factor=None,
    total_trades=400,
)


def test_good_account_passes() -> None:
    verdict = filters.evaluate_quality(GOOD)
    assert verdict.passed is True
    assert verdict.reasons == []


def test_sniper_fpg_rejected_on_drawdown_and_history() -> None:
    verdict = filters.evaluate_quality(SNIPER_FPG)
    assert verdict.passed is False
    text = " ".join(verdict.reasons).lower()
    assert "drawdown" in text
    assert "history" in text


def test_missing_metrics_fail_with_reasons() -> None:
    summary = AccountSummary(account_id=2, member="m", system="s", url="u", verified=True)
    verdict = filters.evaluate_quality(summary)
    assert verdict.passed is False
    assert len(verdict.reasons) >= 3


def test_unverified_fails() -> None:
    summary = AccountSummary(account_id=3, member="m", system="s", url="u", verified=False, tracked_months=24)
    verdict = filters.evaluate_quality(summary)
    assert verdict.passed is False
    assert "unverified" in " ".join(verdict.reasons)


def test_custom_thresholds() -> None:
    strict = filters.QualityThresholds(min_tracked_months=36, max_drawdown_pct=15.0)
    verdict = filters.evaluate_quality(GOOD, thresholds=strict)
    assert verdict.passed is False
