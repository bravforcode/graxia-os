"""HTTP fetch layer for Thaifxbook public pages.

Mirrors the myfxbook collector's fetcher: httpx client with a browser UA,
tenacity retry on transient failures, and a polite throttle. The pages are
Next.js RSC payloads served without Cloudflare on the public surface
(verified 2026-08-06: /p/ and /tools/outlook fetch directly).
"""

from __future__ import annotations

import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from . import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"


class FetchError(RuntimeError):
    """Raised when a Thaifxbook page cannot be fetched after retries."""


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": UA, "Accept-Language": "th-TH,th;q=0.9"},
        follow_redirects=True,
        timeout=config.TIMEOUT_SECONDS,
    )


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0),  # tests must stay fast; prod delay comes from throttle
    reraise=True,
)
def _get(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp


def fetch_page(client: httpx.Client, url: str) -> str:
    """Fetch a public Thaifxbook page and return its HTML.

    Raises FetchError if the page is not fetchable (e.g. login redirect).
    """
    try:
        resp = _get(client, url)
    except Exception as exc:  # noqa: BLE001 - wrap any retry exhaustion
        raise FetchError(f"fetch failed for {url}: {exc}") from exc
    if resp.url.path.rstrip("/").endswith(("/sign-in", "/sign-up")):
        raise FetchError(f"page {url} redirected to auth (login required)")
    return resp.text


def sleep_between_requests() -> None:
    time.sleep(config.REQUEST_DELAY_SECONDS)
