"""Real isolated SQLite sessions; actual mapping/repository, no app startup/provider."""
import asyncio
import hashlib
import faulthandler
import importlib.util
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects import postgresql

ROOT=Path(__file__).resolve().parents[1]


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


class DurableAttemptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.base=load('_delivery_test_base',ROOT/'app/models/base.py')
        Base=self.base.Base
        # Minimal real FK parents with the production column names/types, not app graph.
        self.org_table=sa.Table('organizations',Base.metadata,sa.Column('id',sa.Uuid,primary_key=True))
        class Order(Base):
            __tablename__='funnel_orders'
            id:Mapped[object]=mapped_column(sa.Uuid,primary_key=True)
            organization_id:Mapped[object]=mapped_column(sa.Uuid,sa.ForeignKey('organizations.id'),nullable=False)
            status:Mapped[str]=mapped_column(sa.String(50),nullable=False)
            customer_email:Mapped[str]=mapped_column(sa.String(255),nullable=False)
            stripe_session_id:Mapped[str|None]=mapped_column(sa.String(255),nullable=True)
            paid_at:Mapped[datetime|None]=mapped_column(sa.DateTime(timezone=True),nullable=True)
        class Access(Base):
            __tablename__='delivery_accesses'
            id:Mapped[object]=mapped_column(sa.Uuid,primary_key=True)
            organization_id:Mapped[object]=mapped_column(sa.Uuid,sa.ForeignKey('organizations.id'),nullable=False)
            order_id:Mapped[object]=mapped_column(sa.Uuid,sa.ForeignKey('funnel_orders.id'),nullable=False)
            status:Mapped[str]=mapped_column(sa.String(50),nullable=False)
        self.Order,self.Access=Order,Access
        with patch.dict(sys.modules,{'_delivery_mapping.base':self.base}):
            # The exact model relative .base resolves inside this isolated package.
            self.model=load('_delivery_mapping.event',ROOT/'app/models/delivery_email_event.py')
        with patch.dict(sys.modules,{'app.models.delivery_email_event':self.model,
                                    'app.models.funnel':SimpleNamespace(FunnelOrder=Order,DeliveryAccess=Access)}):
            self.repo=load('_delivery_attempt_repository',ROOT/'app/services/delivery_email_attempts.py')
        self.temp=tempfile.TemporaryDirectory(prefix='graxia-email-attempt-test-')
        self.engine=create_async_engine('sqlite+aiosqlite:///'+str(Path(self.temp.name)/'attempts.sqlite'))
        @sa.event.listens_for(self.engine.sync_engine,'connect')
        def foreign_keys(connection, _): connection.execute('PRAGMA foreign_keys=ON')
        self.factory=async_sessionmaker(self.engine,expire_on_commit=False)
        self.owner,self.foreign,self.order_id,self.access_id=[uuid4() for _ in range(4)]
        self.paid_at=datetime.now(UTC)-timedelta(days=45)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(self.org_table.insert(),[{'id':self.owner},{'id':self.foreign}])
            await conn.execute(Order.__table__.insert().values(id=self.order_id,organization_id=self.owner,
                status='paid',customer_email='fixture@example.invalid',stripe_session_id='cs_synthetic_delivery',
                paid_at=self.paid_at))
            await conn.execute(Access.__table__.insert().values(id=self.access_id,organization_id=self.owner,
                order_id=self.order_id,status='active'))
        self.store=self.repo.DeliveryEmailAttemptStore(self.factory)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp.cleanup()

    async def claim(self, store=None, owner=None):
        return await (store or self.store).claim(owner or self.owner,self.order_id,
                    'fixture@example.invalid',(self.access_id,))

    async def claim_win_back(self, store=None, owner=None, order_id=None, email='fixture@example.invalid'):
        return await (store or self.store).claim_win_back(
            owner or self.owner,order_id or self.order_id,email)

    async def rows(self):
        async with self.factory() as db:
            return (await db.scalars(sa.select(self.model.DeliveryEmailEvent))).all()

    async def test_concurrent_independent_sessions_acquire_once(self):
        first,second=await asyncio.gather(self.claim(),self.claim(self.repo.DeliveryEmailAttemptStore(self.factory)))
        self.assertEqual(sum(c.acquired for c in (first,second)),1)
        rows=await self.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].status,'pending')
        self.assertEqual(rows[0].idempotency_key,f'funnel_delivery_session:{self.owner}:'+hashlib.sha256(b'cs_synthetic_delivery').hexdigest())

    async def add_order(self, owner=None, paid_at=None, email='fixture@example.invalid'):
        owner=owner or self.owner
        order,access=uuid4(),uuid4()
        async with self.factory() as db:
            db.add(self.Order(id=order,organization_id=owner,status='paid',
                customer_email=email,stripe_session_id='cs_synthetic_delivery',
                paid_at=paid_at or self.paid_at))
            await db.flush()
            db.add(self.Access(id=access,organization_id=owner,order_id=order,status='active'))
            await db.commit()
        return order,access

    async def test_two_orders_same_session_one_provider_and_no_foreign_order_receipt(self):
        order,access=await self.add_order()
        provider=AsyncMock(return_value={'status':'sent','id':'accepted_first_order'})
        async def invoke(order_id,access_id):
            claim=await self.repo.DeliveryEmailAttemptStore(self.factory).claim(
                self.owner,order_id,'fixture@example.invalid',(access_id,))
            if claim.acquired:
                result=await provider()
                await self.store.finish(claim,'sent',result['id'])
            return claim
        claims=await asyncio.gather(invoke(self.order_id,self.access_id),invoke(order,access))
        self.assertEqual(sum(c.acquired for c in claims),1)
        provider.assert_awaited_once()
        loser=next(c for c in claims if not c.acquired)
        self.assertEqual(loser.outcome,'unknown')
        self.assertIsNone(loser.provider_reference)
        repeated=await self.store.claim(self.owner,loser.order_id,'fixture@example.invalid',
            (self.access_id if loser.order_id==self.order_id else access,))
        self.assertFalse(repeated.acquired)
        self.assertEqual(repeated.outcome,'unknown')
        self.assertIsNone(repeated.provider_reference)
        self.assertEqual(len(await self.rows()),1)

    async def test_same_session_different_organizations_independent(self):
        order,access=await self.add_order(self.foreign)
        first,second=await asyncio.gather(self.claim(),self.store.claim(
            self.foreign,order,'fixture@example.invalid',(access,)))
        self.assertTrue(first.acquired and second.acquired)
        self.assertNotEqual(first.key,second.key)

    async def test_missing_or_empty_session_never_claims(self):
        for session in (None,'','   '):
            async with self.factory() as db:
                await db.execute(sa.update(self.Order).values(stripe_session_id=session))
                await db.commit()
            with self.assertRaises(ValueError): await self.claim()
        self.assertEqual(await self.rows(),[])

    async def test_pending_crash_and_unknown_are_never_reacquired(self):
        first=await self.claim()
        restarted=self.repo.DeliveryEmailAttemptStore(self.factory)
        self.assertFalse((await self.claim(restarted)).acquired)
        await self.store.finish(first,'unknown')
        again=await self.claim(restarted)
        self.assertFalse(again.acquired)
        self.assertEqual(again.outcome,'unknown')
        row=(await self.rows())[0]
        self.assertEqual(row.status,'pending')
        self.assertIsNone(row.sent_at)
        self.assertNotIn('provider_reference',row.metadata_json)

    async def test_valid_reference_is_durable_without_reacquisition(self):
        first=await self.claim()
        await self.store.finish(first,'sent','provider_123')
        again=await self.claim(self.repo.DeliveryEmailAttemptStore(self.factory))
        self.assertFalse(again.acquired)
        self.assertEqual((again.outcome,again.provider_reference),('sent','provider_123'))
        row=(await self.rows())[0]
        self.assertIsNotNone(row.sent_at)
        self.assertEqual(row.metadata_json['provider_reference'],'provider_123')

    async def test_missing_reference_and_duplicate_completion_reject(self):
        claim=await self.claim()
        with self.assertRaises(ValueError): await self.store.finish(claim,'sent',None)
        await self.store.finish(claim,'unknown')
        with self.assertRaises(RuntimeError): await self.store.finish(claim,'sent','ref')
        self.assertEqual((await self.rows())[0].status,'pending')

    async def test_suppressed_is_terminal_skipped_not_sent(self):
        claim=await self.claim()
        await self.store.finish(claim,'suppressed')
        again=await self.claim()
        self.assertFalse(again.acquired)
        self.assertEqual(again.outcome,'suppressed')
        row=(await self.rows())[0]
        self.assertEqual(row.status,'skipped')
        self.assertIsNone(row.sent_at)

    async def test_foreign_owner_unpaid_or_revoked_access_cannot_claim(self):
        with self.assertRaises(ValueError): await self.claim(owner=self.foreign)
        async with self.factory() as db:
            await db.execute(sa.update(self.Order).values(status='pending'))
            await db.commit()
        with self.assertRaises(ValueError): await self.claim()
        async with self.factory() as db:
            await db.execute(sa.update(self.Order).values(status='paid'))
            await db.execute(sa.update(self.Access).values(status='revoked'))
            await db.commit()
        with self.assertRaises(ValueError): await self.claim()
        self.assertEqual(await self.rows(),[])

    async def test_unverified_fulfillment_receipt_blocks_resend(self):
        async with self.factory() as db:
            db.add(self.model.DeliveryEmailEvent(organization_id=self.owner,order_id=self.order_id,
                customer_email='fixture@example.invalid',status='sent',provider='resend',
                idempotency_key='historical_fixture',
                metadata_json={'contract':self.repo.CONTRACT,'outcome':'unknown'}))
            await db.commit()
        claim=await self.claim()
        self.assertFalse(claim.acquired)
        self.assertEqual(claim.outcome,'unknown')
        self.assertIsNone(claim.provider_reference)

    async def test_legacy_receipt_without_contract_blocks_fulfillment_resend(self):
        async with self.factory() as db:
            db.add(self.model.DeliveryEmailEvent(organization_id=self.owner,order_id=self.order_id,
                customer_email='fixture@example.invalid',status='sent',provider='resend',
                idempotency_key='legacy_without_contract',metadata_json={}))
            await db.commit()
        claim=await self.claim()
        self.assertFalse(claim.acquired)
        self.assertEqual(claim.outcome,'unknown')
        self.assertIsNone(claim.provider_reference)

    async def test_win_back_receipt_does_not_block_fulfillment_claim(self):
        win_back = await self.claim_win_back()
        fulfillment = await self.claim()
        self.assertTrue(win_back.acquired)
        self.assertTrue(fulfillment.acquired)
        rows = await self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row.metadata_json['contract'] for row in rows},
            {self.repo.CONTRACT, self.repo.WIN_BACK_CONTRACT},
        )

    async def test_win_back_concurrent_claim_and_unknown_outcome_block_retries(self):
        first,second=await asyncio.gather(
            self.claim_win_back(),
            self.claim_win_back(self.repo.DeliveryEmailAttemptStore(self.factory)),
        )
        self.assertEqual(sum(claim.acquired for claim in (first,second)),1)
        claim=first if first.acquired else second
        duplicate=second if first.acquired else first
        self.assertEqual(duplicate.key,claim.key)
        self.assertEqual(duplicate.outcome,'unknown')
        digest=hashlib.sha256(b'fixture@example.invalid').hexdigest()
        self.assertEqual(claim.key,f'win_back:{self.owner}:{digest}:order:{self.order_id}')
        rows=await self.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].status,'pending')
        self.assertEqual(rows[0].metadata_json['outcome'],'pending')
        await self.store.finish_win_back(claim,'unknown')
        retry=await self.claim_win_back(self.repo.DeliveryEmailAttemptStore(self.factory))
        self.assertFalse(retry.acquired)
        self.assertEqual(retry.outcome,'unknown')
        self.assertEqual((await self.rows())[0].status,'pending')

    async def test_win_back_accepted_receipt_starts_new_cycle_only_after_cooldown(self):
        first=await self.claim_win_back()
        self.assertTrue(first.acquired)
        await self.store.finish_win_back(first,'sent','provider_win_back_1')
        cooldown=await self.claim_win_back()
        self.assertFalse(cooldown.acquired)
        self.assertEqual(cooldown.outcome,'sent')
        self.assertEqual(cooldown.provider_reference,'provider_win_back_1')

        old_sent_at=datetime.now(UTC)-timedelta(days=8)
        async with self.factory() as db:
            await db.execute(sa.update(self.model.DeliveryEmailEvent).where(
                self.model.DeliveryEmailEvent.id==first.id).values(sent_at=old_sent_at))
            await db.commit()
        second=await self.claim_win_back()
        self.assertTrue(second.acquired)
        self.assertEqual(second.key,f'win_back:{self.owner}:{first.email_digest}:receipt:{first.id}')
        await self.store.finish_win_back(second,'sent','provider_win_back_2')

        async with self.factory() as db:
            await db.execute(sa.update(self.model.DeliveryEmailEvent).where(
                self.model.DeliveryEmailEvent.id==second.id).values(
                    sent_at=old_sent_at+timedelta(seconds=1)))
            await db.commit()
        third=await self.claim_win_back()
        self.assertTrue(third.acquired)
        self.assertEqual(third.key,f'win_back:{self.owner}:{second.email_digest}:receipt:{second.id}')

    async def test_win_back_definite_suppression_releases_claim(self):
        claim=await self.claim_win_back()
        self.assertTrue(claim.acquired)
        await self.store.finish_win_back(claim,'suppressed')
        self.assertEqual(await self.rows(),[])
        retry=await self.claim_win_back(self.repo.DeliveryEmailAttemptStore(self.factory))
        self.assertTrue(retry.acquired)
        self.assertEqual(retry.key,claim.key)

    async def test_win_back_cycle_is_tenant_scoped_and_latest_order_bound(self):
        foreign_order,_=await self.add_order(owner=self.foreign)
        own=await self.claim_win_back()
        foreign=await self.claim_win_back(owner=self.foreign,order_id=foreign_order)
        self.assertTrue(own.acquired and foreign.acquired)
        self.assertNotEqual(own.key,foreign.key)
        await self.store.finish_win_back(own,'suppressed')

        newer_order,_=await self.add_order(
            paid_at=datetime.now(UTC)-timedelta(days=31),
            email=' FIXTURE@EXAMPLE.INVALID ',
        )
        with self.assertRaises(ValueError):
            await self.claim_win_back(order_id=self.order_id)
        latest=await self.claim_win_back(order_id=newer_order,email='fixture@example.invalid')
        self.assertTrue(latest.acquired)

    def test_mapping_postgres_ddl_matches_migration_contract(self):
        ddl=str(sa.schema.CreateTable(self.model.DeliveryEmailEvent.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn('uq_delivery_email_idempotency',ddl)
        self.assertIn("status IN ('pending', 'sent', 'failed', 'skipped')",ddl)
        self.assertIn('JSONB',ddl)
        self.assertEqual(set(self.model.DeliveryEmailEvent.__table__.c.keys()),{
            'id','organization_id','order_id','delivery_access_id','customer_email','status','provider',
            'idempotency_key','error_code','error_message_redacted','sent_at','metadata_json','created_at'})

    def service_fixture(self, provider):
        helper=load('_delivery_fulfillment_test_helpers',ROOT/'tests/test_fulfillment_email_receipt.py')
        fixture=helper.FulfillmentContracts()
        fixture.setUp()
        fixture.owner,fixture.order_id,fixture.access_id=self.owner,self.order_id,self.access_id
        fixture.order.id=self.order_id
        fixture.order.organization_id=self.owner
        fixture.access.id=self.access_id
        fixture.access.organization_id=self.owner
        fixture.access.order_id=self.order_id
        fixture.reset_rows()
        fixture.service=fixture.module['FunnelDeliveryEmailService'](fixture.db,
            attempt_store=self.repo.DeliveryEmailAttemptStore(self.factory))
        fixture.service.email_service=SimpleNamespace(send_email=provider)
        return fixture

    async def test_two_services_share_durable_claim_and_one_mocked_provider_call(self):
        async def accepted(**kwargs):
            # Independent session observes committed intent before provider invocation.
            rows=await self.rows()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].status,'pending')
            await asyncio.sleep(0.02)
            return {'status':'sent','id':'provider_accepted'}
        provider=AsyncMock(side_effect=accepted)
        first,second=self.service_fixture(provider),self.service_fixture(provider)
        outcomes=await asyncio.gather(first.invoke(),second.invoke())
        self.assertEqual(sum(outcome.status=='sent' for outcome in outcomes),1)
        provider.assert_awaited_once()
        restarted=self.service_fixture(provider)
        outcome=await restarted.invoke()
        self.assertEqual(outcome.status,'sent')
        self.assertEqual(outcome.provider_reference,'provider_accepted')
        provider.assert_awaited_once()

    async def test_transport_unknown_blocks_mocked_provider_after_restart(self):
        provider=AsyncMock(side_effect=TimeoutError('synthetic timeout'))
        first=self.service_fixture(provider)
        self.assertEqual((await first.invoke()).status,'unknown')
        restarted=self.service_fixture(provider)
        self.assertEqual((await restarted.invoke()).status,'unknown')
        provider.assert_awaited_once()
        row=(await self.rows())[0]
        self.assertEqual(row.status,'pending')
        self.assertEqual(row.metadata_json['outcome'],'unknown')
        self.assertIsNone(row.sent_at)


if __name__=='__main__':
    faulthandler.dump_traceback_later(90,exit=True)
    unittest.main()
