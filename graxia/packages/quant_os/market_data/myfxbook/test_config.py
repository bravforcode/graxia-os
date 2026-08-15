"""Config sanity tests — catches typos in URLs/IDs early."""

from market_data.myfxbook import config


def test_pilot_accounts_are_complete() -> None:
    assert len(config.PILOT_ACCOUNTS) == 8
    ids = [acc[2] for acc in config.PILOT_ACCOUNTS]
    assert len(set(ids)) == 8  # no duplicates


def test_sniperfpg_is_first_pilot() -> None:
    member, system, account_id = config.PILOT_ACCOUNTS[0]
    assert member == "Tanon58"
    assert system == "sniperfpg"
    assert account_id == 12096204


def test_account_url_format() -> None:
    url = config.account_url("Tanon58", "sniperfpg", 12096204)
    assert url == "https://www.myfxbook.com/members/Tanon58/sniperfpg/12096204"


def test_rate_limit_is_respectful() -> None:
    assert config.REQUEST_DELAY_SECONDS >= 5.0
