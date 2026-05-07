"""
Load tests for Revenue OS - tests with 1000+ campaigns.

These tests verify performance under realistic load:
1. Campaign engine with 1000+ campaigns
2. Concurrent approval requests
3. Query performance monitoring
"""

import asyncio
import os
import time
from uuid import uuid4

import pytest
from app.database import get_db_session
from sqlalchemy import func, select

# Skip all tests in this file if Graxia OS is not enabled
GRAXIA_ENABLED = os.getenv("GRAXIA_ENABLED", "false").lower() == "true"
pytestmark = pytest.mark.skipif(
    not GRAXIA_ENABLED, reason="Graxia OS is not enabled (GRAXIA_ENABLED=false)"
)

if GRAXIA_ENABLED:
    from graxia.packages.revenue_os.celery.tasks.campaign_engine import (
        _async_impl as campaign_engine_impl,
    )
    from graxia.packages.revenue_os.models import (
        Approval,
        ApprovalStatus,
        AttributionEvent,
        CampaignStatus,
        IncidentEvent,
        Order,
        OrderStatus,
        RevenueCampaign,
    )
    from graxia.packages.revenue_os.services import ApprovalService


@pytest.mark.asyncio
@pytest.mark.slow
async def test_campaign_engine_with_1000_campaigns():
    """
    Load test: Campaign engine with 1000+ active campaigns.
    Verifies N+1 query fixes hold up under load.
    """
    async with get_db_session() as db:
        # Create 1000 campaigns
        print("\nCreating 1000 campaigns...")
        campaigns = []
        for i in range(1000):
            campaign = RevenueCampaign(
                name=f"Load Test Campaign {i}",
                created_by_agent="LoadTest",
                status=CampaignStatus.ACTIVE.value,
                budget_cents=100_000,
                target_revenue_cents=500_000,
            )
            db.add(campaign)
            if i % 100 == 0:
                await db.flush()
                print(f"  Created {i} campaigns...")
            campaigns.append(campaign)

        await db.commit()
        print("✓ 1000 campaigns created")

        # Create orders and attributions for subset of campaigns
        print("Creating orders and attributions...")
        for i in range(0, 1000, 10):  # Every 10th campaign gets orders
            campaign = campaigns[i]
            for j in range(5):  # 5 orders per campaign
                order = Order(
                    platform="test",
                    platform_order_id=f"load_order_{i}_{j}",
                    customer_email=f"customer{i}_{j}@test.com",
                    amount_cents=50_000,
                    currency="USD",
                    status=OrderStatus.PAID.value,
                    idempotency_key=f"load_idem_{i}_{j}",
                )
                db.add(order)
                await db.flush()

                attribution = AttributionEvent(
                    campaign_id=campaign.id,
                    order_id=order.id,
                    event_type="purchase",
                    channel="email",
                )
                db.add(attribution)

        await db.commit()
        print("✓ Orders and attributions created")

        # Run campaign engine and measure performance
        print("\nRunning campaign engine...")
        start_time = time.time()

        result = await campaign_engine_impl()

        elapsed = time.time() - start_time
        print(f"✓ Campaign engine completed in {elapsed:.2f}s")
        print(f"  Results: {result}")

        # Performance assertion: should complete in under 10 seconds
        # (with N+1 fixes, this should be fast even with 1000 campaigns)
        assert elapsed < 10.0, f"Campaign engine too slow: {elapsed:.2f}s"

        # Verify revenue was computed correctly
        assert result["roas_updated"] == 1000


@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_approval_requests():
    """
    Load test: 100 concurrent approval requests.
    Verifies ApprovalService handles concurrent access correctly.
    """
    async with get_db_session() as db:
        # Create 100 campaigns with pending approvals
        print("\nCreating 100 campaigns with approvals...")
        approval_ids = []
        for i in range(100):
            campaign = RevenueCampaign(
                name=f"Concurrent Test Campaign {i}",
                created_by_agent="ConcurrentTest",
                status=CampaignStatus.DRAFT.value,
                budget_cents=100_000,
            )
            db.add(campaign)
            await db.flush()

            approval = Approval(
                item_type="campaign",
                item_id=campaign.id,
                requested_by_agent="ConcurrentTest",
                status=ApprovalStatus.PENDING.value,
            )
            db.add(approval)
            await db.flush()
            approval_ids.append(approval.id)

        await db.commit()
        print("✓ 100 campaigns with approvals created")

        # Approve all concurrently
        print("Approving all 100 concurrently...")
        start_time = time.time()

        async def approve_one(approval_id):
            async with get_db_session() as session:
                await ApprovalService.approve(
                    session,
                    approval_id,
                    ceo_notes="Batch approved",
                )

        # Run all approvals concurrently
        await asyncio.gather(*[approve_one(aid) for aid in approval_ids])

        elapsed = time.time() - start_time
        print(f"✓ All approvals completed in {elapsed:.2f}s")

        # Verify all campaigns are now ACTIVE
        async with get_db_session() as db:
            active_count = await db.scalar(
                select(func.count(RevenueCampaign.id)).where(
                    RevenueCampaign.status == CampaignStatus.ACTIVE.value,
                    RevenueCampaign.created_by_agent == "ConcurrentTest",
                )
            )
            assert active_count == 100, f"Expected 100 active campaigns, got {active_count}"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_query_performance_monitoring():
    """
    Performance test: Monitor query execution time for key operations.
    Ensures queries stay fast as data grows.
    """
    async with get_db_session() as db:
        # Create test data
        print("\nCreating test data for performance monitoring...")
        for i in range(500):
            campaign = RevenueCampaign(
                name=f"Perf Test Campaign {i}",
                created_by_agent="PerfTest",
                status=CampaignStatus.ACTIVE.value,
            )
            db.add(campaign)
        await db.commit()

        # Test 1: Revenue aggregation query
        print("\nTest 1: Revenue aggregation query...")
        start = time.time()
        result = await db.execute(
            select(
                AttributionEvent.campaign_id,
                func.coalesce(func.sum(Order.amount_cents), 0).label("total_revenue"),
            )
            .join(Order, AttributionEvent.order_id == Order.id)
            .where(Order.status == OrderStatus.PAID.value)
            .group_by(AttributionEvent.campaign_id)
        )
        list(result)  # Consume results
        elapsed = time.time() - start
        print(f"  ✓ Completed in {elapsed:.3f}s")
        assert elapsed < 1.0, f"Revenue aggregation too slow: {elapsed:.3f}s"

        # Test 2: Incident count query
        print("\nTest 2: Incident count query...")
        campaign_ids = [uuid4() for _ in range(500)]
        start = time.time()
        result = await db.execute(
            select(
                IncidentEvent.affected_campaign_id, func.count(IncidentEvent.id).label("open_count")
            )
            .where(
                IncidentEvent.affected_campaign_id.in_(campaign_ids),
                IncidentEvent.resolved_at.is_(None),
            )
            .group_by(IncidentEvent.affected_campaign_id)
        )
        list(result)
        elapsed = time.time() - start
        print(f"  ✓ Completed in {elapsed:.3f}s")
        assert elapsed < 0.5, f"Incident count query too slow: {elapsed:.3f}s"

        # Test 3: Approval lookup
        print("\nTest 3: Approval lookup...")
        start = time.time()
        result = await db.execute(
            select(Approval).where(Approval.status == ApprovalStatus.PENDING.value).limit(100)
        )
        list(result.scalars())
        elapsed = time.time() - start
        print(f"  ✓ Completed in {elapsed:.3f}s")
        assert elapsed < 0.1, f"Approval lookup too slow: {elapsed:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "slow"])
