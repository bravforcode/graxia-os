"""Actual fulfillment source with controlled provider/SQL mocks; no app startup."""
import ast
import logging
import re
import sys
import unittest
from datetime import datetime, UTC
from pathlib import Path
from types import SimpleNamespace
from typing import List, Tuple, Optional, Literal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]


class Column:
    def __eq__(self, other): return ('eq', other)
    def is_(self, other): return ('is', other)


class Query:
    def where(self, *args): return self
    def limit(self, *args): return self
    def with_for_update(self, *args, **kwargs): return self


def model(*columns):
    def init(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = kwargs.get('id', uuid4())
    return type('FixtureRow', (), dict(__init__=init, **{col: Column() for col in columns}))


def load_service(filename, globals_):
    tree = ast.parse((ROOT / 'app/services' / filename).read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, filename, 'exec'), globals_)
    return globals_


class FulfillmentContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.owner, self.order_id, self.product_id, self.access_id = [uuid4() for _ in range(4)]
        self.order = SimpleNamespace(id=self.order_id, organization_id=self.owner,
            status='paid', customer_email='fixture@example.invalid', contact_id=None)
        self.access = SimpleNamespace(id=self.access_id, organization_id=self.owner,
            order_id=self.order_id, product_id=self.product_id, status='active', expires_at=None)
        self.provider = AsyncMock(return_value={'status':'sent', 'id':'provider_123'})
        self.attempts = SimpleNamespace(claim=AsyncMock(return_value=SimpleNamespace(
            acquired=True,outcome='unknown',provider_reference=None)),finish=AsyncMock())
        self.db = SimpleNamespace(execute=AsyncMock(), get=AsyncMock(return_value=self.access))
        self.reset_rows()
        self.globals = dict(__name__=__name__, logging=logging, UUID=UUID, datetime=datetime,
            UTC=UTC, List=List, Tuple=Tuple, Optional=Optional, Literal=Literal,
            dataclass=dataclass, re=re, AsyncSession=object, select=lambda *args: Query(),
            settings=SimpleNamespace(FRONTEND_URL='https://fixture.invalid'),
            email_service=SimpleNamespace(send_email=self.provider),
            DeliveryEmailAttemptStore=lambda: self.attempts,
            DeliveryAccess=model('id','organization_id','order_id','status'),
            DigitalProduct=model('id','name','organization_id'),
            FunnelOrder=model('id','organization_id','status'),
            Contact=model('id','organization_id','email','is_deleted'))
        # Same acceptance predicate as production, extracted without provider/settings imports.
        tree = ast.parse((ROOT / 'app/services/email_service.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'email_accepted')
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'email_service.py', 'exec'), self.globals)
        self.module = load_service('funnel_delivery_email_service.py', self.globals)
        self.service = self.module['FunnelDeliveryEmailService'](self.db)
        self.service.sent_emails.clear()

    def reset_rows(self):
        self.db.execute.side_effect = [SimpleNamespace(scalar_one_or_none=lambda: self.order),
                                      SimpleNamespace(scalar_one_or_none=lambda: 'Synthetic product')]

    async def invoke(self, accesses=None):
        return await self.service.send_delivery_links(self.owner,self.order_id,self.order.customer_email,
            [(self.access,'synthetic_token')] if accesses is None else accesses)

    async def test_verified_provider_reference_marks_sent(self):
        result = await self.invoke()
        self.assertEqual(result.status, 'sent')
        self.assertEqual(result.provider_reference, 'provider_123')
        self.assertEqual(len(self.service.sent_emails), 1)
        self.provider.assert_awaited_once()

    async def test_ambiguous_provider_response_never_marks_sent(self):
        for response in ({'status':'sent'}, {'status':'sent','id':''},
                         {'status':'sent','id':'invalid id'}, {'status':'sent','id':'ref','error':'failed'}):
            with self.subTest(response=response):
                self.reset_rows(); self.provider.return_value=response
                result=await self.invoke()
                self.assertEqual(result.status,'unknown')
                self.assertIsNone(result.provider_reference)
        self.assertEqual(self.service.sent_emails, [])

    async def test_failed_suppressed_logged_skipped_and_exception_not_sent(self):
        for response, expected in (({'status':'failed'},'unknown'), ({'status':'suppressed'},'suppressed'),
                                   ({'status':'logged'},'suppressed'), ({'status':'skipped'},'suppressed')):
            self.reset_rows(); self.provider.return_value=response
            result=await self.invoke()
            self.assertEqual(result.status,expected)
            self.assertIsNone(result.provider_reference)
        self.reset_rows(); self.provider.side_effect=RuntimeError('private provider message')
        result=await self.invoke()
        self.assertEqual(result.status,'unknown')
        self.assertEqual(self.service.sent_emails,[])

    async def test_adapter_transport_errors_remain_unknown_without_retry(self):
        for error in ('TimeoutError','RuntimeError','ConnectionError'):
            with self.subTest(error=error):
                self.reset_rows(); self.provider.reset_mock()
                self.provider.return_value={'status':'failed','error':error}
                result=await self.invoke()
                self.assertEqual(result.status,'unknown')
                self.assertIsNone(result.provider_reference)
                self.provider.assert_awaited_once()
                self.assertEqual(self.service.sent_emails,[])
        for response in ({'status':'suppressed','error':'TimeoutError'},
                         {'status':'sent','id':'provider_ref','error':'ConnectionError'}):
            self.reset_rows(); self.provider.reset_mock(); self.provider.return_value=response
            result=await self.invoke()
            self.assertEqual(result.status,'unknown')
            self.assertIsNone(result.provider_reference)
            self.provider.assert_awaited_once()
        for exception in (TimeoutError('synthetic timeout'),RuntimeError('synthetic exception')):
            self.reset_rows(); self.provider.reset_mock(); self.provider.side_effect=exception
            result=await self.invoke()
            self.assertEqual(result.status,'unknown')
            self.assertIsNone(result.provider_reference)
            self.provider.assert_awaited_once()
        self.assertEqual(self.service.sent_emails,[])

    async def test_provider_requires_committed_intent_and_duplicate_never_resends(self):
        async def accepted(**kwargs):
            self.attempts.claim.assert_awaited_once()
            return {'status':'sent','id':'provider_ref'}
        self.provider.side_effect=accepted
        result=await self.invoke()
        self.assertEqual(result.status,'sent')
        self.attempts.finish.assert_awaited_once()
        self.attempts.claim.return_value=SimpleNamespace(acquired=False,outcome='unknown',provider_reference=None)
        self.reset_rows()
        result=await self.invoke()
        self.assertEqual(result.status,'unknown')
        self.provider.assert_awaited_once()

    async def test_claim_failure_or_receipt_commit_unknown_cannot_mark_sent(self):
        self.attempts.claim.side_effect=RuntimeError('synthetic missing schema')
        result=await self.invoke()
        self.assertEqual(result.status,'unknown')
        self.provider.assert_not_awaited()
        self.attempts.claim.side_effect=None
        self.attempts.finish.side_effect=RuntimeError('synthetic uncertain commit')
        self.reset_rows()
        result=await self.invoke()
        self.assertEqual(result.status,'unknown')
        self.assertIsNone(result.provider_reference)
        self.assertEqual(self.service.sent_emails,[])
        self.provider.assert_awaited_once()

    async def test_empty_access_is_suppressed_without_provider(self):
        result=await self.invoke([])
        self.assertEqual(result.status,'suppressed')
        self.provider.assert_not_awaited()

    async def test_unpaid_or_foreign_order_is_suppressed_without_provider(self):
        for name, value in (('status','pending'),('organization_id',uuid4())):
            original=getattr(self.order,name); setattr(self.order,name,value)
            self.reset_rows()
            result=await self.invoke()
            self.assertEqual(result.status,'suppressed')
            setattr(self.order,name,original)
        self.provider.assert_not_awaited()

    async def test_foreign_access_is_suppressed_without_provider(self):
        self.access.organization_id=uuid4()
        result=await self.invoke()
        self.assertEqual(result.status,'suppressed')
        self.provider.assert_not_awaited()

    async def test_order_caller_propagates_actual_outcome_and_does_not_retry(self):
        outcomes = [self.module['DeliveryEmailOutcome'](status=s, provider_reference='ref' if s=='sent' else None)
                    for s in ('sent','failed','suppressed','unknown')]
        for outcome in outcomes:
            with self.subTest(status=outcome.status):
                sender=AsyncMock(return_value=outcome)
                fake_email=SimpleNamespace(FunnelDeliveryEmailService=lambda db: SimpleNamespace(send_delivery_links=sender),
                                           DeliveryEmailOutcome=self.module['DeliveryEmailOutcome'])
                checkout=SimpleNamespace(amount=10,currency='THB',customer_email='fixture@example.invalid',
                                         metadata_json={},contact_id=None,stripe_session_id='synthetic_checkout',
                                         product_id=self.product_id)
                no_existing_orders=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[]))
                results=[SimpleNamespace(scalar_one_or_none=lambda:checkout),no_existing_orders,
                         SimpleNamespace(scalar_one_or_none=lambda:SimpleNamespace(id=self.product_id))]
                db=SimpleNamespace(execute=AsyncMock(side_effect=results),
                    add=lambda row:None,flush=AsyncMock(),commit=AsyncMock(),refresh=AsyncMock())
                ns=dict(self.globals, and_=lambda *args:args, or_=lambda *args:args,
                    FunnelOrder=model('id','organization_id','checkout_session_id','stripe_session_id'),
                    FunnelCheckoutSession=model('id','organization_id'), FunnelOrderItem=model(),
                    FunnelDeliveryService=lambda db:SimpleNamespace(grant_delivery_access_for_order=AsyncMock(return_value=[])),
                    FunnelAnalyticsService=lambda db:SimpleNamespace(log_event=AsyncMock()),
                    AutomationEmailService=lambda db:SimpleNamespace(trigger_post_purchase=AsyncMock()),
                    settings=SimpleNamespace(CELERY_BROKER_URL='',REDIS_URL=''))
                load_service('funnel_order_service.py',ns)
                with patch.dict(sys.modules, {'app.services.funnel_delivery_email_service':fake_email}):
                    svc=ns['FunnelOrderService'](db)
                    order=await svc.create_order_from_checkout_completed({'id':'synthetic_checkout',
                        'metadata':{'organization_id':str(self.owner),'product_id':str(self.product_id),
                                    'funnel_checkout_session_id':str(uuid4())}})
                self.assertEqual(order.delivery_email_result,outcome)
                self.assertEqual(svc.delivery_email_result,outcome)
                sender.assert_awaited_once()

    async def test_webhook_exposes_typed_outcome_and_rejects_untyped_sent(self):
        tree=ast.parse((ROOT/'app/api/funnel_webhooks.py').read_text(encoding='utf-8'))
        fn=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef)
                and node.name=='stripe_funnel_webhook')
        fn.decorator_list=[]
        event={'type':'checkout.session.completed','data':{'object':{'id':'synthetic_checkout'}}}
        ns=dict(self.globals, Request=object,FunnelOrderService=object,
                Depends=lambda fn:None,get_order_service=object,
                stripe=SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda *args:event),
                                       error=SimpleNamespace(SignatureVerificationError=RuntimeError)),
                _forward_to_revenue_os=AsyncMock(),logger=logging.getLogger('offline-webhook'),
                settings=SimpleNamespace(STRIPE_WEBHOOK_SECRET='synthetic-only'))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'funnel_webhooks.py','exec'),ns)
        cls=self.module['DeliveryEmailOutcome']
        for outcome in (cls('sent','provider_ref'),cls('failed'),cls('suppressed'),cls('unknown'),
                        {'status':'sent','provider_reference':'forged'}, None):
            with self.subTest(outcome=outcome):
                order=SimpleNamespace(id=self.order_id,delivery_email_result=outcome)
                service=SimpleNamespace(create_order_from_checkout_completed=AsyncMock(return_value=order))
                request=SimpleNamespace(body=AsyncMock(return_value=b'synthetic'),headers={})
                with patch.dict(sys.modules,{'app.services.funnel_delivery_email_service':SimpleNamespace(DeliveryEmailOutcome=cls)}):
                    response=await ns['stripe_funnel_webhook'](request,service)
                expected=outcome if type(outcome) is cls else cls('unknown')
                self.assertEqual(response['delivery_email_status'],expected.status)
                self.assertEqual(response['delivery_email_provider_reference'],expected.provider_reference)
                self.assertEqual(response['order_id'],str(self.order_id))
                self.assertTrue(response['received'])
                service.create_order_from_checkout_completed.assert_awaited_once()

    def test_sent_outcome_cannot_be_constructed_without_reference(self):
        for ref in (None,'','invalid id'):
            with self.assertRaises(ValueError): self.module['DeliveryEmailOutcome']('sent',ref)


if __name__=='__main__': unittest.main()
