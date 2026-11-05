"""Offline regression contracts for event replay aliases and tenant-scoped DLQ."""
import ast
import logging
from pathlib import Path
import unittest
from unittest.mock import AsyncMock
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
OWNER = UUID("00000000-0000-0000-0000-000000000001")
FOREIGN = UUID("00000000-0000-0000-0000-000000000002")
EVENT_NAMES = {
    "get_event_stats",
    "get_failed_events",
    "replay_event",
    "remove_failed_event",
    "clear_failed_events",
    "get_event_bus_health",
}


def load_bus():
    tree = ast.parse((ROOT / "app/core/event_bus.py").read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "_create_global_event_bus"
            or isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "event_bus"
                for target in node.targets
            )
        )
    ]
    namespace = {}
    exec(compile(tree, "app/core/event_bus.py", "exec"), namespace)
    return namespace


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


def load_api(namespace, bus):
    tree = ast.parse((ROOT / "app/api/events.py").read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in EVENT_NAMES
    ]
    for function in functions:
        function.decorator_list = []
    globals_ = {
        "AuthContext": object,
        "Depends": lambda dependency: None,
        "require_organization": object(),
        "HTTPException": HTTPError,
        "DeliverySuccessReplayError": namespace["DeliverySuccessReplayError"],
        "event_bus": bus,
        "logger": logging.getLogger("offline-event-api-test"),
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "app/api/events.py", "exec"),
        globals_,
    )
    return globals_


def trusted_auth(organization_id):
    from app.auth.context import AuthContext

    return AuthContext(
        organization_id=organization_id,
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )


async def record_failure(bus, event, payload, auth_context=None):
    async def fail(_payload):
        raise RuntimeError("synthetic handler failure")

    bus.subscribe(event, fail)
    await bus._process_event(event, payload, auth_context=auth_context)


class EventBusTenantAndReplayContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.namespace = load_bus()
        self.bus = self.namespace["EventBus"]()
        self.bus.emit = AsyncMock(return_value=True)

    async def test_replay_rejects_terminal_aliases_and_keeps_ordinary_events(self):
        aliases = (
            "submission.sent",
            "submission_sent",
            "SubmissionSent",
            "SUBMISSION/SENT",
            "submissionsent",
            "email.sent",
            "EmailSent",
            "message.delivered",
            "MessageDelivered",
            "delivery-delivered",
            "WIN_BACK_SENT",
            "  Submission.Sent\t",
        )
        for event in aliases:
            with self.subTest(event=event), self.assertRaises(
                self.namespace["DeliverySuccessReplayError"]
            ):
                await self.bus.replay_event(event, {})
        self.bus.emit.assert_not_awaited()

        for event in ("job.found", "delivery.access.granted", "consent.updated"):
            await self.bus.replay_event(event, {"safe": True})
        self.assertEqual(self.bus.emit.await_count, 3)

    async def test_typed_submission_sent_cannot_bypass_replay_guard(self):
        from datetime import UTC, datetime

        from app.core.domain_events import SubmissionSent

        event = SubmissionSent(submission_id="synthetic", sent_at=datetime.now(UTC))
        with self.assertRaises(self.namespace["DeliverySuccessReplayError"]):
            await self.bus.emit_domain_event(event)
        self.bus.emit.assert_not_awaited()

    async def test_failed_events_are_visible_only_to_canonical_owner(self):
        await record_failure(
            self.bus,
            "tenant.failure",
            {"organization_id": str(OWNER), "payload": "owner"},
            trusted_auth(OWNER),
        )
        await record_failure(
            self.bus,
            "tenant.failure",
            {"data": {"org_id": str(FOREIGN)}, "payload": "foreign"},
            trusted_auth(FOREIGN),
        )
        await record_failure(self.bus, "global.failure", {"payload": "unscoped"})

        owner_rows = self.bus.get_failed_events_for_organization(OWNER)
        self.assertEqual(len(owner_rows), 1)
        self.assertEqual(owner_rows[0][1]["payload"], "owner")
        self.assertEqual(self.bus.get_failed_events_for_organization(FOREIGN)[0][1]["payload"], "foreign")
        self.assertEqual(self.bus.get_failed_events_for_organization(None), [])
        self.assertEqual(self.bus.get_failed_events_for_organization("not-a-uuid"), [])

    async def test_malformed_or_untracked_dlq_metadata_fails_closed(self):
        await record_failure(
            self.bus,
            "tenant.failure",
            {"organization_id": "not-a-uuid", "payload": "untrusted"},
            trusted_auth(OWNER),
        )
        self.assertEqual(self.bus.get_failed_events_for_organization(OWNER), [])

        self.bus._failed_events.append(("legacy.failure", {"organization_id": str(OWNER)}, "old"))
        self.assertEqual(self.bus.get_failed_events_for_organization(OWNER), [])

    async def test_remove_and_clear_use_scoped_indexes(self):
        for event, organization_id in (
            ("owner.one", OWNER),
            ("foreign.one", FOREIGN),
            ("owner.two", OWNER),
        ):
            await record_failure(
                self.bus,
                event,
                {"organization_id": str(organization_id)},
                trusted_auth(organization_id),
            )

        self.assertEqual(
            [row[0] for row in self.bus.get_failed_events_for_organization(OWNER)],
            ["owner.one", "owner.two"],
        )
        self.assertTrue(self.bus.remove_failed_event_for_organization(0, OWNER))
        self.assertEqual(
            [row[0] for row in self.bus.get_failed_events_for_organization(OWNER)],
            ["owner.two"],
        )
        self.assertEqual(self.bus.clear_failed_events_for_organization(OWNER), 1)
        self.assertEqual(self.bus.clear_failed_events_for_organization(OWNER), 0)
        self.assertEqual(
            [row[0] for row in self.bus.get_failed_events_for_organization(FOREIGN)],
            ["foreign.one"],
        )

    async def test_api_routes_bind_scope_to_organization_dependency(self):
        source = (ROOT / "app/api/events.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for function in (
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name in EVENT_NAMES
        ):
            auth_index = next(
                index
                for index, argument in enumerate(function.args.args)
                if argument.arg == "auth"
            )
            default_index = auth_index - (
                len(function.args.args) - len(function.args.defaults)
            )
            auth_default = function.args.defaults[default_index]
            self.assertIsInstance(auth_default, ast.Call, function.name)
            self.assertIsInstance(auth_default.func, ast.Name, function.name)
            self.assertEqual(auth_default.func.id, "Depends", function.name)
            self.assertIsInstance(auth_default.args[0], ast.Name, function.name)
            self.assertEqual(auth_default.args[0].id, "require_organization", function.name)

    async def test_api_failed_read_and_mutations_do_not_cross_tenant(self):
        await record_failure(
            self.bus,
            "owner.failure",
            {"organization_id": str(OWNER)},
            trusted_auth(OWNER),
        )
        await record_failure(
            self.bus,
            "foreign.failure",
            {"organization_id": str(FOREIGN)},
            trusted_auth(FOREIGN),
        )
        api = load_api(self.namespace, self.bus)
        owner_auth = trusted_auth(OWNER)
        foreign_auth = trusted_auth(FOREIGN)

        self.bus._organization_stats[str(OWNER)].update(
            {"owner.event": 2}
        )
        self.bus._organization_stats[str(FOREIGN)].update(
            {"foreign.private": 99}
        )
        self.assertEqual(
            await api["get_event_stats"](owner_auth),
            {"total_events": 2, "by_type": {"owner.event": 2}},
        )

        owner_response = await api["get_failed_events"](owner_auth)
        self.assertEqual(owner_response["total"], 1)
        self.assertEqual(owner_response["events"][0]["event"], "owner.failure")

        with self.assertRaises(HTTPError) as caught:
            await api["replay_event"](1, owner_auth)
        self.assertEqual(caught.exception.status_code, 404)
        with self.assertRaises(HTTPError) as caught:
            await api["remove_failed_event"](1, owner_auth)
        self.assertEqual(caught.exception.status_code, 404)
        self.bus.emit.assert_not_awaited()

        self.assertEqual(
            await api["clear_failed_events"](owner_auth),
            {"success": True, "cleared": 1},
        )
        self.assertEqual(
            [row[0] for row in self.bus.get_failed_events_for_organization(FOREIGN)],
            ["foreign.failure"],
        )
        health = await api["get_event_bus_health"](foreign_auth)
        self.assertEqual(health, {"status": "healthy", "failed_events": 1})

    async def test_api_rejects_terminal_alias_without_replay_or_dlq_removal(self):
        await record_failure(
            self.bus,
            "SubmissionSent",
            {"organization_id": str(OWNER)},
            trusted_auth(OWNER),
        )
        api = load_api(self.namespace, self.bus)
        auth = trusted_auth(OWNER)

        with self.assertRaises(HTTPError) as caught:
            await api["replay_event"](0, auth)
        self.assertEqual(caught.exception.status_code, 409)
        self.bus.emit.assert_not_awaited()
        self.assertEqual(len(self.bus.get_failed_events_for_organization(OWNER)), 1)


if __name__ == "__main__":
    unittest.main()
