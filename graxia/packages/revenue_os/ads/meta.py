"""Meta Marketing API client — campaigns, insights metrics, budget/status setters.
429-aware backoff; every request goes through one client."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import ADS_METRICS_WINDOW_DAYS
from ..models import AdCampaignSync
from .base import AdPlatformClient, AdPlatformError

API_VERSION = "v19.0"
MAX_ATTEMPTS = 3


class MetaAdsClient(AdPlatformClient):
    def __init__(self, access_token: Optional[str] = None, ad_account_id: Optional[str] = None,
                 http_client: Optional[httpx.AsyncClient] = None):
        import os
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN", "")
        self.ad_account_id = ad_account_id or os.getenv("META_AD_ACCOUNT_ID", "")
        self.base_url = f"https://graph.facebook.com/{API_VERSION}/act_{self.ad_account_id}"
        self._client = http_client

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self._client is not None:
            await self._client.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if not self.access_token or not self.ad_account_id:
            raise AdPlatformError("META_ACCESS_TOKEN / META_AD_ACCOUNT_ID not configured")
        client = await self._ensure_client()
        p = {"access_token": self.access_token, **(params or {})}
        last = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = await client.get(self.base_url + path, params=p)
            if resp.status_code == 429:
                import asyncio
                await asyncio.sleep(1.0 * attempt)
                continue
            if resp.status_code >= 400:
                raise AdPlatformError(f"Meta GET {path} -> {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise AdPlatformError(f"Meta GET {path} rate-limited after {MAX_ATTEMPTS} attempts: {last}")

    async def _post(self, path: str, params: dict) -> dict:
        if not self.access_token or not self.ad_account_id:
            raise AdPlatformError("META_ACCESS_TOKEN / META_AD_ACCOUNT_ID not configured")
        client = await self._ensure_client()
        p = {"access_token": self.access_token, **params}
        resp = await client.post(self.base_url + path, data=p)
        if resp.status_code >= 400:
            raise AdPlatformError(f"Meta POST {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def list_campaigns(self) -> list[dict]:
        data = await self._get("/campaigns", {"fields": "id,name,status,daily_budget", "limit": 100})
        return [{
            "platform_campaign_id": c["id"],
            "name": c.get("name"),
            "status": c.get("status"),
            "daily_budget_cents": int(c.get("daily_budget") or 0),  # Meta reports cents already
        } for c in data.get("data", [])]

    async def get_metrics(self, campaign_ids: list[str]) -> dict[str, dict]:
        out = {}
        for cid in campaign_ids:
            try:
                data = await self._get(f"/{cid}/insights", {
                    "fields": "spend,purchase_roas,purchases",
                    "date_preset": f"last_{ADS_METRICS_WINDOW_DAYS}d",
                })
                row = (data.get("data") or [{}])[0]
                spend = int(Decimal(str(row.get("spend") or 0)) * 100)
                roas = float(row.get("purchase_roas") or 0)
                revenue = int(spend * roas)
                out[cid] = {"spend_cents": spend, "revenue_cents": revenue, "roas": roas}
            except AdPlatformError:
                out[cid] = {"spend_cents": 0, "revenue_cents": 0, "roas": 0.0}
        return out

    async def set_budget(self, campaign_id: str, daily_budget_cents: int) -> None:
        await self._post(f"/{campaign_id}", {"daily_budget": str(daily_budget_cents)})

    async def set_status(self, campaign_id: str, active: bool) -> None:
        await self._post(f"/{campaign_id}", {"status": "ACTIVE" if active else "PAUSED"})


async def sync_ads_metrics(db: AsyncSession, platform: str, metrics: dict[str, dict]) -> int:
    """Upsert AdCampaignSync rows (spend/revenue/roas only — never budgets)."""
    synced = 0
    for cid, m in metrics.items():
        row = await db.scalar(
            select(AdCampaignSync).where(
                AdCampaignSync.platform == platform,
                AdCampaignSync.platform_campaign_id == cid,
            )
        )
        if row is None:
            row = AdCampaignSync(platform=platform, platform_campaign_id=cid)
            db.add(row)
        row.spend_cents = m.get("spend_cents", 0)
        row.revenue_cents = m.get("revenue_cents", 0)
        row.roas = m.get("roas", 0.0)
        row.status = m.get("status") or "ACTIVE"  # ads engine filters on this
        row.last_synced_at = datetime.now(timezone.utc)
        synced += 1
    await db.commit()
    return synced
