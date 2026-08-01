"""
Myfxbook Gateway - READ-ONLY client for the official Myfxbook REST API.

This module wraps the Myfxbook API (https://www.myfxbook.com/api, v1.38) for
reading account analytics, open trades, and history. It does NOT trade and
does NOT send orders. It mirrors the read-only philosophy of ``mt5_gateway``.

Credentials are read from the environment (``MYFXBOOK_EMAIL`` /
``MYFXBOOK_PASSWORD``) and never logged. The session returned by ``/login``
is IP-bound and has a 1-month TTL (per Myfxbook API changelog 2025-10-19), so
it is cached in memory and refreshed when missing or stale.

Stdlib only: ``urllib.request`` for HTTP, ``xml.etree.ElementTree`` for parsing.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.myfxbook.com/api/"
_SESSION_TTL_SECONDS = 25 * 24 * 3600  # 25 days; API TTL is 30 days (be conservative)
_REQUEST_TIMEOUT = 30


class MyfxbookError(Exception):
    """Raised on any Myfxbook API or transport failure."""


class MyfxbookParseError(MyfxbookError):
    """Raised when the API returns a non-XML / unparseable response."""


def _mask(value: str, visible: int = 3) -> str:
    """Mask all but the first ``visible`` chars of a secret for logging."""
    if not value:
        return ""
    return value[:visible] + "*" * max(0, len(value) - visible)


class MyfxbookGateway:
    """Read-only client for the Myfxbook REST API."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        timeout: int = _REQUEST_TIMEOUT,
    ) -> None:
        # Credentials come from params or environment; never hard-coded.
        self._email = email if email is not None else os.getenv("MYFXBOOK_EMAIL", "")
        self._password = password if password is not None else os.getenv("MYFXBOOK_PASSWORD", "")
        self._timeout = timeout
        self._session: str | None = None
        self._session_ts: float = 0.0

    # ------------------------------------------------------------------
    # Auth lifecycle
    # ------------------------------------------------------------------

    def login(self) -> str:
        """Authenticate and return a cached session token.

        Re-uses a cached session unless it is missing or older than the TTL.
        """
        if self._session and (time.time() - self._session_ts) < _SESSION_TTL_SECONDS:
            return self._session
        if not self._email or not self._password:
            raise MyfxbookError("Myfxbook credentials missing. Set MYFXBOOK_EMAIL and MYFXBOOK_PASSWORD.")
        logger.info("Myfxbook login as %s", _mask(self._email, 3))
        data = self._request("login", {"email": self._email, "password": self._password})
        # The <session> element parses to a bare string; tolerate either shape.
        session = data.get("session") if isinstance(data, dict) else data
        if not session:
            raise MyfxbookError("Myfxbook login returned no session")
        self._session = session
        self._session_ts = time.time()
        return session

    def logout(self) -> None:
        """Invalidate the current session (best-effort)."""
        if not self._session:
            return
        try:
            self._request("logout", {"session": self._session})
        except MyfxbookError as exc:
            logger.warning("Myfxbook logout failed (ignored): %s", exc)
        finally:
            self._session = None
            self._session_ts = 0.0

    def _ensure_session(self) -> str:
        return self._session or self.login()

    # ------------------------------------------------------------------
    # Data methods (read-only)
    # ------------------------------------------------------------------

    def get_my_accounts(self) -> list[dict]:
        """Return the list of linked accounts and their analytics."""
        data = self._request("get-my-accounts", {"session": self._ensure_session()})
        return self._as_list(self._inner(data, "account"))

    def get_watched_accounts(self) -> list[dict]:
        data = self._request("get-watched-accounts", {"session": self._ensure_session()})
        return self._as_list(self._inner(data, "account"))

    def get_open_trades(self, account_id: int | str) -> list[dict]:
        data = self._request(
            "get-open-trades",
            {"session": self._ensure_session(), "id": account_id},
        )
        return self._as_list(self._inner(data, "trade"))

    def get_open_orders(self, account_id: int | str) -> list[dict]:
        data = self._request(
            "get-open-orders",
            {"session": self._ensure_session(), "id": account_id},
        )
        return self._as_list(self._inner(data, "order"))

    def get_history(
        self,
        account_id: int | str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Return trade history (Myfxbook limits this to the last 50)."""
        params = {"session": self._ensure_session(), "id": account_id}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        data = self._request("get-history", params)
        return self._as_list(self._inner(data, "trade"))

    def get_daily_gain(self, account_id: int | str) -> list[dict]:
        data = self._request(
            "get-daily-gain",
            {"session": self._ensure_session(), "id": account_id},
        )
        return self._as_list(self._inner(data, "day"))

    def get_data_daily(self, account_id: int | str) -> dict:
        data = self._request(
            "get-data-daily",
            {"session": self._ensure_session(), "id": account_id},
        )
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # HTTP + XML plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _inner(data, tag: str):
        """Extract the list under ``tag`` from a parsed payload dict."""
        if not isinstance(data, dict):
            return []
        return data.get(tag, [])

    @staticmethod
    def _as_list(value) -> list:
        """Normalize a single dict or list into a list."""
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _request(self, method: str, params: dict) -> dict:
        """Call an API method, retrying the ``.xml`` suffix if parsing fails."""
        last_err: Exception | None = None
        for suffix in (".xml", ""):
            url = self._build_url(f"{method}{suffix}", params)
            try:
                return self._http_get(url)
            except MyfxbookParseError as exc:
                # Wrong endpoint name (e.g. missing .xml) -> try the other form.
                last_err = exc
                logger.debug("Myfxbook %s%s parse failed, retrying: %s", method, suffix, exc)
                continue
        assert last_err is not None
        raise last_err

    def _build_url(self, path: str, params: dict) -> str:
        # The session token Myfxbook returns is ALREADY URL-encoded (it contains
        # sequences like %2F). Quoting it again double-encodes those and the API
        # rejects the session. Pass it verbatim; quote every other param normally.
        parts = []
        for k, v in params.items():
            if k == "session":
                parts.append(f"{k}={v}")
            else:
                parts.append(f"{k}={urllib.parse.quote(str(v))}")
        query = "&".join(parts)
        return f"{_BASE_URL}{path}?{query}"

    def _http_get(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # network / timeout / HTTP error
            raise MyfxbookError(f"Myfxbook HTTP request failed: {exc}") from exc
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> dict:
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise MyfxbookParseError(f"Invalid XML from Myfxbook: {exc}") from exc

        if root.tag != "response":
            raise MyfxbookParseError(f"Unexpected root element: {root.tag}")

        error_attr = (root.get("error") or "false").lower()
        message = root.get("message", "") or ""
        if error_attr == "true":
            raise MyfxbookError(f"Myfxbook API error: {message}")

        children = list(root)
        if not children:
            return {}
        return _xml_to_obj(children[0])


def _xml_to_obj(el: ElementTree.Element):
    """Recursively convert an ElementTree element into dict / list / str.

    Repeated child tags become a list; leaf elements become their text.
    Empty elements (no text, no children) become ``{}`` so downstream
    ``.get()`` access is always safe.
    """
    children = list(el)
    if not children:
        text = (el.text or "").strip()
        return text if text else {}

    grouped: dict[str, object] = {}
    for child in children:
        value = _xml_to_obj(child)
        if child.tag in grouped:
            existing = grouped[child.tag]
            if not isinstance(existing, list):
                grouped[child.tag] = [existing]
            grouped[child.tag].append(value)  # type: ignore[attr-defined]
        else:
            grouped[child.tag] = value
    return grouped
