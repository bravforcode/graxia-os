"""Fetcher tests (offline via httpx.MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from market_data.thaifxbook import config
from market_data.thaifxbook.fetcher import FetchError, fetch_page


def _client_with(responses, status=200, url="https://thaifxbook.com/tools/outlook"):
    def handler(request):
        if responses:
            if callable(responses[0]):
                return responses.pop(0)(request)
            return httpx.Response(status, text=responses.pop(0), request=request)
        return httpx.Response(404, text="not found", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler)), url


def test_fetch_ok():
    client, url = _client_with(["<html>data</html>"])
    assert fetch_page(client, url) == "<html>data</html>"


def test_fetch_retries_then_raises():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(500, text="err", request=request)

    client, url = _client_with([flaky, flaky, flaky, flaky])
    with pytest.raises(FetchError):
        fetch_page(client, url)
    assert calls["n"] >= 3, "tenacity must retry transient 500s"


def test_fetch_redirect_to_auth_raises():
    def redirect(request):
        return httpx.Response(302, headers={"location": "/sign-in"}, request=request)

    client, url = _client_with([redirect])
    with pytest.raises(FetchError):
        fetch_page(client, url)


def test_config_urls():
    assert config.OUTLOOK_URL == "https://thaifxbook.com/tools/outlook"
    assert config.PROFILE_URL.format(uuid="abc") == "https://thaifxbook.com/p/abc"
