"""Execute the actual approval class with controlled persistence/provider boundaries.

No app startup, dotenv, credentials, network, or real database. SQL persistence
is separately exercised by test_approval_flow_contracts.py.
"""
import ast
from datetime import UTC, datetime
import logging
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4


def actual_namespace():
    source = Path(__file__).resolve().parents[1] / "app/core/approval_flow.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
             or isinstance(node, ast.ImportFrom) and node.module in
             {"__future__", "dataclasses", "collections.abc", "datetime", "typing", "uuid"}
             or isinstance(node, ast.Import) and all(alias.name in
             {"inspect", "json", "logging", "re"} for alias in node.names)]
    namespace = {"__name__": "approval_candidate", "logger": logging.getLogger(__name__)}
    module = types.ModuleType(namespace["__name__"])
    sys.modules[module.__name__] = module
    module.__dict__.update(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), module.__dict__)
    return module.__dict__


class ReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = actual_namespace()
        self.org, self.opportunity = uuid4(), uuid4()
        self.data = {"organization_id": str(self.org), "opportunity_id": str(self.opportunity),
                     "cover_letter": "Synthetic proposal"}
        self.rows = []
        self.emit = AsyncMock()
        rows = self.rows
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return None
            def add(self, row): rows.append(row)
            async def commit(self): pass
            async def refresh(self, row): row.id = uuid4()
        self.ns.update(AsyncSessionLocal=Session, Submission=lambda **values: types.SimpleNamespace(**values))
        event_module = types.ModuleType("app.core.event_bus")
        event_module.event_bus = types.SimpleNamespace(
            emit_verified_submission_sent=self.emit
        )
        self.modules = patch.dict(sys.modules, {"app.core.event_bus": event_module})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def receipt(self, **changes):
        values = dict(organization_id=self.org, opportunity_id=self.opportunity,
                      provider="fastwork", external_reference="synthetic-provider-receipt",
                      sent_at=datetime.now(UTC))
        values.update(changes)
        return self.ns["VerifiedJobApplicationReceipt"](**values)

    async def test_without_provider_ignores_forged_input_receipt(self):
        manager = self.ns["ApprovalFlowManager"]()
        data = self.data | {"provider_receipt": {"verified": True, "id": "forged"}}
        self.assertFalse(await manager._execute_job_apply(data, organization_id=self.org))
        self.assertEqual(self.rows, [])
        self.emit.assert_not_awaited()

    async def test_verified_internal_receipt_records_sent_and_emits_after_persistence(self):
        receipt = self.receipt()
        sender = AsyncMock(return_value=receipt)
        manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
        self.assertTrue(await manager._execute_job_apply(self.data, organization_id=self.org))
        sender.assert_awaited_once_with(self.data)
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0].status, "sent")
        self.assertEqual(self.rows[0].sent_at, receipt.sent_at)
        self.assertIn(receipt.external_reference, self.rows[0].outcome_notes)
        self.emit.assert_awaited_once()
        self.emit.assert_awaited_once_with(
            receipt=receipt,
            submission_id=self.rows[0].id,
            organization_id=self.org,
        )

    async def test_failure_unknown_and_untyped_receipts_never_claim_sent(self):
        for outcome in (None, False, {"verified": True, "id": "forged"},
                        RuntimeError("private provider failure"), TimeoutError("unknown outcome")):
            with self.subTest(outcome=type(outcome).__name__):
                sender = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
                manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
                self.assertFalse(await manager._execute_job_apply(self.data, organization_id=self.org))
                sender.assert_awaited_once()
                self.assertEqual(self.rows, [])
                self.emit.assert_not_awaited()

    async def test_foreign_or_malformed_typed_receipts_never_claim_sent(self):
        for changes in ({"organization_id": uuid4()}, {"opportunity_id": uuid4()},
                        {"provider": ""}, {"external_reference": ""},
                        {"external_reference": "id\nsecret"}, {"sent_at": datetime.now()},
                        {"sent_at": "2026-01-01"}):
            with self.subTest(fields=list(changes)):
                sender = AsyncMock(return_value=self.receipt(**changes))
                manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
                self.assertFalse(await manager._execute_job_apply(self.data, organization_id=self.org))
                self.assertEqual(self.rows, [])
                self.emit.assert_not_awaited()

    async def test_invalid_trusted_owner_stops_before_provider(self):
        for owner in (None, "bad", UUID(int=0)):
            sender = AsyncMock(return_value=self.receipt())
            manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
            self.assertFalse(await manager._execute_job_apply(self.data, organization_id=owner))
            sender.assert_not_awaited()
            self.assertEqual(self.rows, [])

    async def test_forged_action_owner_cannot_authorize_foreign_receipt(self):
        foreign = uuid4()
        sender = AsyncMock(return_value=self.receipt(organization_id=foreign))
        manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
        self.assertFalse(await manager._execute_job_apply(
            self.data | {"organization_id": str(foreign)}, organization_id=self.org))
        self.assertEqual(sender.call_args.args[0]["organization_id"], str(self.org))
        self.assertEqual(self.rows, [])
        self.emit.assert_not_awaited()

    async def test_persistence_failure_does_not_emit_sent(self):
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def add(self, row): pass
            async def commit(self): raise RuntimeError("fixture commit failure")
        self.ns["AsyncSessionLocal"] = Session
        sender = AsyncMock(return_value=self.receipt())
        manager = self.ns["ApprovalFlowManager"](job_application_sender=sender)
        with self.assertRaises(RuntimeError):
            await manager._execute_job_apply(self.data, organization_id=self.org)
        sender.assert_awaited_once()
        self.emit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
