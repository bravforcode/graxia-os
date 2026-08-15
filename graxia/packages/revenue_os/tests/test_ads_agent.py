import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.commerce_ops import CommerceOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode
from ..models import AdCampaignSync


@pytest.mark.asyncio
async def test_ads_job_cuts_budget_for_low_roas_within_policy(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    db_session.add(AdCampaignSync(platform="meta", platform_campaign_id="c1", name="C1",
                                  status="ACTIVE", daily_budget_cents=10000,
                                  spend_cents=5000, revenue_cents=20000, roas=4.0))
    await db_session.commit()

    calls = []

    class FakeClient:
        async def set_budget(self, campaign_id, daily_budget_cents):
            calls.append((campaign_id, daily_budget_cents))

    monkeypatch.setattr("graxia.packages.revenue_os.agents.commerce_ops.ads_client", FakeClient())
    actions, denials, proposals = await CommerceOpsAgent._ads_optimization(db_session, shadow=False)
    assert any("ad_budget" in a for a in actions)
    assert len(calls) == 1
    # 10% cut of 10,000 cents
    assert calls[0][1] == 9000


@pytest.mark.asyncio
async def test_ads_job_shadow_proposes_without_calling_api(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    db_session.add(AdCampaignSync(platform="meta", platform_campaign_id="c2", name="C2",
                                  status="ACTIVE", daily_budget_cents=10000,
                                  spend_cents=5000, revenue_cents=20000, roas=4.0))
    await db_session.commit()

    called = {"n": 0}

    class FakeClient:
        async def set_budget(self, campaign_id, daily_budget_cents):
            called["n"] += 1

    monkeypatch.setattr("graxia.packages.revenue_os.agents.commerce_ops.ads_client", FakeClient())
    actions, denials, proposals = await CommerceOpsAgent._ads_optimization(db_session, shadow=True)
    assert actions == []
    assert any("ad_budget" in p for p in proposals)
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_ads_job_pauses_roas_below_one(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    db_session.add(AdCampaignSync(platform="meta", platform_campaign_id="c3", name="C3",
                                  status="ACTIVE", daily_budget_cents=10000,
                                  spend_cents=5000, revenue_cents=2000, roas=0.4))
    await db_session.commit()

    calls = []

    class FakeClient:
        async def set_status(self, campaign_id, active):
            calls.append(("pause", campaign_id, active))

    monkeypatch.setattr("graxia.packages.revenue_os.agents.commerce_ops.ads_client", FakeClient())
    actions, denials, proposals = await CommerceOpsAgent._ads_optimization(db_session, shadow=False)
    assert any("campaign_pause" in a for a in actions)
    assert calls and calls[0][2] is False
