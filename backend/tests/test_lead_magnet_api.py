import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import LeadMagnet, DigitalProduct, DeliveryAsset, FunnelOrder, DeliveryAccess
from app.models.contact import Contact
from app.models.organization import Organization
from tests.factories import OrganizationFactory

@pytest.mark.asyncio
class TestLeadMagnetAPI:
    """Test the Lead Magnet and Public Capture API layer."""

    async def test_admin_lead_magnet_crud(self, async_client: AsyncClient, db_session: AsyncSession):
        """1. Admin can create, read, update, list and delete lead magnets within their organization."""
        payload = {
            "name": "Ultimate Guide to AI",
            "slug": "ultimate-guide-ai",
            "promise": "Learn AI in 5 minutes",
            "file_url": "https://example.com/guide.pdf",
            "landing_page_url": "https://example.com/optin"
        }
        
        # Create
        create_res = await async_client.post("/api/v1/funnel/lead-magnets", json=payload)
        assert create_res.status_code == 201, create_res.text
        data = create_res.json()
        assert data["name"] == "Ultimate Guide to AI"
        assert data["slug"] == "ultimate-guide-ai"
        assert data["status"] == "draft"
        lm_id = data["id"]

        # Read (Get)
        get_res = await async_client.get(f"/api/v1/funnel/lead-magnets/{lm_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Ultimate Guide to AI"

        # List
        list_res = await async_client.get("/api/v1/funnel/lead-magnets")
        assert list_res.status_code == 200
        lm_list = list_res.json()
        assert any(lm["id"] == lm_id for lm in lm_list)

        # Update
        update_payload = {
            "name": "Ultimate Guide to AI v2",
            "status": "published"
        }
        update_res = await async_client.put(f"/api/v1/funnel/lead-magnets/{lm_id}", json=update_payload)
        assert update_res.status_code == 200
        assert update_res.json()["name"] == "Ultimate Guide to AI v2"
        assert update_res.json()["status"] == "published"

        # Delete
        delete_res = await async_client.delete(f"/api/v1/funnel/lead-magnets/{lm_id}")
        assert delete_res.status_code == 204

        # Read after delete should be 404
        get_after_delete = await async_client.get(f"/api/v1/funnel/lead-magnets/{lm_id}")
        assert get_after_delete.status_code == 404

    async def test_admin_cross_tenant_isolation(self, async_client: AsyncClient, db_session: AsyncSession):
        """2. Admin cannot access or modify lead magnets owned by another organization."""
        other_org = Organization(
            id=uuid4(),
            name="Other Org",
            slug="other-org",
            status="active"
        )
        db_session.add(other_org)
        await db_session.commit()

        other_lm = LeadMagnet(
            id=uuid4(),
            organization_id=other_org.id,
            name="Other Lead Magnet",
            slug="other-lm",
            status="published",
            opt_in_count=0
        )
        db_session.add(other_lm)
        await db_session.commit()

        # Admin client tries to GET other org's lead magnet
        get_res = await async_client.get(f"/api/v1/funnel/lead-magnets/{other_lm.id}")
        assert get_res.status_code == 404

        # Admin client tries to PUT update other org's lead magnet
        update_res = await async_client.put(
            f"/api/v1/funnel/lead-magnets/{other_lm.id}",
            json={"name": "Hacked Name"}
        )
        assert update_res.status_code == 404

        # Admin client tries to DELETE other org's lead magnet
        delete_res = await async_client.delete(f"/api/v1/funnel/lead-magnets/{other_lm.id}")
        assert delete_res.status_code == 404

    async def test_public_capture_lead_success_with_free_product(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """3. Public lead capture registers contact, opt-in count, zero-dollar order and delivery access."""
        # 1. Setup tenant (Organization)
        org = Organization(
            id=uuid4(),
            name="Public Org",
            slug="public-org",
            status="active"
        )
        db_session.add(org)
        await db_session.flush()

        # 2. Setup Digital Product and Delivery Asset for delivery
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Super Lead Magnet Product",
            slug="super-lm-prod",
            price_amount=Decimal("0.00"),
            currency="USD",
            status="published"
        )
        db_session.add(product)
        await db_session.flush()

        asset = DeliveryAsset(
            id=uuid4(),
            product_id=product.id,
            organization_id=org.id,
            asset_type="file",  # Must be one of valid choice constraints
            title="Super PDF",
            storage_path="/files/super.pdf",
            is_active=True
        )
        db_session.add(asset)
        await db_session.flush()

        # 3. Setup Lead Magnet
        lm = LeadMagnet(
            id=uuid4(),
            organization_id=org.id,
            name="Super Lead Magnet",
            slug="super-lm",
            target_product_id=product.id,
            promise="Get super powers",
            status="published",
            opt_in_count=0
        )
        db_session.add(lm)
        await db_session.commit()

        # 4. Perform Public Capture
        payload = {
            "organization_id": str(org.id),
            "email": "lead@example.com",
            "name": "Super Lead",
            "source": "facebook",
            "medium": "ad",
            "campaign": "launch_2026",
            "referrer": "https://facebook.com/ad"
        }

        # Call public capture route (auth/csrf-exempt)
        response = await public_async_client.post(
            f"/api/v1/public/funnel/lead-magnets/{lm.slug}/capture",
            json=payload
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert "contact_id" in data
        assert data["raw_token"] is not None
        assert data["delivery_url"].startswith("/delivery/")

        # 5. Verify database state
        # Verify Contact created
        stmt = select(Contact).where(Contact.email == "lead@example.com")
        contact_res = await db_session.execute(stmt)
        contact = contact_res.scalar_one()
        assert contact.organization_id == org.id
        assert contact.name == "Super Lead"

        # Verify Lead Magnet opt_in_count incremented
        await db_session.refresh(lm)
        assert lm.opt_in_count == 1

        # Verify zero-dollar FunnelOrder created
        stmt = select(FunnelOrder).where(FunnelOrder.contact_id == contact.id)
        order_res = await db_session.execute(stmt)
        order = order_res.scalar_one()
        assert order.organization_id == org.id
        assert order.status == "paid"
        assert order.total_amount == Decimal("0.00")

        # Verify DeliveryAccess created
        stmt = select(DeliveryAccess).where(DeliveryAccess.order_id == order.id)
        access_res = await db_session.execute(stmt)
        access = access_res.scalar_one()
        assert access.organization_id == org.id
        assert access.product_id == product.id
        assert access.asset_id == asset.id

    async def test_public_capture_lead_idempotent(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """4. Capture lead is idempotent for email: reuse contact but increment opt-in count."""
        org = Organization(id=uuid4(), name="Idempotent Org", slug="idem-org", status="active")
        db_session.add(org)
        await db_session.flush()

        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Gift Product",
            slug="gift-prod",
            price_amount=Decimal("0.00"),
            currency="USD",
            status="published"
        )
        db_session.add(product)
        await db_session.flush()

        asset = DeliveryAsset(
            id=uuid4(),
            product_id=product.id,
            organization_id=org.id,
            asset_type="file",  # Must be one of valid choice constraints
            title="Gift PDF",
            storage_path="/files/gift.pdf",
            is_active=True
        )
        db_session.add(asset)
        await db_session.flush()

        lm = LeadMagnet(
            id=uuid4(),
            organization_id=org.id,
            name="Gift Lead Magnet",
            slug="gift-lm",
            target_product_id=product.id,
            status="published",
            opt_in_count=0
        )
        db_session.add(lm)
        await db_session.commit()

        payload = {
            "organization_id": str(org.id),
            "email": "duplicate@example.com",
            "name": "Dup User"
        }

        # First capture
        res1 = await public_async_client.post(
            f"/api/v1/public/funnel/lead-magnets/{lm.slug}/capture",
            json=payload
        )
        assert res1.status_code == 201
        contact_id1 = res1.json()["contact_id"]
        token1 = res1.json()["raw_token"]

        # Second capture
        res2 = await public_async_client.post(
            f"/api/v1/public/funnel/lead-magnets/{lm.slug}/capture",
            json=payload
        )
        assert res2.status_code == 201
        contact_id2 = res2.json()["contact_id"]
        token2 = res2.json()["raw_token"]

        # Should be same Contact ID
        assert contact_id1 == contact_id2
        # Should generate a new delivery token or the same (service creates a new order/access each time, which is fine)
        assert token2 is not None

        # Verify opt_in_count is 2
        await db_session.refresh(lm)
        assert lm.opt_in_count == 2

        # Verify only one Contact exists in DB
        stmt = select(Contact).where(Contact.email == "duplicate@example.com")
        contacts_res = await db_session.execute(stmt)
        contacts = contacts_res.scalars().all()
        assert len(contacts) == 1

    async def test_public_capture_fails_for_draft_lead_magnet(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """5. Public capture fails if lead magnet is in draft status."""
        org = Organization(id=uuid4(), name="Draft Org", slug="draft-org", status="active")
        db_session.add(org)
        await db_session.flush()

        lm = LeadMagnet(
            id=uuid4(),
            organization_id=org.id,
            name="Draft Lead Magnet",
            slug="draft-lm",
            status="draft",
            opt_in_count=0
        )
        db_session.add(lm)
        await db_session.commit()

        payload = {
            "organization_id": str(org.id),
            "email": "test@example.com"
        }

        response = await public_async_client.post(
            f"/api/v1/public/funnel/lead-magnets/{lm.slug}/capture",
            json=payload
        )
        assert response.status_code == 400
        assert "not published" in response.json()["detail"]
