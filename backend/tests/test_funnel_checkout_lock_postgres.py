"""PostgreSQL process-level proof for checkout-row idempotency locking.

Opt in only with GRAZIA_TEST_POSTGRES_URL pointing at a dedicated loopback
database whose name ends in ``_test``. Each run owns and drops one random schema.
"""

from __future__ import annotations

import asyncio
import ipaddress
import multiprocessing
import os
import queue
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


TEST_DATABASE_URL = os.environ.get("GRAZIA_TEST_POSTGRES_URL", "").strip()
CHECKOUT_PARENT_READY_TIMEOUT_SECONDS = 75
CHECKOUT_WORKER_START_BARRIER_SECONDS = 90


def _validate_test_url(raw_url: str):
    try:
        url = make_url(raw_url)
        host = url.host
        database = url.database or ""
        if host == "localhost":
            is_loopback = True
        else:
            is_loopback = bool(host and ipaddress.ip_address(host).is_loopback)
    except Exception as exc:
        raise ValueError("GRAZIA_TEST_POSTGRES_URL is malformed or not loopback") from exc

    if url.drivername != "postgresql+asyncpg" or not is_loopback or not database.endswith("_test"):
        raise ValueError("PostgreSQL proof requires asyncpg, loopback, and a database ending _test")
    return url


def _process_checkout(
    database_url: str,
    schema: str,
    organization_id: str,
    product_id: str,
    checkout_id: str,
    stripe_session_id: str,
    start_event,
    result_queue,
) -> None:
    try:
        asyncio.run(
            _async_process_checkout(
                database_url,
                schema,
                organization_id,
                product_id,
                checkout_id,
                stripe_session_id,
                start_event,
                result_queue,
            )
        )
    except BaseException as exc:  # child failures are returned without secrets
        result_queue.put(("error", type(exc).__name__))


async def _async_process_checkout(
    database_url: str,
    schema: str,
    organization_id: str,
    product_id: str,
    checkout_id: str,
    stripe_session_id: str,
    start_event,
    result_queue,
) -> None:
    from unittest.mock import AsyncMock, patch

    from app.config import settings
    from app.services.funnel_delivery_email_service import DeliveryEmailOutcome
    from app.services.funnel_delivery_service import FunnelDeliveryService
    from app.services.funnel_order_service import FunnelOrderService

    settings.CELERY_BROKER_URL = ""
    settings.REDIS_URL = ""
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            result_queue.put(("ready", backend_pid))
            if not start_event.wait(CHECKOUT_WORKER_START_BARRIER_SECONDS):
                raise TimeoutError("concurrency start barrier timed out")

            original_grant = FunnelDeliveryService.grant_delivery_access_for_order

            async def delayed_grant(service, *args, **kwargs):
                # Keep the first transaction inside the lock long enough for
                # the other process to block on the same persisted checkout.
                await asyncio.sleep(0.4)
                return await original_grant(service, *args, **kwargs)

            with patch(
                "app.services.funnel_delivery_service.FunnelDeliveryService.grant_delivery_access_for_order",
                delayed_grant,
            ), patch(
                "app.services.funnel_delivery_email_service.FunnelDeliveryEmailService.send_delivery_links",
                new_callable=AsyncMock,
                return_value=DeliveryEmailOutcome("suppressed"),
            ), patch(
                "app.services.automation_email_service.AutomationEmailService.trigger_post_purchase",
                new_callable=AsyncMock,
            ):
                order = await FunnelOrderService(session).create_order_from_checkout_completed(
                    {
                        "id": stripe_session_id,
                        "customer_details": {"email": "fixture@example.invalid"},
                        "metadata": {
                            "organization_id": organization_id,
                            "product_id": product_id,
                            "funnel_checkout_session_id": checkout_id,
                        },
                    }
                )
            result_queue.put(("result", str(order.id) if order else None))
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="GRAZIA_TEST_POSTGRES_URL is unset")
def test_postgres_checkout_lock_serializes_separate_processes():
    asyncio.run(_test_postgres_checkout_lock_serializes_separate_processes())


