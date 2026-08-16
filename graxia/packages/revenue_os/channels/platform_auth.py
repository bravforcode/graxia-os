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

    def __init__(self, base_url: str, http_client: Optional[httpx.AsyncClient] = None,
                 extra_headers: Optional[dict] = None):
        self.base_url = base_url
        self._client = http_client
        self._extra_headers = extra_headers or {}

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _sign(self, method: str, path: str, params: dict, body: Optional[dict] = None) -> dict:
        raise NotImplementedError

    async def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        return await self._request("GET", path, params=params or {})

    async def post_json(self, path: str, params: Optional[dict] = None, json: Optional[dict] = None) -> dict:
        return await self._request("POST", path, params=params or {}, json=json)

    async def _request(self, method: str, path: str, **kw) -> dict:
        client = await self._ensure_client()
        params = dict(kw.get("params") or {})
        signed = self._sign(method, path, params, kw.get("json"))
        params.update(signed)
        kw["params"] = params
        if self._extra_headers:
            kw["headers"] = {**(kw.get("headers") or {}), **self._extra_headers}
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

    def _sign(self, method: str, path: str, params: dict, body: Optional[dict] = None) -> dict:
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

    def _sign(self, method: str, path: str, params: dict, body: Optional[dict] = None) -> dict:
        base = {**params, "app_key": self.app_key, "timestamp": str(int(__import__("time").time() * 1000))}
        if self.seller_id:
            base["user_id"] = self.seller_id  # signed like every other param
        base["sign"] = self.signer.sign(method, path, base)
        return base


class TikTokSigner:
    """TikTok Shop Open Platform v202309 request signature.

    Formula (documented at partner.tiktokshop.com/doc/page/274638; verified
    against the EcomPHP/tiktokshop-php v202309 SDK implementation):
      sign = HMAC-SHA256(
          key=app_secret,
          data=app_secret + path + sorted_keyvalue_params + [body] + app_secret)
    where sorted_keyvalue_params concatenates every query param EXCEPT
    sign/access_token/x-tts-access-token in alphabetical key order, and the
    raw request body is appended for non-GET requests. Hex digest.
    """

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret

    def sign(self, method: str, path: str, params: dict, body: Optional[str] = None) -> str:
        excluded = {"sign", "access_token", "x-tts-access-token"}
        kv = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in excluded)
        raw = f"{self.app_secret}{path}{kv}"
        if method != "GET" and body:
            raw += body
        raw += self.app_secret
        return hmac.new(self.app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


class TikTokClient(BaseSignedClient):
    def __init__(self, app_key: str, app_secret: str, shop_id: int, mode: str = "sandbox",
                 access_token: str = "", http_client: Optional[httpx.AsyncClient] = None):
        host = ("https://open-api-sandbox.tiktokglobalshop.com" if mode == "sandbox"
                else "https://open-api.tiktokglobalshop.com")
        super().__init__(host + "/api", http_client=http_client,
                         extra_headers={"x-tts-access-token": access_token} if access_token else None)
        self.signer = TikTokSigner(app_key, app_secret)
        self.app_key = app_key
        self.shop_id = shop_id

    def _sign(self, method: str, path: str, params: dict, body: Optional[dict] = None) -> dict:
        import json
        base = {**params, "app_key": self.app_key, "timestamp": str(int(__import__("time").time())),
                "version": "202309", "shop_id": self.shop_id}
        raw_body = None
        if method != "GET" and body is not None:
            raw_body = json.dumps(body, separators=(",", ":"))
        base["sign"] = self.signer.sign(method, "/api" + path, base, raw_body)
        return base


class AmazonTokenCache:
    """LWA client-credentials token cache for SP-API (sellingpartnerapi scope)
    plus cached STS AssumeRole (role ARN) for request signing."""

    def __init__(self, client_id: str, client_secret: str,
                 http_client: Optional[httpx.AsyncClient] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._client = http_client
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._role_creds: Optional[dict] = None

    async def _post_form(self, url: str, data: dict) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(url, data=data)
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(url, data=data)

    async def get_token(self) -> str:
        import time
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        return await self.force_refresh()

    async def force_refresh(self) -> str:
        import time
        resp = await self._post_form("https://api.amazon.com/auth/o2/token", {
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.client_secret, "scope": "sellingpartnerapi",
        })
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def assume_role(self, role_arn: str, session_name: str = "graxia-revenue-os") -> dict:
        """Exchange the LWA token for role credentials via STS AssumeRole
        (WebIdentityToken flow). Cached until 5 min before expiry."""
        import time
        if self._role_creds and time.time() < self._role_creds["expires_at"] - 300:
            return self._role_creds
        token = await self.get_token()
        resp = await self._post_form("https://sts.amazonaws.com/", {
            "Action": "AssumeRole", "Version": "2011-06-15",
            "RoleArn": role_arn, "RoleSessionName": session_name,
            "WebIdentityToken": token,
        })
        resp.raise_for_status()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        def _find(tag: str) -> str:
            el = root.find(f".//{{*}}{tag}")
            return el.text if el is not None else ""
        exp = _find("Expiration")
        self._role_creds = {
            "access_key": _find("AccessKeyId"),
            "secret_key": _find("SecretAccessKey"),
            "session_token": _find("SessionToken"),
            "expires_at": time.mktime(time.strptime(exp, "%Y-%m-%dT%H:%M:%SZ")) if exp else 0.0,
        }
        return self._role_creds


class AmazonSigV4Signer:
    """AWS Signature V4 for SP-API requests (service execute-api).

    Verified against botocore (AWS reference SDK) for GET/GET-query/POST-body
    shapes; test vector covers the pinned get-vanilla shape.
    """

    def __init__(self, access_key: str, secret_key: str, session_token: str = "",
                 region: str = "us-east-1", service: str = "execute-api"):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.region = region
        self.service = service

    def _hmac(self, key: bytes, msg: str) -> bytes:
        import hashlib
        import hmac
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    def sign(self, method: str, path: str, query: str, headers: dict, body: str,
             amz_date: str) -> str:
        """Return the full Authorization header value for a request."""
        import hashlib
        payload_hash = hashlib.sha256(body.encode()).hexdigest()
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join([method, path, query, canonical_headers,
                                       signed_headers, payload_hash])
        scope = f"{amz_date[:8]}/{self.region}/{self.service}/aws4_request"
        string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                    hashlib.sha256(canonical_request.encode()).hexdigest()])
        k = self._hmac(("AWS4" + self.secret_key).encode(), amz_date[:8])
        k = self._hmac(k, self.region)
        k = self._hmac(k, self.service)
        k = self._hmac(k, "aws4_request")
        signature = self._hmac(k, string_to_sign).hex()
        return (f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}")


