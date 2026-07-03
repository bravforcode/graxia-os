"""
Tests for the Funnel AI Recommendation Engine

Validates that the recommendation service correctly:
- Generates CRITICAL recs for blocking issues (no products, no assets, broken checkout)
- Generates HIGH/MEDIUM recs for below-benchmark metrics
- Calculates accurate health scores
- Prioritizes and deduplicates recommendations
- Scopes recommendations per-product correctly
- Exposes recommendations via authenticated API
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch
from uuid import uuid4, UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DeliveryAsset,
    DigitalProduct,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelOrderItem,
)
from app.services.funnel_ai_recommendation_service import (
    FunnelAIRecommendationService,
    RecommendationPriority,
    RecommendationCategory,
)
from tests.factories import OrganizationFactory


# ── Helpers ──────────────────────────────────────────────────────────────────

async def make_product(db, org_id, name="Test Product", slug=None, status="published",
                       price=100.0, stripe_price_id="price_test_123"):
    p = DigitalProduct(
        id=uuid4(),
        organization_id=org_id,
        name=name,
        slug=slug or name.lower().replace(" ", "-"),
        price_amount=Decimal(str(price)),
        status=status,
        stripe_price_id=stripe_price_id,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def make_asset(db, org_id, product_id, title="Guide PDF"):
    a = DeliveryAsset(
        id=uuid4(),
        organization_id=org_id,
        product_id=product_id,
        asset_type="file",
        title=title,
        storage_path="products/guide.pdf",
        is_active=True,
    )
    db.add(a)
    await db.commit()
    return a


async def log_events(db, org_id, event_type, count, product_id=None, source=None):
    for i in range(count):
        event = ConversionEvent(
            id=uuid4(),
            organization_id=org_id,
            event_type=event_type,
            product_id=product_id,
            source=source or "direct",
            session_id=f"sess-{uuid4().hex[:8]}",
            occurred_at=datetime.now(UTC) - timedelta(hours=i),
        )
        db.add(event)
    await db.commit()


async def make_paid_order(db, org_id, product_id, amount=100.0):
    order = FunnelOrder(
        id=uuid4(),
        organization_id=org_id,
        status="paid",
        subtotal_amount=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
        currency="THB",
        customer_email="buyer@test.com",
        paid_at=datetime.now(UTC),
    )
    db.add(order)
    await db.commit()

    item = FunnelOrderItem(
        id=uuid4(),
        organization_id=org_id,
        order_id=order.id,
        product_id=product_id,
        quantity=1,
        unit_amount=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
    )
    db.add(item)
    await db.commit()
    return order


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFunnelAIRecommendations:

    async def test_critical_rec_when_no_published_products(self, db_session: AsyncSession):
        """CRITICAL recommendation emitted when org has no published products."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id, days_back=30)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "no-published-products" in rec_ids

        rec = next(r for r in result["recommendations"] if r["id"] == "no-published-products")
        assert rec["priority"] == RecommendationPriority.CRITICAL.value
        assert rec["category"] == RecommendationCategory.PRODUCT.value

    async def test_critical_rec_draft_products_mentioned(self, db_session: AsyncSession):
        """When drafts exist, the no-published-products rec mentions them."""
        org = await OrganizationFactory.build(db_session)
        await make_product(db_session, org.id, name="Draft Ebook", status="draft",
                           stripe_price_id=None)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id)

        rec = next(r for r in result["recommendations"] if r["id"] == "no-published-products")
        assert rec["data"]["draft_count"] == 1

    async def test_critical_rec_no_traffic(self, db_session: AsyncSession):
        """CRITICAL rec when product is published but has zero traffic."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "no-traffic" in rec_ids

    async def test_critical_rec_no_delivery_assets(self, db_session: AsyncSession):
        """CRITICAL rec when published product has no delivery assets."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        # No asset added

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert f"no-assets-{str(product.id)[:8]}" in rec_ids

    async def test_critical_rec_no_stripe_price(self, db_session: AsyncSession):
        """CRITICAL rec when published product has no Stripe price ID."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id, stripe_price_id=None)
        await make_asset(db_session, org.id, product.id)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert f"no-stripe-{str(product.id)[:8]}" in rec_ids

    async def test_critical_rec_broken_checkout_completion(self, db_session: AsyncSession):
        """CRITICAL rec when checkout-to-purchase rate is critically low (>5 starts, <30%)."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        # 100 views, 10 checkout starts, only 1 purchase → 10% c2p rate
        await log_events(db_session, org.id, "page_view", 100, product.id)
        await log_events(db_session, org.id, "checkout_start", 10, product.id)
        await log_events(db_session, org.id, "purchase", 1, product.id)
        await make_paid_order(db_session, org.id, product.id, 500.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "low-checkout-completion" in rec_ids

        rec = next(r for r in result["recommendations"] if r["id"] == "low-checkout-completion")
        assert rec["priority"] == RecommendationPriority.CRITICAL.value

    async def test_high_rec_low_lead_conversion(self, db_session: AsyncSession):
        """HIGH rec when lead conversion rate is critically low (<50% of benchmark)."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        # 200 views, 0 lead captures → 0% lead conversion
        await log_events(db_session, org.id, "page_view", 200, product.id)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "low-lead-conversion" in rec_ids

    async def test_high_rec_no_lead_capture_at_all(self, db_session: AsyncSession):
        """HIGH rec when there's traffic but zero leads captured."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        await log_events(db_session, org.id, "page_view", 50, product.id)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "no-lead-capture" in rec_ids

    async def test_high_rec_low_delivery_open_rate(self, db_session: AsyncSession):
        """HIGH rec when delivery open rate is very low."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        # 5 purchases but only 1 delivery opened
        await log_events(db_session, org.id, "page_view", 200, product.id)
        await log_events(db_session, org.id, "purchase", 5, product.id)
        await log_events(db_session, org.id, "delivery_opened", 1, product.id)
        for _ in range(5):
            await make_paid_order(db_session, org.id, product.id, 100.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "low-delivery-open" in rec_ids

    async def test_medium_rec_low_aov(self, db_session: AsyncSession):
        """MEDIUM rec when AOV is below $20."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id, price=10.0)
        await make_asset(db_session, org.id, product.id)

        await log_events(db_session, org.id, "page_view", 200, product.id)
        for _ in range(5):
            await make_paid_order(db_session, org.id, product.id, 10.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "low-aov" in rec_ids

        rec = next(r for r in result["recommendations"] if r["id"] == "low-aov")
        assert rec["priority"] == RecommendationPriority.MEDIUM.value
        assert rec["metric_value"] == 10.0

    async def test_no_duplicate_recommendations(self, db_session: AsyncSession):
        """Recommendations are deduplicated by ID."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id)

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert len(rec_ids) == len(set(rec_ids))

    async def test_recommendations_sorted_by_priority(self, db_session: AsyncSession):
        """Recommendations are sorted CRITICAL → HIGH → MEDIUM → LOW."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        # No asset → CRITICAL; some traffic but no leads → HIGH; low AOV → MEDIUM
        await log_events(db_session, org.id, "page_view", 200, product.id)
        await log_events(db_session, org.id, "purchase", 10, product.id)
        for _ in range(10):
            await make_paid_order(db_session, org.id, product.id, 5.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [priority_order[r["priority"]] for r in result["recommendations"]]
        assert priorities == sorted(priorities)

    async def test_health_score_zero_revenue_no_products(self, db_session: AsyncSession):
        """Health score is low when no products and no revenue."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id)

        health = result["health_score"]
        assert health["overall"] < 40
        assert health["revenue"] == 0
        assert health["label"] in ["Critical", "Needs Work"]

    async def test_health_score_improves_with_revenue(self, db_session: AsyncSession):
        """Health score revenue dimension improves as revenue increases."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        await log_events(db_session, org.id, "page_view", 500, product.id)
        await log_events(db_session, org.id, "purchase", 20, product.id)
        for _ in range(20):
            await make_paid_order(db_session, org.id, product.id, 1000.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        health = result["health_score"]
        assert health["revenue"] >= 60
        assert health["traffic"] >= 50

    async def test_product_scoped_recommendations(self, db_session: AsyncSession):
        """Product-scoped recs only analyze that product's data."""
        org = await OrganizationFactory.build(db_session)
        product_a = await make_product(db_session, org.id, name="Product A", slug="prod-a")
        product_b = await make_product(db_session, org.id, name="Product B", slug="prod-b")
        await make_asset(db_session, org.id, product_a.id)
        await make_asset(db_session, org.id, product_b.id)

        # Only product_a gets traffic
        await log_events(db_session, org.id, "page_view", 200, product_a.id)

        service = FunnelAIRecommendationService(db_session)

        # Product B scoped: no traffic → should get "no-traffic"
        result_b = await service.get_product_recommendations(org.id, product_b.id)
        rec_ids_b = [r["id"] for r in result_b["recommendations"]]
        assert "no-traffic" in rec_ids_b

        # Product A scoped: has traffic but no leads → should NOT have "no-traffic"
        result_a = await service.get_product_recommendations(org.id, product_a.id)
        rec_ids_a = [r["id"] for r in result_a["recommendations"]]
        assert "no-traffic" not in rec_ids_a

    async def test_tenant_isolation_in_recommendations(self, db_session: AsyncSession):
        """Recommendations do not bleed across organizations."""
        org1 = await OrganizationFactory.build(db_session)
        org2 = await OrganizationFactory.build(db_session)

        # org1 has published product with good revenue
        prod = await make_product(db_session, org1.id)
        await make_asset(db_session, org1.id, prod.id)
        await log_events(db_session, org1.id, "page_view", 500, prod.id)
        for _ in range(10):
            await make_paid_order(db_session, org1.id, prod.id, 500.0)

        # org2 has nothing
        service2 = FunnelAIRecommendationService(db_session)
        result2 = await service2.get_recommendations(org2.id)

        # org2 should see its own "no products" rec, not org1's data
        assert result2["metrics_snapshot"]["views"] == 0
        assert result2["metrics_snapshot"]["total_revenue"] == 0.0
        rec_ids = [r["id"] for r in result2["recommendations"]]
        assert "no-published-products" in rec_ids

    async def test_metrics_snapshot_included(self, db_session: AsyncSession):
        """Response includes metrics_snapshot with correct values."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        await log_events(db_session, org.id, "page_view", 100, product.id)
        await log_events(db_session, org.id, "lead_capture", 5, product.id)
        await log_events(db_session, org.id, "purchase", 3, product.id)
        for _ in range(3):
            await make_paid_order(db_session, org.id, product.id, 200.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        snap = result["metrics_snapshot"]
        assert snap["views"] == 100
        assert snap["leads"] == 5
        assert snap["purchases"] == 3
        assert snap["total_revenue"] == 600.0
        assert snap["aov"] == 200.0

    async def test_response_structure(self, db_session: AsyncSession):
        """Response has all required top-level keys."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id)

        assert "health_score" in result
        assert "recommendations" in result
        assert "metrics_snapshot" in result
        assert "analysis_period_days" in result
        assert "generated_at" in result
        assert "total_recommendations" in result

        health = result["health_score"]
        for key in ["overall", "conversion", "traffic", "revenue", "delivery", "label", "summary"]:
            assert key in health

    async def test_recommendation_structure(self, db_session: AsyncSession):
        """Each recommendation has all required fields."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id)

        assert len(result["recommendations"]) > 0
        for rec in result["recommendations"]:
            for key in ["id", "title", "description", "action", "priority",
                        "category", "impact_estimate", "effort", "metric_trigger"]:
                assert key in rec, f"Missing key '{key}' in recommendation {rec.get('id')}"

    async def test_max_recommendations_limit_respected(self, db_session: AsyncSession):
        """max_recommendations parameter caps the output."""
        org = await OrganizationFactory.build(db_session)
        service = FunnelAIRecommendationService(db_session)

        result = await service.get_recommendations(org.id, max_recommendations=2)

        assert len(result["recommendations"]) <= 2

    async def test_analysis_period_respected(self, db_session: AsyncSession):
        """Events outside the analysis window are excluded."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        # Add views far in the past (60 days ago)
        old_event = ConversionEvent(
            id=uuid4(),
            organization_id=org.id,
            event_type="page_view",
            product_id=product.id,
            occurred_at=datetime.now(UTC) - timedelta(days=60),
        )
        db_session.add(old_event)
        await db_session.commit()

        service = FunnelAIRecommendationService(db_session)
        # 7-day window should NOT include the 60-day-old event
        result = await service.get_recommendations(org.id, days_back=7)

        assert result["metrics_snapshot"]["views"] == 0

    async def test_good_funnel_gets_lower_priority_recs(self, db_session: AsyncSession):
        """A well-performing funnel only gets MEDIUM or LOW recommendations."""
        org = await OrganizationFactory.build(db_session)
        product = await make_product(db_session, org.id)
        await make_asset(db_session, org.id, product.id)

        # Solid metrics: good traffic, good leads, good checkout rate
        await log_events(db_session, org.id, "page_view", 300, product.id)
        await log_events(db_session, org.id, "lead_capture", 15, product.id)   # 5% lcr
        await log_events(db_session, org.id, "checkout_start", 20, product.id)
        await log_events(db_session, org.id, "purchase", 14, product.id)       # 70% c2p
        await log_events(db_session, org.id, "delivery_opened", 12, product.id)
        for _ in range(14):
            await make_paid_order(db_session, org.id, product.id, 200.0)

        service = FunnelAIRecommendationService(db_session)
        result = await service.get_recommendations(org.id)

        # Should have no CRITICAL recs
        critical = [r for r in result["recommendations"]
                    if r["priority"] == RecommendationPriority.CRITICAL.value]
        assert len(critical) == 0

        # Health score should be Good or Excellent
        assert result["health_score"]["overall"] >= 55


@pytest.mark.asyncio
class TestFunnelAIRecommendationAPI:
    """Test the AI recommendation API endpoints."""

    async def test_authenticated_user_can_get_recommendations(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """Authenticated org user can fetch recommendations."""
        response = await async_client.get("/api/v1/funnel/ai/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "health_score" in data
        assert "recommendations" in data

    async def test_recommendations_default_params(
        self, async_client: AsyncClient
    ):
        """Default params (30 days, 10 max) work correctly."""
        response = await async_client.get("/api/v1/funnel/ai/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_period_days"] == 30
        assert len(data["recommendations"]) <= 10

    async def test_recommendations_custom_params(
        self, async_client: AsyncClient
    ):
        """Custom days_back and max_recommendations params are respected."""
        response = await async_client.get(
            "/api/v1/funnel/ai/recommendations?days_back=7&max_recommendations=3"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_period_days"] == 7
        assert len(data["recommendations"]) <= 3

    async def test_product_scoped_recommendations_api(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """Product-scoped recommendation endpoint works."""
        # Create product via API
        create_res = await async_client.post("/api/v1/funnel/products", json={
            "name": "AI Scoped Product", "slug": "ai-scoped-product", "price_amount": "499.00"
        })
        assert create_res.status_code == 201
        product_id = create_res.json()["id"]

        response = await async_client.get(
            f"/api/v1/funnel/ai/recommendations/products/{product_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "health_score" in data
        assert "recommendations" in data

    async def test_unauthenticated_request_rejected(
        self, public_async_client: AsyncClient
    ):
        """Unauthenticated requests to AI endpoint return 401."""
        response = await public_async_client.get("/api/v1/funnel/ai/recommendations")
        assert response.status_code == 401

    async def test_invalid_days_back_rejected(self, async_client: AsyncClient):
        """days_back=0 is rejected with 422."""
        response = await async_client.get(
            "/api/v1/funnel/ai/recommendations?days_back=0"
        )
        assert response.status_code == 422

    async def test_invalid_max_recommendations_rejected(self, async_client: AsyncClient):
        """max_recommendations=0 is rejected with 422."""
        response = await async_client.get(
            "/api/v1/funnel/ai/recommendations?max_recommendations=0"
        )
        assert response.status_code == 422