async def _test_postgres_checkout_lock_serializes_separate_processes() -> None:
    from app.models.base import Base
    from app.models.funnel import (
        ConversionEvent,
        DeliveryAccess,
        DeliveryAsset,
        DigitalProduct,
        FunnelCheckoutSession,
        FunnelOrder,
        FunnelOrderItem,
    )

    url = _validate_test_url(TEST_DATABASE_URL)
    schema = f"graxia_checkout_race_{uuid4().hex}"
    organization_id = uuid4()
    product_id = uuid4()
    checkout_id = uuid4()
    stripe_session_id = f"cs_race_{uuid4().hex}"
    bootstrap_engine = create_async_engine(url, poolclass=NullPool)
    test_engine = None
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        test_engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with test_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE organizations (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE contacts (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE users (id UUID PRIMARY KEY)"))

            selected_tables = [
                DigitalProduct.__table__,
                DeliveryAsset.__table__,
                FunnelCheckoutSession.__table__,
                FunnelOrder.__table__,
                FunnelOrderItem.__table__,
                DeliveryAccess.__table__,
                ConversionEvent.__table__,
            ]
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=selected_tables,
                    checkfirst=True,
                )
            )
            await connection.execute(
                text("INSERT INTO organizations (id) VALUES (:organization_id)"),
                {"organization_id": organization_id},
            )

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as session:
            session.add(
                DigitalProduct(
                    id=product_id,
                    organization_id=organization_id,
                    name="Concurrency fixture",
                    slug=f"checkout-race-{uuid4().hex}",
                    price_amount=Decimal("1.00"),
                    currency="THB",
                    status="published",
                )
            )
            session.add(
                FunnelCheckoutSession(
                    id=checkout_id,
                    organization_id=organization_id,
                    product_id=product_id,
                    stripe_session_id=stripe_session_id,
                    status="pending",
                    amount=Decimal("1.00"),
                    currency="THB",
                )
            )
            await session.commit()

        process_context = multiprocessing.get_context("spawn")
        start_event = process_context.Event()
        result_queue = process_context.Queue()
        processes = [
            process_context.Process(
                target=_process_checkout,
                args=(
                    TEST_DATABASE_URL,
                    schema,
                    str(organization_id),
                    str(product_id),
                    str(checkout_id),
                    stripe_session_id,
                    start_event,
                    result_queue,
                ),
            )
            for _ in range(2)
        ]
        try:
            for process in processes:
                process.start()

            ready_pids: set[int] = set()
            deadline = time.monotonic() + CHECKOUT_PARENT_READY_TIMEOUT_SECONDS
            while len(ready_pids) < 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError("PostgreSQL workers did not reach start barrier")
                try:
                    kind, value = result_queue.get(timeout=remaining)
                except queue.Empty as exc:
                    raise AssertionError("PostgreSQL workers did not reach start barrier") from exc
                if kind == "error":
                    raise AssertionError(f"PostgreSQL worker failed before barrier: {value}")
                assert kind == "ready"
                ready_pids.add(value)

            assert len(ready_pids) == 2
            start_event.set()
            order_ids: list[str | None] = []
            deadline = time.monotonic() + 45
            while len(order_ids) < 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError("PostgreSQL checkout workers timed out")
                try:
                    kind, value = result_queue.get(timeout=remaining)
                except queue.Empty as exc:
                    raise AssertionError("PostgreSQL checkout workers timed out") from exc
                if kind == "error":
                    raise AssertionError(f"PostgreSQL worker failed: {value}")
                assert kind == "result"
                order_ids.append(value)

            for process in processes:
                process.join(timeout=10)
                assert process.exitcode == 0
            assert order_ids[0] is not None
            assert order_ids[0] == order_ids[1]

            async with session_factory() as session:
                assert await session.scalar(
                    text("SELECT count(*) FROM funnel_orders WHERE checkout_session_id = :checkout_id"),
                    {"checkout_id": checkout_id},
                ) == 1
                assert await session.scalar(
                    text("SELECT count(*) FROM funnel_order_items")
                ) == 1
        finally:
            start_event.set()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
            result_queue.close()
            result_queue.join_thread()
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="GRAZIA_TEST_POSTGRES_URL is unset")
def test_postgres_win_back_claim_commits_once_before_provider_work():
    asyncio.run(_test_postgres_win_back_claim_commits_once_before_provider_work())


