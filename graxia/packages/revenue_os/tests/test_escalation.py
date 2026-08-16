"""Escalation bot tests — policy denials become 1-click approvals + replay."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..approvals.escalation import escalate, replay_approved
from ..channels.supplier_pod import SupplierPODAdapter
from ..core.policy_engine import PolicyEngine
from ..enums import ApprovalStatus, AutonomyMode, ProductStatus
from ..models import Approval, Product


async def _product(db_session: AsyncSession, cost=3000) -> Product:
    product = Product(name="Test Product", slug="esc-product",
                      price_cents=9900, status=ProductStatus.PUBLISHED,
                      supplier="printful", supplier_cost_cents=cost, is_physical=True)
    db_session.add(product)
    await db_session.commit()
    return product


@pytest.mark.asyncio
async def test_escalate_creates_pending_approval_and_dedupes(db_session: AsyncSession):
    import uuid
    oid = uuid.uuid4()
    first = await escalate(db_session, "supplier_order", oid, "Needs approval",
                           "margin below cap")
    second = await escalate(db_session, "supplier_order", oid, "Needs approval",
                            "margin below cap")
    assert first is second  # idempotent — one open approval per object
    rows = (await db_session.execute(select(Approval))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_escalate_notifies(db_session: AsyncSession):
    import uuid
    sent = {}

    class _Notifier:
        async def send_message(self, text, **kw):
            sent["text"] = text

    approval = await escalate(db_session, "supplier_order", uuid.uuid4(),
                              "Needs approval", "reason",
                              notifier=_Notifier)
    assert approval is not None
    assert "APPROVAL NEEDED" in sent["text"]
    assert str(approval.id) in sent["text"]


@pytest.mark.asyncio
async def test_supplier_denial_creates_approval(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = await _product(db_session, cost=5000)
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopee", platform_order_id="esc_o1",
        customer_email="c@example.com", product_id=product.id, amount_cents=5000,
    )
    # margin (5000-5000-350)/5000 = -7% < 20% -> policy denies -> escalates
    so = await SupplierPODAdapter(client=object()).submit_order(db_session, order, product)
    assert so is None
    approval = await db_session.scalar(select(Approval).where(
        Approval.object_type == "supplier_order",
        Approval.object_id == order.id))
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_replay_approved_submits_supplier_order(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = await _product(db_session, cost=3000)  # margin 62% -> passes
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopee", platform_order_id="esc_o2",
        customer_email="c@example.com", product_id=product.id, amount_cents=9900,
    )
    approval = await escalate(db_session, "supplier_order", order.id,
                              "Approve?", "passes now")
    result = await replay_approved(db_session, approval)
    assert result["status"] == "submitted"
    # idempotent: replay again returns the same submitted order
    again = await replay_approved(db_session, approval)
    assert again["status"] == "submitted"


@pytest.mark.asyncio
async def test_replay_denied_again_when_policy_still_blocks(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = await _product(db_session, cost=9000)  # margin 9% -> still denies
    db_session.add(product)
    await db_session.commit()
    from ..services.order_service import OrderService
    order = await OrderService.create_order(
        db_session, platform="shopee", platform_order_id="esc_o3",
        customer_email="c@example.com", product_id=product.id, amount_cents=9900,
    )
    approval = await escalate(db_session, "supplier_order", order.id, "Approve?", "x")
    result = await replay_approved(db_session, approval)
    assert result["status"] == "denied_again"
