"""Actual source methods, controlled settings/provider/persistence; no DB/network."""
import ast
from datetime import UTC, datetime
import hashlib
import logging
from pathlib import Path
import types
import sys
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch
from uuid import uuid4


class Field:
    def __init__(self, name): self.name = name
    def __eq__(self, other): return (self.name, "eq", other)
    def __lt__(self, other): return (self.name, "lt", other)
    def __ge__(self, other): return (self.name, "ge", other)
    def is_(self, other): return (self.name, "is", other)
    def isnot(self, other): return (self.name, "not", other)
    def label(self, name): return self


class Query:
    def __init__(self, *args): self.conditions, self.updates = [], {}
    def where(self, *args): self.conditions.extend(args); return self
    def limit(self, number): return self
    def with_for_update(self): return self
    def values(self, **kwargs): self.updates.update(kwargs); return self
    def group_by(self, *args): return self
    def having(self, *args): return self
    def subquery(self):
        self.c = types.SimpleNamespace(customer_email=Field("email"), organization_id=Field("organization_id"), last_paid_at=Field("paid_at"))
        return self


def model(*fields):
    return types.SimpleNamespace(**{name: Field(name) for name in fields})


class Result:
    def __init__(self, value=None, rows=None): self.value, self.rows = value, rows or []
    def scalar_one_or_none(self): return self.value
    def scalars(self): return self
    def all(self): return self.rows


class Session:
    def __init__(self, results=()):
        self.results, self.queries, self.added = list(results), [], []
        self.commit = AsyncMock()
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def execute(self, query):
        self.queries.append(query)
        return self.results.pop(0) if self.results else Result()
    def add(self, row): self.added.append(row)


