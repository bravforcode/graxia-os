"""Actual producer/legacy method bodies with blocked app/network/data boundaries."""
import ast
import builtins
from datetime import UTC, datetime
import logging
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


class Auth:
    def __init__(self, owner=None):
        self.organization_id = owner
        self.is_authenticated = True
        self.is_mock_auth = False
        self.is_staging_or_production = True


class Generic:
    def __class_getitem__(cls, item): return cls


def load(relative, values, names=None):
    source = ROOT / relative
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and (names is None or n.name in names)
             or isinstance(n, ast.Import) and all(a.name in {"logging", "uuid"} for a in n.names)
             or isinstance(n, ast.ImportFrom) and n.module in {"datetime", "typing", "uuid", "pathlib"}]
    namespace = {"logger": logging.getLogger(__name__), **values}
    exec(compile(ast.Module(nodes, []), str(source), "exec"), namespace)
    return namespace


class ProducerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.owner = uuid4()
        self.control = load("app/core/control_plane.py", {
            "AuthContext": Auth, "ApprovalRequest": object, "AutomationRun": object,
        }, {"_trusted_approval_owner", "queue_approval_request", "create_draft_review_request", "ApprovalAlreadyProcessedError"})
        self.guard = self.control["_trusted_approval_owner"]
        self.queue = AsyncMock()
        self.common = {"BaseAgent": object, "AuthContext": Auth,
                       "_trusted_approval_owner": self.guard, "create_draft_review_request": self.queue}
        self.control_module = types.ModuleType("app.core.control_plane")
        self.control_module._trusted_approval_owner = self.guard

    async def test_missing_auth_stops_all_producers_before_database_or_provider_import(self):
        drafter = load("app/agents/drafter.py", self.common)["Drafter"]()
        follow = load("app/agents/follow_up.py", self.common)["FollowUpAgent"]()
        outreach = load("app/agents/outreach_agent.py", self.common)["OutreachAgent"]()
        career = load("app/core/career.py", {"UUID": __import__("uuid").UUID}, {"request_job_apply_approval"})
        calls = [lambda: drafter.handle_decided_opportunity({"decision": "do_now", "opportunity_id": str(uuid4()), "organization_id": str(self.owner)}),
                 lambda: drafter._draft_for_opportunity(uuid4()), lambda: follow.run(),
                 lambda: follow._handle_followup(types.SimpleNamespace(organization_id=self.owner)),
                 lambda: outreach.run(), lambda: career["request_job_apply_approval"](uuid4())]
        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if (name.startswith("app.") or name == "sqlalchemy") and name != "app.core.control_plane":
                raise AssertionError("producer_reached_external_boundary_without_auth")
            return original_import(name, *args, **kwargs)
        with patch.dict(sys.modules, {"app.core.control_plane": self.control_module}), patch.object(builtins, "__import__", guarded_import):
            for index, call in enumerate(calls):
                if index == 4:  # Outreach reports a fail-closed blocked result.
                    self.assertEqual(
                        await call(),
                        {"status": "blocked", "reason": "trusted_auth_context_required"},
                    )
                    continue
                with self.assertRaisesRegex(ValueError, "approval_authenticated_organization_required"):
                    await call()
        self.queue.assert_not_awaited()

    async def test_foreign_followup_denies_before_identity_or_database(self):
        follow = load("app/agents/follow_up.py", self.common)["FollowUpAgent"]()
        with self.assertRaisesRegex(ValueError, "approval_foreign_submission"):
            await follow._handle_followup(types.SimpleNamespace(organization_id=uuid4()), auth=Auth(self.owner))
        self.queue.assert_not_awaited()

    async def test_cog_handler_missing_auth_fails_before_queue_insert(self):
        api = load("app/api/approvals.py", {
            "AuthContext": Auth, "ApprovalRequest": object,
            "queue_approval_request": self.control["queue_approval_request"],
        }, {"create_approval_from_event"})
        tree = ast.parse((ROOT / "app/core/bootstrap.py").read_text(encoding="utf-8"))
        callback = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "handle_cog_suggestion")
        namespace = {"create_approval_from_event": api["create_approval_from_event"], "auth": None}
        exec(compile(ast.Module([callback], []), "bootstrap-callback", "exec"), namespace)
        with self.assertRaisesRegex(ValueError, "approval_authenticated_organization_required"):
            await namespace["handle_cog_suggestion"]({"organization_id": str(self.owner), "suggested_weights": {}})

    async def test_legacy_cqrs_missing_auth_rejects_before_unit_of_work(self):
        unit = Mock(side_effect=AssertionError("unit_of_work_must_not_open"))
        ns = load("app/cqrs/draft_handlers.py", {
            "CommandHandler": Generic, "QueryHandler": Generic, "Result": Generic,
            "ApproveDraftCommand": object, "RejectDraftCommand": object,
            "GetDraftQuery": object, "ListDraftsQuery": object, "ContentDraft": object,
            "_trusted_approval_owner": self.guard, "AsyncUnitOfWork": unit,
            "err": lambda exc: (False, exc), "ok": lambda value: (True, value),
        })
        for name in ("ApproveDraftHandler", "RejectDraftHandler"):
            result = await ns[name]().handle(types.SimpleNamespace(draft_id=uuid4(), reason="Synthetic"))
            self.assertFalse(result[0])
            self.assertIsInstance(result[1], ValueError)
        unit.assert_not_called()

    def test_all_production_queue_calls_forward_internal_auth(self):
        expected = {"app/agents/drafter.py": 1, "app/agents/follow_up.py": 1,
                    "app/agents/outreach_agent.py": 2, "app/core/career.py": 1,
                    "app/core/bootstrap.py": 1}
        for path, count in expected.items():
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id in {"create_draft_review_request", "queue_approval_request", "create_approval_from_event"}]
            self.assertEqual(len(calls), count, path)
            for call in calls:
                keyword = next(k for k in call.keywords if k.arg == "auth")
                self.assertIsInstance(keyword.value, ast.Name)
                self.assertEqual(keyword.value.id, "auth")

    async def test_legacy_cqrs_foreign_or_duplicate_cannot_mutate_draft(self):
        foreign = types.SimpleNamespace(organization_id=uuid4())
        owned = types.SimpleNamespace(organization_id=self.owner)
        repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=foreign), update=AsyncMock())
        session = types.SimpleNamespace(refresh=AsyncMock())
        class Unit:
            async def __aenter__(self): self.session = session; return self
            async def __aexit__(self, *args): pass
        cas = AsyncMock(return_value=0)
        ns = load("app/cqrs/draft_handlers.py", {
            "CommandHandler": Generic, "QueryHandler": Generic, "Result": Generic,
            "ApproveDraftCommand": object, "RejectDraftCommand": object,
            "GetDraftQuery": object, "ListDraftsQuery": object, "ContentDraft": object,
            "_trusted_approval_owner": self.guard, "AsyncUnitOfWork": Unit,
            "DraftRepository": lambda db: repo, "mark_subject_approvals_resolved": cas,
            "err": lambda exc: (False, exc), "ok": lambda value: (True, value),
        })
        for name in ("ApproveDraftHandler", "RejectDraftHandler"):
            handler = ns[name](auth=Auth(self.owner))
            command = types.SimpleNamespace(draft_id=uuid4(), reason="Synthetic")
            repo.get_by_id.return_value = foreign
            self.assertFalse((await handler.handle(command))[0])
            cas.assert_not_awaited()
            repo.get_by_id.return_value = owned
            self.assertFalse((await handler.handle(command))[0])
            self.assertEqual(cas.call_args.kwargs["auth"].organization_id, self.owner)
            cas.reset_mock()
        repo.update.assert_not_awaited()
        session.refresh.assert_not_awaited()

    async def test_legacy_subject_resolution_uses_owned_cas_and_skips_duplicate(self):
        class Field:
            def __init__(self, name): self.name = name
            def __eq__(self, value): return (self.name, value)
        row = types.SimpleNamespace(**{n: Field(n) for n in ("id", "subject_type", "subject_id", "organization_id", "status")})
        captured = []
        class Query:
            def where(self, *conditions): captured.extend(conditions); return self
        approval_id = uuid4()
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def execute(self, query): return types.SimpleNamespace(scalars=lambda: [approval_id])
        control = load("app/core/control_plane.py", {
            "AuthContext": Auth, "ApprovalRequest": row,
            "_trusted_approval_owner": self.guard, "AsyncSessionLocal": Session,
            "select": lambda *a: Query(),
        }, {"ApprovalAlreadyProcessedError", "mark_subject_approvals_resolved"})
        cas = AsyncMock(side_effect=[types.SimpleNamespace(id=approval_id, status="approved"), control["ApprovalAlreadyProcessedError"]("approved")])
        control["resolve_approval_request"] = cas
        for expected in (1, 0):
            self.assertEqual(await control["mark_subject_approvals_resolved"](
                "content_draft", uuid4(), "approved", auth=Auth(self.owner)), expected)
        self.assertIn(("organization_id", self.owner), captured)
        self.assertEqual(cas.await_count, 2)
        self.assertEqual(cas.call_args.kwargs["organization_id"], self.owner)
        with self.assertRaises(ValueError):
            await control["mark_subject_approvals_resolved"]("content_draft", uuid4(), "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
