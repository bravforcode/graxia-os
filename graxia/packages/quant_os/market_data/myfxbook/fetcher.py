"""HTTP layer for Myfxbook public pages. Offline-testable via httpx.MockTransport."""

import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from market_data.myfxbook import config


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched after all retries."""


# myfxbook.com rejects default httpx/python UA with 403; use a browser-like UA.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPError):
        return True
    if isinstance(exc, httpx.Response):
        return exc.status_code >= 500
    response = getattr(exc, "response", None)
    return bool(response is not None and getattr(response, "status_code", 0) >= 500)


def make_client(*, timeout: float | None = None) -> httpx.Client:
    """Build an httpx client with sane defaults for public page fetching."""
    return httpx.Client(
        follow_redirects=True,
        timeout=timeout or config.TIMEOUT_SECONDS,
        headers=DEFAULT_HEADERS,
    )


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception(_is_retryable))
def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()  # 4xx/5xx become exceptions INSIDE the retried call
    return response


def fetch_account_page(client: httpx.Client, account_url: str) -> str:
    """Fetch a Myfxbook account page. Returns decoded HTML text or raises FetchError."""
    try:
        return _get(client, account_url).text
    except Exception as exc:
        raise FetchError(f"failed to fetch {account_url}: {exc}") from exc


def sleep_between_requests(delay: float | None = None) -> None:
    """Polite throttle between page requests. Pass delay=0.0 in tests."""
    time.sleep(delay if delay is not None else config.REQUEST_DELAY_SECONDS)
