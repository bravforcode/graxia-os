"""Offline replay contracts: real source, mocked queue, no application startup."""
import ast
import logging
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
OWNER = UUID('00000000-0000-0000-0000-000000000001')


def load_bus():
    tree = ast.parse((ROOT / 'app/core/event_bus.py').read_text(encoding='utf-8'))
    # Do not initialize the application's global bus/settings.
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.FunctionDef) and node.name == '_create_global_event_bus'
        or isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'event_bus'
            for target in node.targets
        )
    )]
    namespace = {}
    exec(compile(tree, 'app/core/event_bus.py', 'exec'), namespace)
    return namespace


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


def load_route(namespace, bus):
    tree = ast.parse((ROOT / 'app/api/events.py').read_text(encoding='utf-8'))
    fn = next(node for node in tree.body
              if isinstance(node, ast.AsyncFunctionDef) and node.name == 'replay_event')
    fn.decorator_list = []
    globals_ = dict(
        namespace,
        event_bus=bus,
        HTTPException=HTTPError,
        AuthContext=object,
        Depends=lambda _dependency: SimpleNamespace(organization_id=OWNER),
        require_organization=object(),
        logger=logging.getLogger('offline-replay-test'),
    )
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'app/api/events.py', 'exec'), globals_)
    return globals_['replay_event']


class ReplayContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.namespace = load_bus()
        self.bus = self.namespace['EventBus']()
        self.bus.emit = AsyncMock(return_value=True)

    async def test_submission_without_receipt_never_publishes(self):
        with self.assertRaises(ValueError):
            await self.bus.replay_event('submission.sent', {})
        self.bus.emit.assert_not_awaited()

    async def test_caller_forged_receipt_cannot_unlock_replay(self):
        with self.assertRaises(ValueError):
            await self.bus.replay_event('submission.sent', {
                'verified': True, 'provider_receipt': {'id': 'forged'},
                'organization_id': '00000000-0000-0000-0000-000000000001',
            })
        self.bus.emit.assert_not_awaited()

    async def test_terminal_delivery_name_conventions_are_non_replayable(self):
        for name in ('email.sent', 'message.delivered', 'delivery.delivered', 'win_back_sent',
                     '  SUBMISSION.SENT\t', 'Email.Delivered', 'WIN_BACK_SENT '):
            with self.subTest(name=name), self.assertRaises(ValueError):
                await self.bus.replay_event(name, {})
        self.bus.emit.assert_not_awaited()

    async def test_ordinary_event_replay_still_forwards_exact_payload(self):
        payload = {'job_id': 'synthetic'}
        await self.bus.replay_event('job.found', payload)
        self.bus.emit.assert_awaited_once_with('job.found', payload)

    async def test_non_delivery_names_are_not_blocked_or_rewritten(self):
        for name in ('job.accepted', 'delivery.access.granted', 'delivery.opened',
                     'submission.created', 'consent.updated'):
            with self.subTest(name=name):
                self.bus.emit.reset_mock()
                await self.bus.replay_event(name, {})
                self.bus.emit.assert_awaited_once_with(name, {})

    async def test_api_returns_fixed_conflict_without_publish_or_dlq_removal(self):
        entry = ('submission.sent', {'verified': True}, 'synthetic failure')
        self.bus._failed_events.append(entry)
        self.bus._failed_event_organizations.append(str(OWNER))
        with self.assertRaises(HTTPError) as caught:
            await load_route(self.namespace, self.bus)(0)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail, 'Delivery success events cannot be replayed')
        self.bus.emit.assert_not_awaited()
        self.assertEqual(self.bus.get_failed_events(), [entry])

    async def test_api_ordinary_replay_remains_successful(self):
        payload = {'job_id': 'synthetic'}
        self.bus._failed_events.append(('job.found', payload, 'synthetic failure'))
        self.bus._failed_event_organizations.append(str(OWNER))
        response = await load_route(self.namespace, self.bus)(0)
        self.assertTrue(response['success'])
        self.bus.emit.assert_awaited_once_with(
            'job.found', payload, auth_context=SimpleNamespace(organization_id=OWNER)
        )


if __name__ == '__main__':
    unittest.main()
