import pytest
from uuid import uuid4, UUID
from decimal import Decimal
from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelOrder, FunnelOrderItem, ConversionEvent
from app.models.organization import Organization
from tests.factories import OrganizationFactory

@pytest.mark.asyncio
class TestFunnelAnalytics:
    """Test suite for conversion analytics logging and reports"""

    async def test_public_log_event(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """1. Public logging of valid conversion events, and rejection of invalid event types"""
        # Create organization
        org = await OrganizationFactory.build(db_session)
        
        # Log a valid event
        payload = {
            "organization_id": str(org.id),
            "event_type": "page_view",
            "session_id": "session-123",
            "source": "google",
            "medium": "cpc",
            "campaign": "spring_sale",
        }
        res = await public_async_client.post("/api/v1/funnel/events", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["event_type"] == "page_view"
        assert data["session_id"] == "session-123"

        # Verify in DB
        stmt = select(ConversionEvent).where(ConversionEvent.id == UUID(data["id"]))
        db_res = await db_session.execute(stmt)
        event = db_res.scalar_one()
        assert event.organization_id == org.id

        # Log an invalid event
        bad_payload = {
            "organization_id": str(org.id),
            "event_type": "invalid_event_type_123",
        }
        res_bad = await public_async_client.post("/api/v1/funnel/events", json=bad_payload)
        assert res_bad.status_code == 400
        assert "Invalid event type" in res_bad.json()["detail"]

    async def test_analytics_tenant_isolation(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """2. Aggregation calculations enforce tenant boundaries"""
        # Retrieve organization created by the async_client fixture (admin org)
        res_org = await db_session.execute(select(Organization))
        admin_org = res_org.scalars().first()
        
        # Create a second organization
        other_org = await OrganizationFactory.build(db_session)

        # Log event for admin org
        event_admin = ConversionEvent(
            organization_id=admin_org.id,
            event_type="page_view",
            session_id="session-admin",
            occurred_at=datetime.utcnow(),
        )
        # Log event for other org
        event_other = ConversionEvent(
            organization_id=other_org.id,
            event_type="page_view",
            session_id="session-other",
            occurred_at=datetime.utcnow(),
        )
        db_session.add_all([event_admin, event_other])
        await db_session.commit()

        # Query summary for admin org (using authenticated client)
        res = await async_client.get("/api/v1/funnel/analytics/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["views"] == 1  # Only admin_org's event is aggregated!

    async def test_analytics_metrics_calculation(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """3. Conversion metrics math is correct (lead conversion, AOV, checkout rate, purchase rate)"""
        # Retrieve organization created by the async_client fixture
        res_org = await db_session.execute(select(Organization))
        org = res_org.scalars().first()

        # Create product
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Book", slug="book",
            price_amount=Decimal("20.00"), currency="USD", status="published"
        )
        db_session.add(prod)
        await db_session.flush()

        # Create analytics events
        # 10 views, 4 leads, 2 checkout starts, 1 purchase
        events = []
        for i in range(10):
            events.append(ConversionEvent(
                organization_id=org.id, event_type="page_view", product_id=prod.id,
                session_id=f"sess-{i}", occurred_at=datetime.utcnow()
            ))
        for i in range(4):
            events.append(ConversionEvent(
                organization_id=org.id, event_type="lead_capture", product_id=prod.id,
                session_id=f"sess-{i}", occurred_at=datetime.utcnow()
            ))
        for i in range(2):
            events.append(ConversionEvent(
                organization_id=org.id, event_type="checkout_start", product_id=prod.id,
                session_id=f"sess-{i}", occurred_at=datetime.utcnow()
            ))
        events.append(ConversionEvent(
            organization_id=org.id, event_type="purchase", product_id=prod.id,
            session_id="sess-0", occurred_at=datetime.utcnow()
        ))
        db_session.add_all(events)

        # Create paid order for revenue calculations
        order = FunnelOrder(
            id=uuid4(), organization_id=org.id, status="paid", 
            subtotal_amount=Decimal("20.00"), total_amount=Decimal("20.00"), currency="USD",
            paid_at=datetime.utcnow()
        )
        db_session.add(order)
        await db_session.flush()

        item = FunnelOrderItem(
            organization_id=org.id, order_id=order.id, product_id=prod.id,
            quantity=1, unit_amount=Decimal("20.00"), total_amount=Decimal("20.00"), currency="USD"
        )
        db_session.add(item)
        await db_session.commit()

        # Query summary
        res = await async_client.get("/api/v1/funnel/analytics/summary")
        assert res.status_code == 200
        data = res.json()

        assert data["views"] == 10
        assert data["leads"] == 4
        assert data["checkout_starts"] == 2
        assert data["purchases"] == 1
        assert data["lead_conversion_rate"] == 40.0  # (4/10)*100
        assert data["checkout_rate"] == 20.0  # (2/10)*100
        assert data["purchase_conversion_rate"] == 10.0  # (1/10)*100
        assert data["checkout_to_purchase_rate"] == 50.0  # (1/2)*100
        assert data["sales_count"] == 1
        assert data["total_revenue"] == 20.0
        assert data["average_order_value"] == 20.0

    async def test_product_specific_analytics(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """4. Product-specific analytics filtering"""
        # Retrieve organization created by the async_client fixture
        res_org = await db_session.execute(select(Organization))
        org = res_org.scalars().first()

        # Create products
        prod1 = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P1", slug="p1",
            price_amount=Decimal("10.00"), currency="USD", status="published"
        )
        prod2 = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P2", slug="p2",
            price_amount=Decimal("50.00"), currency="USD", status="published"
        )
        db_session.add_all([prod1, prod2])
        await db_session.flush()

        # Add events for P1
        db_session.add(ConversionEvent(
            organization_id=org.id, event_type="page_view", product_id=prod1.id, occurred_at=datetime.utcnow()
        ))
        # Add events for P2
        db_session.add(ConversionEvent(
            organization_id=org.id, event_type="page_view", product_id=prod2.id, occurred_at=datetime.utcnow()
        ))
        await db_session.commit()

        # Query summary for P1
        res = await async_client.get(f"/api/v1/funnel/analytics/products/{prod1.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["views"] == 1  # Only P1 view counted!

    async def test_daily_analytics(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """5. Daily activity aggregation is formatted correctly"""
        # Retrieve organization created by the async_client fixture
        res_org = await db_session.execute(select(Organization))
        org = res_org.scalars().first()

        # Add events on two different days
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)

        db_session.add_all([
            ConversionEvent(
                organization_id=org.id, event_type="page_view", occurred_at=today
            ),
            ConversionEvent(
                organization_id=org.id, event_type="page_view", occurred_at=yesterday
            )
        ])
        await db_session.commit()

        # Query daily analytics
        res = await async_client.get("/api/v1/funnel/analytics/daily")
        assert res.status_code == 200
        data = res.json()
        
        # Verify response structure and grouping
        assert len(data) >= 2
        dates = [item["date"] for item in data]
        assert str(yesterday.date()) in dates
        assert str(today.date()) in dates
