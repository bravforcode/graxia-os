import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ads.meta import MetaAdsClient, sync_ads_metrics
from ..models import AdCampaignSync


def _client_with(handler):
    return MetaAdsClient(access_token="tok", ad_account_id="act_1",
                         http_client=AsyncClient(transport=MockTransport(handler)))


@pytest.mark.asyncio
async def test_list_campaigns_maps_budget_to_cents():
    def handler(request):
        assert "/campaigns" in request.url.path
        return Response(200, json={"data": [
            {"id": "2384", "name": "Launch", "status": "ACTIVE", "daily_budget": "1500"},
        ]})

    async with _client_with(handler) as client:
        camps = await client.list_campaigns()
    assert camps[0]["daily_budget_cents"] == 1500


@pytest.mark.asyncio
async def test_sync_ads_metrics_upserts(db_session: AsyncSession):
    await sync_ads_metrics(db_session, platform="meta", metrics={"2384": {"spend_cents": 500, "revenue_cents": 1500, "roas": 3.0}})
    row = (await db_session.execute(
        select(AdCampaignSync).where(AdCampaignSync.platform_campaign_id == "2384")
    )).scalar_one()
    assert row.roas == 3.0
    await sync_ads_metrics(db_session, platform="meta", metrics={"2384": {"spend_cents": 900, "revenue_cents": 2700, "roas": 3.0}})
    rows = (await db_session.execute(select(AdCampaignSync))).scalars().all()
    assert len(rows) == 1
    assert rows[0].spend_cents == 900


@pytest.mark.asyncio
async def test_set_budget_posts_cents():
    def handler(request):
        body = request.content.decode()
        assert "daily_budget" in body
        assert "9000" in body
        return Response(200, json={"success": True})

    async with _client_with(handler) as client:
        await client.set_budget("2384", 9000)