def source_namespace(relative, values):
    source = Path(__file__).resolve().parents[1] / relative
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
             or isinstance(n, ast.Import) and all(a.name in {"logging", "re"} for a in n.names)
             or isinstance(n, ast.ImportFrom) and n.module in {"datetime", "typing", "uuid", "pydantic"}]
    namespace = {"logger": logging.getLogger(__name__), **values}
    exec(compile(ast.Module(nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class EmailReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = source_namespace("app/services/email_service.py", {
            "settings": types.SimpleNamespace(RESEND_API_KEY="synthetic-only", APP_ENV="production",
                                              FROM_EMAIL="fixture@example.invalid",
                                              ALLOW_REAL_EMAIL_SEND=True,
                                              EMAIL_RECIPIENT_ALLOWLIST="fixture@example.invalid"),
            "_sent_keys": set(),
            "_email_address_adapter": types.SimpleNamespace(
                validate_python=lambda address: address
            ),
            "ValidationError": ValueError,
        })
        self.service = self.ns["EmailService"]()
        self.service._send_via_resend = AsyncMock()
        self.ns["EmailTemplate"].synthetic = staticmethod(lambda: {
            "subject": "Synthetic", "html": "Synthetic", "text": "Synthetic",
        })

    async def test_delivery_missing_provider_reference_is_not_sent(self):
        self.service._send_via_resend.return_value = {}
        result = await self.service.send_email("fixture@example.invalid", "synthetic", {}, "fixture-key")
        self.assertNotEqual(result["status"], "sent")

    async def test_delivery_accepted_reference_and_ambiguous_receipts(self):
        cases = [({"id": "provider-reference-1"}, True), ({"id": ""}, False),
                 ({"id": None}, False), ({"id": True}, False),
                 ({"id": "spaces not valid"}, False),
                 ({"id": "provider-reference-1", "error": {}}, False),
                 ({"id": "provider-reference-1", "status": "failed"}, False),
                 (None, False)]
        for i, (response, accepted) in enumerate(cases):
            with self.subTest(response=response):
                self.service._send_via_resend.return_value = response
                result = await self.service.send_email("fixture@example.invalid", "synthetic", {}, f"fixture-{i}")
                self.assertEqual(self.ns["email_accepted"](result), accepted)
                self.assertEqual(result["status"] == "sent", accepted)

    async def test_delivery_failure_unknown_is_not_retried(self):
        for i, failure in enumerate([RuntimeError("private provider text"), TimeoutError("unknown")]):
            self.service._send_via_resend.reset_mock()
            self.service._send_via_resend.side_effect = failure
            result = await self.service.send_email("fixture@example.invalid", "synthetic", {}, f"failure-{i}")
            self.assertFalse(self.ns["email_accepted"](result))
            self.assertNotIn(str(failure), str(result))
            duplicate = await self.service.send_email("fixture@example.invalid", "synthetic", {}, f"failure-{i}")
            self.assertEqual(duplicate["status"], "skipped")
            self.service._send_via_resend.assert_awaited_once()

    async def test_delivery_dev_and_no_key_never_call_provider(self):
        self.service.api_key = ""
        result = await self.service.send_email("fixture@example.invalid", "synthetic", {}, "no-key")
        self.assertFalse(self.ns["email_accepted"](result))
        self.service.api_key = "synthetic-only"
        self.ns["settings"].APP_ENV = "development"
        result = await self.service.send_email("fixture@example.invalid", "synthetic", {}, "dev-mode")
        self.assertFalse(self.ns["email_accepted"](result))
        self.service._send_via_resend.assert_not_awaited()


class CallerResultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        email = source_namespace("app/services/email_service.py", {})
        self.accepted = email["email_accepted"]
        self.owner, self.checkout = uuid4(), uuid4()
        self.adapter = types.SimpleNamespace(send_email=AsyncMock())
        self.models = {
            "FunnelCheckoutSession": model("id", "organization_id", "product_id", "stripe_session_id",
                                            "expires_at", "status", "created_at", "abandoned_email_sent_at"),
            "FunnelOrder": model("id", "organization_id", "status", "paid_at", "customer_email"),
            "DigitalProduct": model("id", "organization_id", "name"),
            "Contact": model("id", "organization_id", "marketing_consent", "marketing_unsubscribed", "is_deleted", "email"),
        }
        self.automation = source_namespace("app/services/automation_email_service.py", {
            **self.models, "AsyncSession": object, "select": Query, "email_service": self.adapter,
            "hashlib": hashlib,
            "email_accepted": self.accepted, "STORE_URL": "https://example.invalid/store",
            "DELIVERY_URL": "https://example.invalid/delivery",
            "InvalidUnsubscribeProof": ValueError,
            "UnsubscribeProofUnavailable": RuntimeError,
            "create_unsubscribe_url": lambda _organization_id, _email: "https://example.invalid/unsubscribe?token=offline",
        })

    async def test_all_automation_triggers_propagate_result_and_suppression(self):
        order = types.SimpleNamespace(customer_email="fixture@example.invalid", contact_id=uuid4(), items=[])
        checkout = types.SimpleNamespace(status="pending", abandoned_email_sent_at=None,
            customer_email="fixture@example.invalid", contact_id=uuid4(), product_id=None, amount=1)
        for method in ("trigger_welcome", "trigger_abandoned_cart", "trigger_post_purchase",
                       "trigger_review_request", "trigger_cross_sell", "trigger_win_back"):
            for result in ({"status": "sent", "id": "accepted-1"},
                           {"status": "sent", "id": None}, {"status": "failed", "id": None},
                           {"status": "logged", "id": "dev-mode"}):
                self.adapter.send_email.reset_mock()
                self.adapter.send_email.return_value = result
                db = Session([Result(checkout if method == "trigger_abandoned_cart" else order)])
                service = self.automation["AutomationEmailService"](db)
                service._marketing_allowed = AsyncMock(return_value=True)
                args = (self.owner, "fixture@example.invalid", "Synthetic") if method in (
                    "trigger_welcome", "trigger_win_back") else (self.owner, self.checkout)
                kwargs = {}
                if method == "trigger_win_back":
                    digest = hashlib.sha256(b"fixture@example.invalid").hexdigest()
                    kwargs["idempotency_key"] = f"win_back:{self.owner}:{digest}:order:fixture"
                actual = await getattr(service, method)(*args, **kwargs)
                self.assertEqual(self.accepted(actual), self.accepted(result), method)
                self.adapter.send_email.assert_awaited_once()
                self.adapter.send_email.reset_mock()
                db = Session([Result(checkout if method == "trigger_abandoned_cart" else order)])
                service = self.automation["AutomationEmailService"](db)
                service._marketing_allowed = AsyncMock(return_value=False)
                self.assertEqual(
                    (await getattr(service, method)(*args, **kwargs))["status"], "suppressed"
                )
                self.adapter.send_email.assert_not_awaited()

    async def test_marketing_query_preserves_tenant_consent_unsubscribe_deletion(self):
        db = Session([Result(None)])
        service = self.automation["AutomationEmailService"](db)
        self.assertFalse(await service._marketing_allowed(self.owner, "fixture@example.invalid"))
        conditions = db.queries[0].conditions
        for expected in [("organization_id", "eq", self.owner), ("marketing_consent", "is", True),
                         ("marketing_unsubscribed", "is", False), ("is_deleted", "is", False)]:
            self.assertIn(expected, conditions)

    async def test_abandoned_lookup_and_product_are_owner_bound(self):
        checkout = types.SimpleNamespace(status="pending", abandoned_email_sent_at=None,
            customer_email="fixture@example.invalid", contact_id=uuid4(), product_id=uuid4(), amount=1)
        db = Session([Result(checkout), Result("Synthetic product")])
        service = self.automation["AutomationEmailService"](db)
        service._marketing_allowed = AsyncMock(return_value=True)
        self.adapter.send_email.return_value = {"status": "sent", "id": "accepted-1"}
        await service.trigger_abandoned_cart(self.owner, self.checkout)
        for query in db.queries:
            self.assertIn(("organization_id", "eq", self.owner), query.conditions)

    async def test_webhook_only_accepted_reference_marks_owned_timestamp(self):
        program = source_namespace("app/api/funnel_webhooks.py", {
            "router": types.SimpleNamespace(post=lambda *a, **k: lambda fn: fn),
            "Request": object, "FunnelOrderService": object, "AsyncSession": object,
            "Depends": lambda *a: None, "get_db": object, "email_accepted": self.accepted,
        })
        sqlalchemy = types.ModuleType("sqlalchemy")
        sqlalchemy.select = Query
        sqlalchemy.update = Query
        funnel = types.ModuleType("app.models.funnel")
        funnel.FunnelCheckoutSession = self.models["FunnelCheckoutSession"]
        product_id = uuid4()
        stripe_session_id = "cs_test_synthetic"
        stripe_expires_at = int(datetime(2026, 10, 7, 12, 0, tzinfo=UTC).timestamp())
        data_object = {"id": stripe_session_id, "expires_at": stripe_expires_at, "metadata": {
            "organization_id": str(self.owner), "funnel_checkout_session_id": str(self.checkout),
            "product_id": str(product_id),
        }}
        for result in ({"status": "sent", "id": "provider-reference-1"}, {"status": "sent", "id": None},
                       {"status": "failed", "id": None}, {"status": "suppressed", "id": None}, None):
            checkout = types.SimpleNamespace(id=self.checkout, organization_id=self.owner,
                product_id=product_id, stripe_session_id=stripe_session_id,
                expires_at=datetime.fromtimestamp(stripe_expires_at, UTC), status="pending",
                abandoned_email_sent_at=None)
            checkout_db, email_db = Session(), Session()
            checkout_db.scalar = AsyncMock(return_value=checkout)
            email_db.rollback = AsyncMock()
            db_sessions = iter((checkout_db, email_db))
            trigger = AsyncMock(return_value=result)
            program.update(AsyncSessionLocal=lambda: next(db_sessions), AutomationEmailService=lambda session: types.SimpleNamespace(
                trigger_abandoned_cart=trigger))
            self.assertIsInstance(self.adapter.send_email, AsyncMock)
            self.adapter.send_email.reset_mock()
            with patch.dict(sys.modules, {"sqlalchemy": sqlalchemy, "app.models.funnel": funnel}):
                actual = await program["_handle_checkout_expired"](data_object)
            checkout_query = checkout_db.scalar.await_args.args[0]
            for expected in [("id", "eq", self.checkout), ("organization_id", "eq", self.owner),
                             ("product_id", "eq", product_id),
                             ("stripe_session_id", "eq", stripe_session_id)]:
                self.assertIn(expected, checkout_query.conditions)
            self.assertEqual(int(checkout.expires_at.timestamp()), stripe_expires_at)
            self.assertEqual(checkout.status, "expired")
            checkout_db.commit.assert_awaited_once()
            trigger.assert_awaited_once_with(organization_id=self.owner, checkout_session_id=self.checkout)
            if self.accepted(result):
                self.assertTrue(self.accepted(actual))
                self.assertEqual(len(email_db.queries), 1)
                self.assertIn(("organization_id", "eq", self.owner), email_db.queries[0].conditions)
                self.assertIn(("id", "eq", self.checkout), email_db.queries[0].conditions)
                recorded_at = email_db.queries[0].updates["abandoned_email_sent_at"]
                self.assertIsInstance(recorded_at, datetime)
                self.assertEqual(recorded_at.tzinfo, UTC)
                email_db.commit.assert_awaited_once()
                email_db.rollback.assert_not_awaited()
            else:
                self.assertFalse(self.accepted(actual))
                self.assertNotEqual(actual.get("status"), "sent")
                email_db.commit.assert_not_awaited()
                email_db.rollback.assert_awaited_once()
                self.assertEqual(email_db.queries, [])
            self.adapter.send_email.assert_not_awaited()

    async def test_scanner_does_not_mark_unverified_results(self):
        program = source_namespace("app/tasks/funnel_automation_runtime.py", {
            **self.models, "select": Query, "email_accepted": self.accepted,
            "BATCH_LIMIT": 50, "ABANDONED_CART_AFTER": datetime.now(UTC)-datetime.now(UTC),
        })
        for result in ({"status": "sent", "id": "accepted-1"}, {"status": "sent", "id": None},
                       {"status": "failed", "id": None}, {"status": "suppressed", "id": None}):
            row = types.SimpleNamespace(id=self.checkout, organization_id=self.owner, abandoned_email_sent_at=None)
            db = Session([Result(rows=[row])])
            trigger = AsyncMock(return_value=result)
            program.update(AsyncSessionLocal=lambda: db, AutomationEmailService=lambda session: types.SimpleNamespace(
                trigger_abandoned_cart=trigger))
            count = await program["scan_abandoned_carts"]()
            self.assertEqual(count, int(self.accepted(result)))
            self.assertEqual(row.abandoned_email_sent_at is not None, self.accepted(result))
            trigger.assert_awaited_once_with(self.owner, self.checkout)

    async def test_order_scan_records_only_provider_accepted_result(self):
        program = source_namespace("app/tasks/funnel_automation_runtime.py", {
            **self.models, "select": Query, "email_accepted": self.accepted,
            "BATCH_LIMIT": 50, "ConversionEvent": model("metadata_json", "event_type"),
        })
        # The actual source uses a mapped event constructor; controlled record only.
        class Event:
            metadata_json, event_type = Field("metadata_json"), Field("event_type")
            def __init__(self, **kwargs): self.__dict__.update(kwargs)
        program["ConversionEvent"] = Event
        from datetime import timedelta
        for result in ({"status": "sent", "id": "accepted-1"}, {"status": "sent", "id": None},
                       {"status": "failed", "id": None}, {"status": "suppressed", "id": None}):
            order = types.SimpleNamespace(id=uuid4(), organization_id=self.owner)
            db = Session([Result(rows=[order]), Result(rows=[])])
            trigger = AsyncMock(return_value=result)
            program.update(AsyncSessionLocal=lambda: db, AutomationEmailService=lambda session: object())
            count = await program["_scan_order_emails"]("review_request_sent", trigger, timedelta(days=3))
            self.assertEqual(count, int(self.accepted(result)))
            self.assertEqual(len(db.added), int(self.accepted(result)))
            if db.added:
                self.assertEqual(db.added[0].organization_id, self.owner)
                self.assertEqual(db.added[0].metadata_json["provider_reference"], result["id"])
            trigger.assert_awaited_once()

    async def test_order_trigger_wrappers_propagate_provider_result(self):
        program = source_namespace("app/tasks/funnel_automation_runtime.py", {
            "BATCH_LIMIT": 50, "REVIEW_AFTER": 3, "CROSS_SELL_AFTER": 7,
        })
        order = types.SimpleNamespace(id=uuid4(), organization_id=self.owner)
        result = {"status": "failed", "id": None}
        service = types.SimpleNamespace(trigger_review_request=AsyncMock(return_value=result),
                                       trigger_cross_sell=AsyncMock(return_value=result))
        async def scan(event, trigger, cutoff, limit):
            return await trigger(service, order)
        program["_scan_order_emails"] = scan
        for method in ("scan_review_requests", "scan_cross_sells"):
            self.assertEqual(await program[method](), result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
