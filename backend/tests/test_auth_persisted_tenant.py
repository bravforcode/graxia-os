"""Offline contracts for persisted tenant identity; no real JWT, DB or network."""
import ast
import runpy
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
AuthContext = runpy.run_path(str(ROOT / 'app/auth/context.py'))['AuthContext']
OWNER = uuid.UUID('00000000-0000-0000-0000-000000000001')
FOREIGN = uuid.UUID('00000000-0000-0000-0000-000000000002')
ACTOR = uuid.UUID('00000000-0000-0000-0000-000000000003')


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


def load_dependency():
    tree = ast.parse((ROOT / 'app/auth/dependencies.py').read_text(encoding='utf-8'))
    names = {'_csv_header_values', '_request_id', '_correlation_id', '_role_permissions', 'get_auth_context'}
    tree.body = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    namespace = dict(uuid=uuid, UUID=uuid.UUID, AuthContext=AuthContext,
                     LOCAL_DEV_ORGANIZATION_ID=OWNER, Request=SimpleNamespace,
                     settings=SimpleNamespace(APP_ENV='production'),
                     Header=lambda _: None, HTTPException=HTTPError,
                     status=SimpleNamespace(HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403),
                     normalize_permissions=lambda items: items,
                     permissions_for_role=lambda role: ['role:' + role])
    exec(compile(tree, 'app/auth/dependencies.py', 'exec'), namespace)
    return namespace


class Session:
    def __init__(self, user):
        self.get = AsyncMock(return_value=user)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None


class PersistedTenantContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = load_dependency()
        self.user = SimpleNamespace(id=ACTOR, organization_id=OWNER, role='user', is_active=True)
        self.session = Session(self.user)
        self.verify = AsyncMock(return_value={'sub': str(ACTOR), 'role': 'admin'})
        self.request = SimpleNamespace(method='POST', headers={'X-Graxia-Permissions': 'admin:write'},
            state=SimpleNamespace(auth_payload={'sub': str(ACTOR)},
                                  authenticated_user_id=str(ACTOR), authenticated_role='admin'))
        modules = {
            'app.database': SimpleNamespace(AsyncSessionLocal=lambda: self.session),
            'app.middleware.auth': SimpleNamespace(build_auth_context=self.verify,
                AuthLevel=SimpleNamespace(PUBLIC='public'), classify_route=lambda *args: 'authenticated',
                find_route_template=lambda request: '/api/v1/approvals'),
            'app.models.user': SimpleNamespace(User=object),
        }
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    async def test_foreign_org_selector_rejects_before_caller_write(self):
        write = AsyncMock()
        with self.assertRaises(HTTPError) as caught:
            auth = await self.ns['get_auth_context'](self.request, x_graxia_org_id=str(FOREIGN))
            await write(auth)
        self.assertEqual(caught.exception.status_code, 403)
        write.assert_not_awaited()

    async def test_forged_identity_permissions_and_scopes_are_ignored(self):
        auth = await self.ns['get_auth_context'](self.request, x_graxia_org_id=str(OWNER),
            x_graxia_actor_type='system', x_graxia_actor_id='forged', x_graxia_scopes='admin:write')
        self.verify.assert_awaited_once_with(self.request)
        self.session.get.assert_awaited_once_with(object, ACTOR)
        self.assertEqual(auth.actor_id, str(ACTOR))
        self.assertEqual(auth.actor_type, 'user')
        self.assertEqual(auth.permissions, ['role:user'])
        self.assertEqual(auth.scopes, [])
        self.assertFalse(auth.is_internal)
        self.assertFalse(auth.is_mock_auth)

    async def test_owner_comes_from_persisted_user_without_selector(self):
        auth = await self.ns['get_auth_context'](self.request)
        self.assertEqual(auth.organization_id, OWNER)
        self.assertTrue(auth.is_authenticated)

    async def test_inactive_missing_user_and_missing_org_fail_closed(self):
        for user in (None, SimpleNamespace(id=ACTOR, organization_id=OWNER, role='user', is_active=False),
                     SimpleNamespace(id=ACTOR, organization_id=None, role='user', is_active=True)):
            with self.subTest(user=user):
                self.session.get.return_value = user
                with self.assertRaises(HTTPError):
                    await self.ns['get_auth_context'](self.request, x_graxia_org_id=str(OWNER))

    async def test_missing_verified_jwt_stops_before_database(self):
        self.verify.side_effect = HTTPError(401, 'Authentication required')
        with self.assertRaises(HTTPError):
            await self.ns['get_auth_context'](self.request, x_graxia_org_id=str(OWNER))
        self.session.get.assert_not_awaited()

    def middleware_dispatch(self):
        tree = ast.parse((ROOT / 'app/auth/middleware.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == 'AuthContextMiddleware')
        fn = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'dispatch')
        future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
        namespace = dict(settings=self.ns['settings'], HTTPException=HTTPError,
                         get_auth_context=self.ns['get_auth_context'],
                         build_error_response=lambda request, **kwargs: kwargs)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[future, fn], type_ignores=[])),
                     'app/auth/middleware.py', 'exec'), namespace)
        return namespace['dispatch']

    async def test_middleware_foreign_selector_never_calls_downstream(self):
        self.request.headers['X-Graxia-Org-Id'] = str(FOREIGN)
        self.request.state.auth_context = 'untrusted prior context'
        downstream = AsyncMock()
        response = await self.middleware_dispatch()(object(), self.request, downstream)
        self.assertEqual(response['status_code'], 403)
        self.assertIsNone(self.request.state.auth_context)
        downstream.assert_not_awaited()
        self.verify.assert_awaited_once_with(self.request)

    async def test_middleware_valid_owner_uses_verified_user_not_headers(self):
        self.request.headers.update({'X-Graxia-Org-Id': str(OWNER),
            'X-Graxia-Actor-Id': 'forged', 'X-Graxia-Actor-Type': 'system'})
        downstream = AsyncMock(return_value='passed')
        response = await self.middleware_dispatch()(object(), self.request, downstream)
        self.assertEqual(response, 'passed')
        downstream.assert_awaited_once_with(self.request)
        self.assertEqual(self.request.state.auth_context.organization_id, OWNER)
        self.assertEqual(self.request.state.auth_context.actor_id, str(ACTOR))
        self.assertEqual(self.request.state.auth_context.permissions, ['role:user'])


if __name__ == '__main__':
    unittest.main()