async def _test_postgres_win_back_claim_commits_once_before_provider_work() -> None:
    from app.models.base import Base
    from app.models.delivery_email_event import DeliveryEmailEvent
    from app.services.delivery_email_attempts import DeliveryEmailAttemptStore

    url = _validate_test_url(TEST_DATABASE_URL)
    schema = f"graxia_win_back_claim_{uuid4().hex}"
    organization_id = uuid4()
    order_id = uuid4()
    email = "win-back-race@example.invalid"
    bootstrap_engine = create_async_engine(url, poolclass=NullPool)
    test_engine = None
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        test_engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with test_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE organizations (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE contacts (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE users (id UUID PRIMARY KEY)"))
            await connection.execute(text(
                "CREATE TABLE funnel_orders ("
                "id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id), "
                "status VARCHAR(50) NOT NULL, subtotal_amount NUMERIC(12,2) NOT NULL, "
                "total_amount NUMERIC(12,2) NOT NULL, currency VARCHAR(10) NOT NULL, "
                "customer_email VARCHAR(255), paid_at TIMESTAMPTZ)"
            ))
            await connection.execute(text(
                "CREATE TABLE delivery_accesses ("
                "id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES funnel_orders(id))"
            ))
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[DeliveryEmailEvent.__table__],
                    checkfirst=True,
                )
            )
            await connection.execute(
                text("INSERT INTO organizations (id) VALUES (:organization_id)"),
                {"organization_id": organization_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO funnel_orders (id, organization_id, status, subtotal_amount, "
                    "total_amount, currency, customer_email, paid_at) VALUES "
                    "(:order_id, :organization_id, 'paid', 1.00, 1.00, 'THB', :email, :paid_at)"
                ),
                {
                    "order_id": order_id,
                    "organization_id": organization_id,
                    "email": email,
                    "paid_at": datetime.now(UTC) - timedelta(days=45),
                },
            )

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        stores = [DeliveryEmailAttemptStore(session_factory) for _ in range(2)]
        claims = await asyncio.gather(*(
            store.claim_win_back(organization_id, order_id, email)
            for store in stores
        ))
        assert sum(claim.acquired for claim in claims) == 1
        async with session_factory() as session:
            rows = (await session.scalars(
                select(DeliveryEmailEvent).where(
                    DeliveryEmailEvent.organization_id == organization_id,
                    DeliveryEmailEvent.order_id == order_id,
                )
            )).all()
            assert len(rows) == 1
            assert rows[0].status == "pending"
            assert rows[0].metadata_json["outcome"] == "pending"
            assert rows[0].metadata_json["contract"] == "win-back-email-v1"
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="GRAZIA_TEST_POSTGRES_URL is unset")
def test_postgres_delivery_grant_lock_serializes_separate_sessions():
    asyncio.run(_test_postgres_delivery_grant_lock_serializes_separate_sessions())


