"""Tests for MCP read-only tools — system and funnel tools."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from uuid import UUID, uuid4

import app.mcp.tools  # noqa: F401
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse
from app.database import AsyncSessionLocal
from tests.factories import OrganizationFactory


TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def setup_data(db_session):
    """Seed test organization, product, and asset for MCP tool tests."""
    from app.models.funnel import DigitalProduct, DeliveryAsset, LeadMagnet

    org = await OrganizationFactory.build(db_session, id=TEST_ORG_ID)

    product = DigitalProduct(
        id=uuid4(),
        organization_id=TEST_ORG_ID,
        name="MCP Test Product",
        slug=f"mcp-test-{uuid4().hex[:8]}",
        description="A test product for MCP",
        price_amount=999.00,
        currency="THB",
        status="published",
        product_type="ebook",
    )
    db_session.add(product)

    asset = DeliveryAsset(
        id=uuid4(),
        organization_id=TEST_ORG_ID,
        product_id=product.id,
        asset_type="file",
        title="Test Asset",
        is_active=True,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(product)
    await db_session.refresh(asset)

    yield

    # Cleanup
    await db_session.execute(DigitalProduct.__table__.delete().where(DigitalProduct.organization_id == TEST_ORG_ID))
    await db_session.execute(DeliveryAsset.__table__.delete().where(DeliveryAsset.organization_id == TEST_ORG_ID))
    await db_session.execute(LeadMagnet.__table__.delete().where(LeadMagnet.organization_id == TEST_ORG_ID))
    await db_session.commit()


# ── System Tool Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSystemTools:
    async def test_get_system_status(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool("get_system_status", {}, auth=auth)
        assert resp.ok is True
        assert resp.data["status"] == "operational"
        assert resp.data["version"] == "3.0.0"

    async def test_get_latest_test_status(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool("get_latest_test_status", {}, auth=auth)
        assert resp.ok is True
        assert resp.data["has_test_suite"] is True
        assert resp.data["test_count"] > 0

    async def test_get_token_optimizer_status(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool("get_token_optimizer_status", {}, auth=auth)
        assert resp.ok is True
        assert resp.data["available"] is False

    async def test_get_funnel_phase_status(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool("get_funnel_phase_status", {}, auth=auth)
        assert resp.ok is True
        assert resp.data["status"] == "LOCAL_FUNNEL_READY"


# ── Funnel Tool Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFunnelTools:
    async def test_list_products_with_data(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "list_products",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] > 0

    async def test_list_products_empty_org(self):
        auth = MCPAuthContext.system(organization_id=OTHER_ORG_ID)
        resp = await mcp_registry.call_tool(
            "list_products",
            {"organization_id": str(OTHER_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] == 0

    async def test_get_product_found(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        list_resp = await mcp_registry.call_tool(
            "list_products",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert list_resp.ok is True
        assert list_resp.data["total"] > 0
        product_id = list_resp.data["items"][0]["id"]

        resp = await mcp_registry.call_tool(
            "get_product",
            {"organization_id": str(TEST_ORG_ID), "product_id": product_id},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["name"] == "MCP Test Product"

    async def test_get_product_not_found(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_product",
            {"organization_id": str(TEST_ORG_ID), "product_id": str(uuid4())},
            auth=auth,
        )
        assert resp.ok is False

    async def test_list_delivery_assets(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "list_delivery_assets",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] >= 1

    async def test_get_orders_summary(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_orders_summary",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert "total_orders" in resp.data
        assert "total_revenue" in resp.data

    async def test_get_recent_orders(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_recent_orders",
            {"organization_id": str(TEST_ORG_ID), "limit": 5},
            auth=auth,
        )
        assert resp.ok is True

    async def test_get_revenue_summary(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_revenue_summary",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["currency"] == "THB"

    async def test_get_conversion_summary(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_conversion_summary",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert "conversion_rate" in resp.data

    async def test_get_checkout_abandonment(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_checkout_abandonment",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert "checkout_abandonment_rate" in resp.data

    async def test_get_delivery_open_rate(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_delivery_open_rate",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert "delivery_open_rate" in resp.data

    async def test_get_pending_approvals(self):
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool(
            "get_pending_approvals",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert "items" in resp.data

    # ── Cross-org safety ──────────────────────────────────────────────

    async def test_cross_org_blocked(self):
        """Tools should return NOT_FOUND for cross-org access."""
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        list_resp = await mcp_registry.call_tool(
            "list_products",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert list_resp.ok is True
        if list_resp.data["total"] > 0:
            product_id = list_resp.data["items"][0]["id"]
            other_auth = MCPAuthContext.system(organization_id=OTHER_ORG_ID)
            resp = await mcp_registry.call_tool(
                "get_product",
                {
                    "organization_id": str(OTHER_ORG_ID),
                    "product_id": product_id,
                },
                auth=other_auth,
            )
            assert resp.ok is False

    # ── Invalid params ─────────────────────────────────────────────────

    async def test_invalid_org_id(self):
        auth = MCPAuthContext.system()
        resp = await mcp_registry.call_tool(
            "list_products",
            {"organization_id": "not-a-uuid"},
            auth=auth,
        )
        assert resp.ok is False
        assert resp.error.code == "INVALID_PARAMS"

    async def test_missing_required_params(self):
        """Calling get_product without required params should fail."""
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        resp = await mcp_registry.call_tool("get_product", {}, auth=auth)
        assert resp.ok is False