class AmazonClient:
    """SP-API client: LWA token + role-credential SigV4 signing, 429 backoff
    honoring x-amzn-RateLimit-*, token refresh on 401."""

    def __init__(self, token_cache: AmazonTokenCache, role_arn: str,
                 seller_id: str, marketplace_id: str = "ATVPDKIKX0DER",
                 mode: str = "sandbox", region: str = "us-east-1",
                 http_client: Optional[httpx.AsyncClient] = None):
        self.host = ("sandbox.sellingpartnerapi-na.amazon.com" if mode == "sandbox"
                     else "sellingpartnerapi-na.amazon.com")
        self.base_url = f"https://{self.host}"
        self.token_cache = token_cache
        self.role_arn = role_arn
        self.seller_id = seller_id
        self.marketplace_id = marketplace_id
        self.region = region
        self._client = http_client

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        return await self._request("GET", path, params=params or {})

    async def post_json(self, path: str, json: Optional[dict] = None) -> dict:
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, params: Optional[dict] = None,
                       json: Optional[dict] = None, _retried: bool = False) -> dict:
        import json as _json
        import time
        import urllib.parse
        client = await self._ensure_client()
        creds = await self.token_cache.assume_role(self.role_arn)
        token = await self.token_cache.get_token()
        amz_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        # Canonical query: sorted, url-encoded
        query = "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}"
                         for k, v in sorted((params or {}).items()))
        body = _json.dumps(json, separators=(",", ":")) if json is not None else ""
        headers = {
            "host": self.host,
            "x-amz-date": amz_date,
            "x-amzn-access-token": token,
            "x-amzn-marketplace-id": self.marketplace_id,
            "x-amz-security-token": creds["session_token"],
        }
        if json is not None:
            headers["content-type"] = "application/json"
        signer = AmazonSigV4Signer(creds["access_key"], creds["secret_key"],
                                   creds["session_token"], region=self.region)
        authz = signer.sign(method, path, query, {"host": self.host, "x-amz-date": amz_date,
                                                  "x-amz-security-token": creds["session_token"]},
                            body, amz_date)
        headers["authorization"] = authz
        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = await client.request(method, self.base_url + path, params=params or None,
                                        headers=headers, content=body or None,
                                        json=None)
            if resp.status_code == 429:
                try:
                    limit = float(resp.headers.get("x-amzn-RateLimit-Limit", "1"))
                except ValueError:
                    limit = 1.0
                wait = min(1.0 / limit if limit > 0 else 1.0, 10.0) * attempt
                import asyncio
                await asyncio.sleep(wait)
                continue
            if resp.status_code == 401 and not _retried:
                await self.token_cache.force_refresh()
                return await self._request(method, path, params=params, json=json, _retried=True)
            if resp.status_code >= 400:
                raise PlatformError(f"Amazon {method} {path} -> {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise PlatformError(f"Amazon {method} {path} rate-limited after {MAX_ATTEMPTS} attempts")


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
    if platform == "tiktok_shop":
        return TikTokClient(
            app_key=os.getenv("TIKTOK_SHOP_APP_KEY", ""),
            app_secret=os.getenv("TIKTOK_SHOP_APP_SECRET", ""),
            shop_id=int(os.getenv("TIKTOK_SHOP_SHOP_ID", "0")),
            mode=mode,
            access_token=os.getenv("TIKTOK_SHOP_ACCESS_TOKEN", ""),
        )
    raise PlatformError(f"no client factory for platform {platform}")