async def _test_postgres_delivery_grant_lock_serializes_separate_sessions() -> None:
    from app.models.base import Base
    from app.models.funnel import (
        DeliveryAccess,
        DeliveryAsset,
        DigitalProduct,
        FunnelCheckoutSession,
        FunnelOrder,
        FunnelOrderItem,
    )
    from app.services.funnel_delivery_service import FunnelDeliveryService

    url = _validate_test_url(TEST_DATABASE_URL)
    schema = f"graxia_delivery_grant_race_{uuid4().hex}"
    organization_id = uuid4()
    product_id = uuid4()
    asset_id = uuid4()
    order_id = uuid4()
    bootstrap_engine = create_async_engine(url, poolclass=NullPool)
    test_engine = None
    sessions = []
    second_task = None
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        test_engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with test_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE organizations (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE contacts (id UUID PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE users (id UUID PRIMARY KEY)"))
            selected_tables = [
                DigitalProduct.__table__,
                DeliveryAsset.__table__,
                FunnelCheckoutSession.__table__,
                FunnelOrder.__table__,
                FunnelOrderItem.__table__,
                DeliveryAccess.__table__,
            ]
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=selected_tables,
                    checkfirst=True,
                )
            )
            await connection.execute(
                text("INSERT INTO organizations (id) VALUES (:organization_id)"),
                {"organization_id": organization_id},
            )

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as seed_session:
            seed_session.add(
                DigitalProduct(
                    id=product_id,
                    organization_id=organization_id,
                    name="Delivery lock fixture",
                    slug=f"delivery-lock-{uuid4().hex}",
                    price_amount=Decimal("1.00"),
                    currency="THB",
                    status="published",
                )
            )
            seed_session.add(
                DeliveryAsset(
                    id=asset_id,
                    organization_id=organization_id,
                    product_id=product_id,
                    asset_type="text",
                    title="Delivery lock asset",
                    content_body="fixture",
                    is_active=True,
                )
            )
            seed_session.add(
                FunnelOrder(
                    id=order_id,
                    organization_id=organization_id,
                    status="paid",
                    subtotal_amount=Decimal("1.00"),
                    total_amount=Decimal("1.00"),
                    currency="THB",
                )
            )
            seed_session.add(
                FunnelOrderItem(
                    organization_id=organization_id,
                    order_id=order_id,
                    product_id=product_id,
                    quantity=1,
                    unit_amount=Decimal("1.00"),
                    total_amount=Decimal("1.00"),
                    currency="THB",
                )
            )
            await seed_session.commit()

        first = session_factory()
        second = session_factory()
        monitor = session_factory()
        sessions.extend([first, second, monitor])
        first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))

        first_grants = await FunnelDeliveryService(first).grant_delivery_access_for_order(
            organization_id, order_id, commit=False
        )
        assert len(first_grants) == 1
        assert first_grants[0][0].access_token_hash is not None

        second_task = asyncio.create_task(
            FunnelDeliveryService(second).grant_delivery_access_for_order(
                organization_id, order_id, commit=False
            )
        )
        deadline = time.monotonic() + 5
        blocked_by_first = False
        while time.monotonic() < deadline:
            blockers = await monitor.scalar(
                text("SELECT pg_blocking_pids(:backend_pid)"),
                {"backend_pid": second_pid},
            )
            if first_pid in blockers:
                blocked_by_first = True
                break
            if second_task.done():
                break
            await asyncio.sleep(0.05)

        assert blocked_by_first, "second grant did not block on the persisted order row"

        await first.commit()
        second_grants = await asyncio.wait_for(second_task, timeout=10)
        await second.commit()
        assert second_grants == []

        active_access_count = await monitor.scalar(
            text(
                "SELECT count(*) FROM delivery_accesses "
                "WHERE order_id = :order_id AND status = 'active' "
                "AND (asset_id = :asset_id OR delivery_asset_id = :asset_id)"
            ),
            {"order_id": order_id, "asset_id": asset_id},
        )
        active_token_count = await monitor.scalar(
            text(
                "SELECT count(access_token_hash) FROM delivery_accesses "
                "WHERE order_id = :order_id AND status = 'active' "
                "AND (asset_id = :asset_id OR delivery_asset_id = :asset_id)"
            ),
            {"order_id": order_id, "asset_id": asset_id},
        )
        assert active_access_count == 1
        assert active_token_count == 1

        async def assert_other_session_can_lock(order_id: UUID) -> None:
            acquired_order_id = await asyncio.wait_for(
                second.scalar(
                    text("SELECT id FROM funnel_orders WHERE id = :order_id FOR UPDATE"),
                    {"order_id": order_id},
                ),
                timeout=2,
            )
            assert acquired_order_id == order_id

        # A duplicate grant with the default commit setting must release its
        # order lock before returning, while leaving the existing access intact.
        await second.scalar(text("SELECT pg_backend_pid()"))
        duplicate_grants = await FunnelDeliveryService(
            first
        ).grant_delivery_access_for_order(organization_id, order_id)
        assert duplicate_grants == []
        await assert_other_session_can_lock(order_id)
        duplicate_access_count = await second.scalar(
            text(
                "SELECT count(*) FROM delivery_accesses "
                "WHERE order_id = :order_id AND status = 'active' "
                "AND (asset_id = :asset_id OR delivery_asset_id = :asset_id)"
            ),
            {"order_id": order_id, "asset_id": asset_id},
        )
        assert duplicate_access_count == 1
        await second.rollback()

        # Unpaid orders also take the row lock before their successful early
        # return, so the default commit must release that lock as well.
        await second.scalar(text("SELECT pg_backend_pid()"))
        unpaid_order_id = uuid4()
        first.add(
            FunnelOrder(
                id=unpaid_order_id,
                organization_id=organization_id,
                status="pending",
                subtotal_amount=Decimal("1.00"),
                total_amount=Decimal("1.00"),
                currency="THB",
            )
        )
        await first.commit()
        unpaid_grants = await FunnelDeliveryService(
            first
        ).grant_delivery_access_for_order(organization_id, unpaid_order_id)
        assert unpaid_grants == []
        await assert_other_session_can_lock(unpaid_order_id)
        await second.rollback()
    finally:
        if sessions:
            await sessions[0].rollback()
        if second_task is not None and not second_task.done():
            try:
                await asyncio.wait_for(second_task, timeout=10)
            except Exception:
                second_task.cancel()
                await asyncio.gather(second_task, return_exceptions=True)
        for session in sessions:
            await session.close()
        if test_engine is not None:
            await test_engine.dispose()
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()
