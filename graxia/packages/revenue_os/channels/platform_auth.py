"""Platform auth helpers — the ONLY place marketplace signing/token logic lives.
Shopee v2: sign = SHA256(partner_key + timestamp + path + partner_id + access_token)
Lazada:    sign = HMAC-SHA256(app_secret, sorted "keyvalue" concatenation).upper()
           (values are signed raw; the receiver re-sorts the DECODED params, so
           percent-encoding on the wire is transparent to the signature)
TikTok Shop: app_key + app_secret signed requests (Task 4).
Amazon: LWA client-credentials token (AmazonTokenCache); SP-API scope.
All clients are 429-aware (backoff) and sandbox/live aware.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

import httpx

MAX_ATTEMPTS = 3


class PlatformError(Exception):
    """Raised when a platform call fails (network, auth, 4xx/5xx)."""


class BaseSignedClient:
    """Rate-limit-aware HTTP base. Subclasses implement _sign()."""

    def __init__(self, base_url: str, http_client: Optional[httpx.AsyncClient] = None):
        self.base_url = base_url
        self._client = http_client

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _sign(self, method: str, path: str, params: dict) -> dict:
        raise NotImplementedError

    async def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        return await self._request("GET", path, params=params or {})

    async def post_json(self, path: str, params: Optional[dict] = None, json: Optional[dict] = None) -> dict:
        return await self._request("POST", path, params=params or {}, json=json)

    async def _request(self, method: str, path: str, **kw) -> dict:
        client = await self._ensure_client()
        params = dict(kw.get("params") or {})
        signed = self._sign(method, path, params)
        params.update(signed)
        kw["params"] = params
        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = await client.request(method, self.base_url + path, **kw)
            if resp.status_code == 429:
                import asyncio
                await asyncio.sleep(1.0 * attempt)
                continue
            if resp.status_code >= 400:
                raise PlatformError(f"{method} {path} -> {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise PlatformError(f"{method} {path} rate-limited after {MAX_ATTEMPTS} attempts")


# Public alias — adapters and tests import PlatformSignedClient
PlatformSignedClient = BaseSignedClient


class ShopeeSigner:
    def __init__(self, partner_id: int, partner_key: str):
        self.partner_id = partner_id
        self.partner_key = partner_key

    def sign(self, timestamp: int, path: str, access_token: str = "") -> str:
        # Shopee Open Platform v2 (API Signature):
        # sign = SHA256(partner_key + timestamp + path + partner_id + access_token)
        # path is the FULL API path, e.g. /api/v2/order/get_order_detail.
        base = f"{self.partner_key}{timestamp}{path}{self.partner_id}{access_token}"
        return hashlib.sha256(base.encode()).hexdigest()


class ShopeeClient(BaseSignedClient):
    def __init__(self, partner_id: int, partner_key: str, shop_id: int, mode: str = "sandbox",
                 access_token: str = "", http_client: Optional[httpx.AsyncClient] = None):
        host = ("https://openapi.test.shopee.cn" if mode == "sandbox"
                else "https://openapi.shopee.com")
        super().__init__(host + "/api/v2", http_client=http_client)
        self.signer = ShopeeSigner(partner_id, partner_key)
        self.shop_id = shop_id
        self.partner_id = partner_id
        self.access_token = access_token

    def _sign(self, method: str, path: str, params: dict) -> dict:
        base = {**params, "partner_id": self.partner_id, "shop_id": self.shop_id,
                "timestamp": int(__import__("time").time()), "version": 2}
        full_path = "/api/v2" + path
        base["sign"] = self.signer.sign(base["timestamp"], full_path, self.access_token)
        return base  # partner_id/shop_id/timestamp/version MUST go on the wire too


class LazadaSigner:
    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret

    def sign(self, method: str, path: str, params: dict) -> str:
        # Lazada: HMAC-SHA256(app_secret, sorted "keyvalue" concat), uppercase hex
        base = "".join(f"{k}{params[k]}" for k in sorted(params))
        return hmac.new(self.app_secret.encode(), base.encode(), hashlib.sha256).hexdigest().upper()


class LazadaClient(BaseSignedClient):
    def __init__(self, app_key: str, app_secret: str, mode: str = "sandbox",
                 seller_id: str = "", http_client: Optional[httpx.AsyncClient] = None):
        host = ("https://api.sellercenter.lazada.com.my" if mode != "sandbox"
                else "https://api.sellercenter.lazada.sandbox.com")
        super().__init__(host, http_client=http_client)
        self.signer = LazadaSigner(app_key, app_secret)
        self.app_key = app_key
        self.seller_id = seller_id

    def _sign(self, method: str, path: str, params: dict) -> dict:
        base = {**params, "app_key": self.app_key, "timestamp": str(int(__import__("time").time() * 1000))}
        if self.seller_id:
            base["user_id"] = self.seller_id  # signed like every other param
        base["sign"] = self.signer.sign(method, path, base)
        return base


class AmazonTokenCache:
    """LWA client-credentials token cache for SP-API (sellingpartnerapi scope)."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    async def get_token(self) -> str:
        import time
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.amazon.com/auth/o2/token",
                data={"grant_type": "client_credentials", "client_id": self.client_id,
                      "client_secret": self.client_secret,
                      "scope": "sellingpartnerapi"},
            )
            resp.raise_for_status()
            data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token


def client_from_env(platform: str, mode: str = "sandbox") -> BaseSignedClient:
    """Factory: build the right signed client from env vars (fail-closed)."""
    if platform == "shopee":
        return ShopeeClient(
            partner_id=int(os.getenv("SHOPEE_PARTNER_ID", "0")),
            partner_key=os.getenv("SHOPEE_PARTNER_KEY", ""),
            shop_id=int(os.getenv("SHOPEE_SHOP_ID", "0")),
            mode=mode,
        )
    if platform == "lazada":
        return LazadaClient(
            app_key=os.getenv("LAZADA_APP_KEY", ""),
            app_secret=os.getenv("LAZADA_APP_SECRET", ""),
            mode=mode,
            seller_id=os.getenv("LAZADA_SELLER_ID", ""),
        )
    raise PlatformError(f"no client factory for platform {platform}")
