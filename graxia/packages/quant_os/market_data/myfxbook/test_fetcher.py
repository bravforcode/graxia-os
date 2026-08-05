"""Fetcher tests — httpx.MockTransport keeps them offline."""

import httpx
import pytest

from market_data.myfxbook import fetcher


def test_fetch_account_page_returns_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/members/Tanon58/sniperfpg/12096204"
        return httpx.Response(200, text="<html><b>Gain :</b><b>+201.89%</b></html>")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    html = fetcher.fetch_account_page(client, "https://www.myfxbook.com/members/Tanon58/sniperfpg/12096204")
    assert "Gain" in html


def test_fetch_retries_on_500_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, text="oops")
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    html = fetcher.fetch_account_page(client, "https://www.myfxbook.com/x")
    assert html == "ok"
    assert calls["n"] == 3


def test_fetch_raises_fetch_error_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(fetcher.FetchError):
        fetcher.fetch_account_page(client, "https://www.myfxbook.com/x")


def test_sleep_between_requests_respects_zero() -> None:
    fetcher.sleep_between_requests(delay=0.0)  # must not raise / sleep noticeably
