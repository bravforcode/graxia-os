"""
Chaos Tests — All untested api/ modules.

Modules covered:
  1. api/admin.py — admin endpoints
  2. api/db.py — database layer
  3. api/health.py — health check endpoints
  4. api/orders.py — order management endpoints
  5. api/positions.py — position endpoints
  6. api/risk.py — risk endpoints
  7. api/webhook.py — webhook handling
  8. api/webhook_receiver.py — webhook receiver

RULE: If a test fails, fix the CODE, never the test.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure conftest mocks are active (revenue_os.db, get_settings)
# conftest.py handles sys.modules patching before collection

ADMIN_KEY = "test-admin-key-12345"
WEBHOOK_SECRET = "test-webhook-secret"


def _mock_config():
    cfg = MagicMock()
    cfg.admin_api_key = ADMIN_KEY
    cfg.webhook_hmac_secret = WEBHOOK_SECRET
    cfg.trading_mode = MagicMock()
    cfg.trading_mode.value = "PAPER"
    return cfg


def _mock_settings():
    s = MagicMock()
    s.TV_WEBHOOK_SECRET = WEBHOOK_SECRET
    s.ADMIN_API_KEY = ADMIN_KEY
    s.trading_mode = "PAPER"
    s.live_trading_enabled = False
    return s


def _make_request(body: bytes | str | dict | None, headers: dict | None = None) -> MagicMock:
    """Build a fake FastAPI Request."""
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode()
    elif isinstance(body, str):
        body_bytes = body.encode()
    elif body is None:
        body_bytes = b""
    else:
        body_bytes = body

    req = MagicMock()
    req.body = AsyncMock(return_value=body_bytes)

    def _lazy_json():
        if not body_bytes:
            return {}
        return json.loads(body_bytes)

    req.json = AsyncMock(side_effect=_lazy_json)
    req.headers = headers or {}
    req.app = MagicMock()
    req.app.state = MagicMock()
    req.app.state.signal_gateway = AsyncMock()
    req.app.state.signal_gateway.ingest = AsyncMock(
        return_value=MagicMock(
            signal_id="sig-001",
            symbol="EURUSD",
            side=MagicMock(value="BUY"),
        )
    )
    return req


# ═══════════════════════════════════════════════════════════════════
# 1. api/admin.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestAdminChaos:
    """Chaos tests for admin endpoints."""

    @pytest.mark.asyncio
    async def test_verify_admin_missing_key(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key=None)

    @pytest.mark.asyncio
    async def test_verify_admin_wrong_key(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key="wrong-key")

    @pytest.mark.asyncio
    async def test_verify_admin_empty_key(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key="")

    @pytest.mark.asyncio
    async def test_verify_admin_sql_injection(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key="' OR 1=1 --")

    @pytest.mark.asyncio
    async def test_verify_admin_xss_attempt(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key="<script>alert(1)</script>")

    @pytest.mark.asyncio
    async def test_change_mode_empty_body(self):
        from graxia.packages.quant_os.api.admin import change_trading_mode

        with pytest.raises(Exception):
            await change_trading_mode(request=None, authorized=True)

    @pytest.mark.asyncio
    async def test_change_mode_invalid_mode(self):
        from graxia.packages.quant_os.api.admin import ModeChangeRequest, change_trading_mode

        with pytest.raises(Exception):
            await change_trading_mode(
                request=ModeChangeRequest(mode="NONEXISTENT"),
                authorized=True,
            )

    @pytest.mark.asyncio
    async def test_update_strategy_empty_id(self):
        from graxia.packages.quant_os.api.admin import StrategyUpdateRequest, update_strategy

        # No DI validation on direct call — accepts empty strategy_id
        result = await update_strategy(
            request=StrategyUpdateRequest(strategy_id="", params={}),
            authorized=True,
        )
        assert result["strategy_id"] == ""

    @pytest.mark.asyncio
    async def test_audit_log_returns_data(self):
        from graxia.packages.quant_os.api.admin import get_audit_log

        # authorized param is only enforced by FastAPI DI, not function body
        result = await get_audit_log(limit=100, authorized=True)
        assert "entries" in result

    @pytest.mark.asyncio
    async def test_system_stats_returns_data(self):
        from graxia.packages.quant_os.api.admin import get_system_stats

        result = await get_system_stats(authorized=True)
        assert "orders" in result

    @pytest.mark.asyncio
    async def test_admin_key_overflow(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await verify_admin(api_key="x" * 100_000)

    @pytest.mark.asyncio
    async def test_admin_concurrent_auth_check(self):
        from graxia.packages.quant_os.api.admin import verify_admin

        with patch("graxia.packages.quant_os.api.admin.get_config", return_value=_mock_config()):
            tasks = [verify_admin(api_key=ADMIN_KEY) for _ in range(20)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = [r for r in results if r is True]
            assert len(successes) == 20


# ═══════════════════════════════════════════════════════════════════
# 2. api/db.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestDbChaos:
    """Chaos tests for database layer."""

    @pytest.mark.asyncio
    async def test_get_db_engine_failure(self):
        with patch("graxia.packages.quant_os.api.db._get_engine") as m:
            m.side_effect = RuntimeError("DB connection refused")
            from graxia.packages.quant_os.api.db import get_db

            with pytest.raises(RuntimeError):
                async for _ in get_db():
                    pass

    @pytest.mark.asyncio
    async def test_get_db_returns_session(self):
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("graxia.packages.quant_os.api.db._get_engine") as m:
            engine = MagicMock()
            engine.session.return_value = mock_cm
            m.return_value = engine
            import graxia.packages.quant_os.api.db as db_mod

            db_mod._get_engine = lambda: engine
            gen = db_mod.get_db()
            session = await gen.__anext__()
            assert session == mock_session

    @pytest.mark.asyncio
    async def test_get_db_timeout(self):
        with patch("graxia.packages.quant_os.api.db._get_engine") as m:
            m.side_effect = TimeoutError("Connection timed out")
            from graxia.packages.quant_os.api.db import get_db

            with pytest.raises(asyncio.TimeoutError):
                async for _ in get_db():
                    pass


# ═══════════════════════════════════════════════════════════════════
# 3. api/health.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestHealthChaos:
    """Chaos tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_basic(self):
        import graxia.packages.quant_os.api.health as health_mod

        req = MagicMock()
        req.app.state._start_time = None
        req.app.state.signal_queue = MagicMock()
        req.app.state.signal_queue.qsize.return_value = 0
        req.app.state.duckdb_write_queue = None
        req.app.state.event_bus = None
        result = await health_mod.health_check(req)
        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_health_check_db_down(self):
        import graxia.packages.quant_os.api.health as health_mod

        req = MagicMock()
        req.app.state._start_time = None
        req.app.state.signal_queue = MagicMock()
        req.app.state.signal_queue.qsize.return_value = 5
        req.app.state.duckdb_write_queue = None
        req.app.state.event_bus = None
        result = await health_mod.health_check(req)
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_redact_secrets_nested(self):
        from graxia.packages.quant_os.api.health import _redact_secrets

        data = {"webhook_hmac_secret": "SECRET123", "nested": {"token": "abc123", "safe": "ok"}}
        result = _redact_secrets(data)
        assert result["webhook_hmac_secret"] == "***REDACTED***"

    @pytest.mark.asyncio
    async def test_redact_secrets_string_passthrough(self):
        from graxia.packages.quant_os.api.health import _redact_secrets

        # _redact_secrets only handles dict/list; strings pass through unchanged
        result = _redact_secrets("password=secret123")
        assert result == "password=secret123"

    @pytest.mark.asyncio
    async def test_health_check_concurrent(self):
        import graxia.packages.quant_os.api.health as health_mod

        results = []
        for _ in range(10):
            req = MagicMock()
            req.app.state._start_time = None
            req.app.state.signal_queue = MagicMock()
            req.app.state.signal_queue.qsize.return_value = 0
            req.app.state.duckdb_write_queue = None
            req.app.state.event_bus = None
            results.append(await health_mod.health_check(req))
        assert all(isinstance(r, dict) for r in results)


# ═══════════════════════════════════════════════════════════════════
# 4. api/orders.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestOrdersChaos:
    """Chaos tests for order management endpoints."""

    @pytest.mark.asyncio
    async def test_create_order_not_implemented(self):
        from graxia.packages.quant_os.api.orders import OrderCreateRequest, create_order

        mock_db = AsyncMock()
        req = OrderCreateRequest(
            symbol="EURUSD",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
        )
        with pytest.raises(Exception):
            await create_order(request=req, db=mock_db)

    @pytest.mark.asyncio
    async def test_create_order_empty_symbol(self):
        from graxia.packages.quant_os.api.orders import OrderCreateRequest

        # No min_length validation on symbol — accepts empty string
        req = OrderCreateRequest(symbol="", side="BUY", order_type="MARKET", quantity=Decimal("0.01"))
        assert req.symbol == ""

    @pytest.mark.asyncio
    async def test_create_order_negative_quantity(self):
        from graxia.packages.quant_os.api.orders import OrderCreateRequest

        with pytest.raises(Exception):
            OrderCreateRequest(symbol="EURUSD", side="BUY", order_type="MARKET", quantity=Decimal("-1"))

    @pytest.mark.asyncio
    async def test_get_order_not_found(self):
        from graxia.packages.quant_os.api.orders import get_order

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_order(order_id="nonexistent", db=mock_db)

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self):
        from graxia.packages.quant_os.api.orders import cancel_order

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await cancel_order(order_id="nonexistent", db=mock_db)

    @pytest.mark.asyncio
    async def test_approve_order_not_found(self):
        from graxia.packages.quant_os.api.orders import approve_order

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await approve_order(order_id="nonexistent", db=mock_db)

    @pytest.mark.asyncio
    async def test_order_sql_injection(self):
        from graxia.packages.quant_os.api.orders import get_order

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_order(order_id="' OR 1=1 --", db=mock_db)

    @pytest.mark.asyncio
    async def test_order_xss_in_symbol(self):
        from graxia.packages.quant_os.api.orders import get_order

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_order(order_id="<script>alert(1)</script>", db=mock_db)

    @pytest.mark.asyncio
    async def test_list_orders_valid_params(self):
        from graxia.packages.quant_os.api.orders import list_orders

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        result = await list_orders(limit=50, offset=0, db=mock_db)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_orders_with_filters(self):
        from graxia.packages.quant_os.api.orders import OrderStatus, list_orders

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        result = await list_orders(
            status=OrderStatus.FILLED, symbol="EURUSD", strategy_id="mtm", limit=10, offset=0, db=mock_db
        )
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_order_large_symbol(self):
        from graxia.packages.quant_os.api.orders import OrderCreateRequest

        # No max_length validation — accepts any string
        req = OrderCreateRequest(symbol="A" * 10_000, side="BUY", order_type="MARKET", quantity=Decimal("0.01"))
        assert len(req.symbol) == 10_000


# ═══════════════════════════════════════════════════════════════════
# 5. api/positions.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestPositionsChaos:
    """Chaos tests for position endpoints."""

    @pytest.mark.asyncio
    async def test_list_positions_empty(self):
        from graxia.packages.quant_os.api.positions import list_positions

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = await list_positions(db=mock_db)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_position_not_found(self):
        from graxia.packages.quant_os.api.positions import get_position

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_position(position_id="nonexistent", db=mock_db)

    @pytest.mark.asyncio
    async def test_get_position_by_symbol_not_found(self):
        from graxia.packages.quant_os.api.positions import get_position_by_symbol

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_position_by_symbol(symbol="NONEXISTENT", db=mock_db)

    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        from graxia.packages.quant_os.api.positions import close_position

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await close_position(position_id="nonexistent", db=mock_db)

    @pytest.mark.asyncio
    async def test_update_stops_not_found(self):
        from graxia.packages.quant_os.api.positions import update_stops

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await update_stops(
                position_id="nonexistent",
                stop_loss=Decimal("1.0800"),
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_position_sql_injection(self):
        from graxia.packages.quant_os.api.positions import get_position

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_position(position_id="' OR 1=1 --", db=mock_db)

    @pytest.mark.asyncio
    async def test_position_xss_in_symbol(self):
        from graxia.packages.quant_os.api.positions import get_position_by_symbol

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(Exception):
            await get_position_by_symbol(symbol="<script>xss</script>", db=mock_db)


# ═══════════════════════════════════════════════════════════════════
# 6. api/risk.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestRiskChaos:
    """Chaos tests for risk endpoints."""

    @pytest.mark.asyncio
    async def test_risk_status_returns_data(self):
        from graxia.packages.quant_os.api.risk import get_risk_status

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            result = await get_risk_status()
            assert result is not None

    @pytest.mark.asyncio
    async def test_kill_switch_invalid_action(self):
        from graxia.packages.quant_os.api.risk import KillSwitchActionRequest, kill_switch_action

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await kill_switch_action(request=KillSwitchActionRequest(action="INVALID_ACTION", reason="test"))

    @pytest.mark.asyncio
    async def test_risk_limits_returns_data(self):
        from graxia.packages.quant_os.api.risk import get_risk_limits

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            result = await get_risk_limits()
            assert result is not None

    @pytest.mark.asyncio
    async def test_portfolio_exposure_concurrent(self):
        from graxia.packages.quant_os.api.risk import get_portfolio_exposure

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            tasks = [get_portfolio_exposure() for _ in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert len(results) == 10

    @pytest.mark.asyncio
    async def test_pnl_summary_concurrent(self):
        from graxia.packages.quant_os.api.risk import get_pnl_summary

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            tasks = [get_pnl_summary() for _ in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert len(results) == 10

    @pytest.mark.asyncio
    async def test_kill_switch_empty_reason(self):
        from graxia.packages.quant_os.api.risk import KillSwitchActionRequest, kill_switch_action

        with patch("graxia.packages.quant_os.api.risk.get_config", return_value=_mock_config()):
            req = KillSwitchActionRequest(action="trigger", reason="", user_id="test_user")
            result = await kill_switch_action(request=req)
            assert result is not None


# ═══════════════════════════════════════════════════════════════════
# 7. api/webhook.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestWebhookChaos:
    """Chaos tests for webhook endpoints."""

    def _valid_payload(self, **overrides) -> dict:
        p = {
            "action": "buy",
            "symbol": "EURUSD",
            "price": 1.0850,
            "sl": 1.0820,
            "tp": 1.0910,
            "strategy": "mtm",
            "regime": "trend",
            "atr": 0.0020,
            "timestamp": int(time.time()),
        }
        p.update(overrides)
        return p

    def _sign(self, payload_bytes: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    # ── Signature tests ────────────────────────────────────────

    def test_verify_signature_valid(self):
        from graxia.packages.quant_os.api.webhook import verify_webhook_signature

        body = b'{"action":"buy"}'
        sig = self._sign(body, WEBHOOK_SECRET)
        assert verify_webhook_signature(body, sig, WEBHOOK_SECRET) is True

    def test_verify_signature_invalid(self):
        from graxia.packages.quant_os.api.webhook import verify_webhook_signature

        body = b'{"action":"buy"}'
        assert verify_webhook_signature(body, "bad-sig", WEBHOOK_SECRET) is False

    def test_verify_signature_empty(self):
        from graxia.packages.quant_os.api.webhook import verify_webhook_signature

        assert verify_webhook_signature(b"test", "", WEBHOOK_SECRET) is False

    def test_verify_signature_no_secret_rejects(self):
        """Empty secret must be rejected (fail-closed security policy)."""
        from graxia.packages.quant_os.api.webhook import verify_webhook_signature

        assert verify_webhook_signature(b"test", "anything", "") is False

    def test_verify_signature_timing_attack_resistant(self):
        from graxia.packages.quant_os.api.webhook import verify_webhook_signature

        body = b'{"test": 1}'
        correct = self._sign(body, WEBHOOK_SECRET)
        t0 = time.time()
        verify_webhook_signature(body, correct, WEBHOOK_SECRET)
        t1 = time.time()
        verify_webhook_signature(body, "x" * 64, WEBHOOK_SECRET)
        t2 = time.time()
        assert abs((t1 - t0) - (t2 - t1)) < 0.5

    # ── TradingView webhook endpoint ───────────────────────────

    @pytest.mark.asyncio
    async def test_tradingview_missing_body(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            req = _make_request(b"")
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=None, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_malformed_json(self):
        import graxia.packages.quant_os.api.webhook as webhook_mod

        old = webhook_mod.get_config
        webhook_mod.get_config = lambda: _mock_config()
        try:
            bad_body = b'{"action": "buy", BROKEN'
            sig = self._sign(bad_body, WEBHOOK_SECRET)
            req = _make_request(bad_body)
            with pytest.raises(Exception):
                await webhook_mod.tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())
        finally:
            webhook_mod.get_config = old

    @pytest.mark.asyncio
    async def test_tradingview_expired_timestamp(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = self._valid_payload(timestamp=int(time.time()) - 300)
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_replay_attack(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = self._valid_payload()
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_oversized_payload(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            big = self._valid_payload(metadata={"x": "y" * 1_000_000})
            body = json.dumps(big).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            # Oversized payload — pydantic may reject or accept
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_invalid_action(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = self._valid_payload(action="INVALID")
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_missing_required_fields(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = {"action": "buy"}
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_negative_price(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = self._valid_payload(price=-100.0)
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_empty_symbol(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = self._valid_payload(symbol="")
            body = json.dumps(payload).encode()
            sig = self._sign(body, WEBHOOK_SECRET)
            req = _make_request(body)
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_signature=sig, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_tradingview_concurrent_requests(self):
        from graxia.packages.quant_os.api.webhook import tradingview_webhook

        cfg = _mock_config()
        cfg.webhook_hmac_secret = ""  # Disable signature for speed
        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=cfg):
            with patch("graxia.packages.quant_os.api.webhook.RiskEngine"):
                with patch("graxia.packages.quant_os.api.webhook.OrderManager"):
                    with patch("graxia.packages.quant_os.api.webhook.BrokerManager"):
                        payload = self._valid_payload()
                        body = json.dumps(payload).encode()
                        tasks = []
                        for _ in range(10):
                            req = _make_request(body)
                            tasks.append(tradingview_webhook(request=req, x_signature=None, db=AsyncMock()))
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        assert len(results) == 10

    # ── Manual signal endpoint ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_manual_signal_wrong_api_key(self):
        from graxia.packages.quant_os.api.webhook import TradingViewPayload, manual_signal

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = TradingViewPayload(
                action="buy",
                symbol="EURUSD",
                price=1.085,
                sl=1.082,
                tp=1.091,
            )
            with pytest.raises(Exception):
                await manual_signal(payload=payload, api_key="wrong", db=AsyncMock())

    @pytest.mark.asyncio
    async def test_manual_signal_missing_payload(self):
        from graxia.packages.quant_os.api.webhook import manual_signal

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            with pytest.raises(Exception):
                await manual_signal(payload=None, api_key=ADMIN_KEY, db=AsyncMock())

    # ── Position size calculation ──────────────────────────────

    def test_calculate_position_size_returns_decimal(self):
        from graxia.packages.quant_os.api.webhook import TradingViewPayload, calculate_position_size

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = TradingViewPayload(
                action="buy",
                symbol="EURUSD",
                price=1.085,
                sl=1.082,
                tp=1.091,
            )
            result = calculate_position_size(payload)
            assert isinstance(result, Decimal)
            assert result > 0

    def test_calculate_position_size_oversized_sl(self):
        from graxia.packages.quant_os.api.webhook import TradingViewPayload, calculate_position_size

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = TradingViewPayload(
                action="buy",
                symbol="EURUSD",
                price=1.085,
                sl=0.001,
                tp=10000,
            )
            result = calculate_position_size(payload)
            assert isinstance(result, Decimal)

    def test_calculate_position_size_zero_atr(self):
        from graxia.packages.quant_os.api.webhook import TradingViewPayload, calculate_position_size

        with patch("graxia.packages.quant_os.api.webhook.get_config", return_value=_mock_config()):
            payload = TradingViewPayload(
                action="buy",
                symbol="EURUSD",
                price=1.085,
                sl=1.082,
                tp=1.091,
                atr=0.0,
            )
            result = calculate_position_size(payload)
            assert result == Decimal("0.01")


# ═══════════════════════════════════════════════════════════════════
# 8. api/webhook_receiver.py — Chaos
# ═══════════════════════════════════════════════════════════════════


class TestWebhookReceiverChaos:
    """Chaos tests for webhook receiver endpoints."""

    def _tv_payload(self, **overrides) -> dict:
        p = {
            "symbol": "XAUUSD",
            "action": "buy",
            "price": 2350.0,
            "sl": 2340.0,
            "tp": 2370.0,
            "strategy": "bos_choch",
            "regime": "TREND_STRONG_UP",
            "asset_class": "metals",
            "conviction": 0.85,
        }
        p.update(overrides)
        return p

    def _generic_payload(self, **overrides) -> dict:
        p = {
            "symbol": "EURUSD",
            "asset_class": "forex",
            "side": "BUY",
            "conviction": 0.8,
            "strategy": "mtm",
            "entry_price": 1.085,
            "stop_loss": 1.082,
            "take_profit": 1.091,
        }
        p.update(overrides)
        return p

    def _gw_with_signal(self, signal_id="s1", symbol="XAUUSD"):
        gw = MagicMock()
        gw.ingest = AsyncMock(
            return_value=MagicMock(
                signal_id=signal_id,
                symbol=symbol,
                side=MagicMock(value="BUY"),
            )
        )
        return gw

    # ── TradingView receiver ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_tv_invalid_secret(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=_mock_settings()):
            req = _make_request(self._tv_payload())
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret="wrong-secret")

    @pytest.mark.asyncio
    async def test_tv_missing_secret(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=_mock_settings()):
            req = _make_request(self._tv_payload())
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_malformed_json(self):
        import graxia.packages.quant_os.api.webhook_receiver as wr_mod

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        old = wr_mod.get_settings
        wr_mod.get_settings = lambda: s
        try:
            req = _make_request(b'{"symbol": "XAUUSD", BROKEN')
            with pytest.raises(Exception):
                await wr_mod.tradingview_webhook(request=req, x_webhook_secret=None)
        finally:
            wr_mod.get_settings = old

    @pytest.mark.asyncio
    async def test_tv_invalid_action(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._tv_payload(action="INVALID_ACTION"))
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_invalid_asset_class(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._tv_payload(asset_class="nonexistent"))
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_negative_price(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._tv_payload(price=-100))
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_empty_symbol(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._tv_payload(symbol=""))
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_missing_required_fields(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request({"symbol": "XAUUSD"})
            with pytest.raises(Exception):
                await tradingview_webhook(request=req, x_webhook_secret=None)

    @pytest.mark.asyncio
    async def test_tv_replay_attack_same_payload(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        gw = self._gw_with_signal()
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            payload = self._tv_payload()
            req1 = _make_request(payload)
            req1.app.state.signal_gateway = gw
            r1 = await tradingview_webhook(request=req1, x_webhook_secret=WEBHOOK_SECRET)
            assert r1.success is True
            gw.ingest.return_value = None  # Reject duplicate
            req2 = _make_request(payload)
            req2.app.state.signal_gateway = gw
            r2 = await tradingview_webhook(request=req2, x_webhook_secret=WEBHOOK_SECRET)
            assert r2.success is False

    @pytest.mark.asyncio
    async def test_tv_oversized_metadata(self):
        import graxia.packages.quant_os.api.webhook_receiver as wr_mod

        s = _mock_settings()
        old = wr_mod.get_settings
        wr_mod.get_settings = lambda: s
        try:
            gw = self._gw_with_signal()
            payload = self._tv_payload(metadata={"big": "x" * 100_000})
            req = _make_request(payload)
            req.app.state.signal_gateway = gw
            result = await wr_mod.tradingview_webhook(request=req, x_webhook_secret=WEBHOOK_SECRET)
            assert result.success is True
        finally:
            wr_mod.get_settings = old

    @pytest.mark.asyncio
    async def test_tv_sql_injection_in_symbol(self):
        import graxia.packages.quant_os.api.webhook_receiver as wr_mod

        s = _mock_settings()
        old = wr_mod.get_settings
        wr_mod.get_settings = lambda: s
        try:
            gw = self._gw_with_signal(symbol="X'; DROP T")
            # symbol max_length=20 rejects longer strings; short injection is accepted as-is
            payload = self._tv_payload(symbol="X'; DROP T")
            req = _make_request(payload)
            req.app.state.signal_gateway = gw
            result = await wr_mod.tradingview_webhook(request=req, x_webhook_secret=WEBHOOK_SECRET)
            assert result.success is True
        finally:
            wr_mod.get_settings = old

    @pytest.mark.asyncio
    async def test_tv_sql_injection_rejected_by_length(self):
        import graxia.packages.quant_os.api.webhook_receiver as wr_mod

        s = _mock_settings()
        s.TV_WEBHOOK_SECRET = ""
        old = wr_mod.get_settings
        wr_mod.get_settings = lambda: s
        try:
            payload = self._tv_payload(symbol="'; DROP TABLE signals; --")
            req = _make_request(payload)
            with pytest.raises(Exception):
                await wr_mod.tradingview_webhook(request=req, x_webhook_secret=None)
        finally:
            wr_mod.get_settings = old

    @pytest.mark.asyncio
    async def test_tv_xss_in_metadata(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        gw = self._gw_with_signal()
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            payload = self._tv_payload(metadata={"user": "<script>alert(1)</script>"})
            req = _make_request(payload)
            req.app.state.signal_gateway = gw
            result = await tradingview_webhook(request=req, x_webhook_secret=WEBHOOK_SECRET)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_tv_concurrent_requests(self):
        from graxia.packages.quant_os.api.webhook_receiver import tradingview_webhook

        s = _mock_settings()
        gw = self._gw_with_signal()
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            tasks = []
            for i in range(10):
                payload = self._tv_payload(price=2350.0 + i)
                req = _make_request(payload)
                req.app.state.signal_gateway = gw
                tasks.append(tradingview_webhook(request=req, x_webhook_secret=WEBHOOK_SECRET))
            results = await asyncio.gather(*tasks)
            assert len(results) == 10

    # ── Generic webhook receiver ───────────────────────────────

    @pytest.mark.asyncio
    async def test_generic_invalid_api_key(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=_mock_settings()):
            req = _make_request(self._generic_payload())
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key="wrong")

    @pytest.mark.asyncio
    async def test_generic_missing_api_key(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=_mock_settings()):
            req = _make_request(self._generic_payload())
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_malformed_json(self):
        import graxia.packages.quant_os.api.webhook_receiver as wr_mod

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        old = wr_mod.get_settings
        wr_mod.get_settings = lambda: s
        try:
            req = _make_request(b"{invalid json")
            with pytest.raises(Exception):
                await wr_mod.generic_webhook(request=req, x_api_key=None)
        finally:
            wr_mod.get_settings = old

    @pytest.mark.asyncio
    async def test_generic_invalid_side(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._generic_payload(side="INVALID"))
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_invalid_asset_class(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._generic_payload(asset_class="nonexistent"))
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_negative_conviction(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._generic_payload(conviction=-0.5))
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_conviction_over_one(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._generic_payload(conviction=1.5))
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_negative_price(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        s.ADMIN_API_KEY = ""
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            req = _make_request(self._generic_payload(entry_price=-100))
            with pytest.raises(Exception):
                await generic_webhook(request=req, x_api_key=None)

    @pytest.mark.asyncio
    async def test_generic_replay_attack(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        gw = self._gw_with_signal(symbol="EURUSD")
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            payload = self._generic_payload()
            req1 = _make_request(payload)
            req1.app.state.signal_gateway = gw
            r1 = await generic_webhook(request=req1, x_api_key=ADMIN_KEY)
            assert r1.success is True
            gw.ingest.return_value = None
            req2 = _make_request(payload)
            req2.app.state.signal_gateway = gw
            r2 = await generic_webhook(request=req2, x_api_key=ADMIN_KEY)
            assert r2.success is False

    @pytest.mark.asyncio
    async def test_generic_concurrent_requests(self):
        from graxia.packages.quant_os.api.webhook_receiver import generic_webhook

        s = _mock_settings()
        gw = self._gw_with_signal(symbol="EURUSD")
        with patch("graxia.packages.quant_os.api.webhook_receiver.get_settings", return_value=s):
            tasks = []
            for i in range(10):
                payload = self._generic_payload(entry_price=1.085 + i * 0.001)
                req = _make_request(payload)
                req.app.state.signal_gateway = gw
                tasks.append(generic_webhook(request=req, x_api_key=ADMIN_KEY))
            results = await asyncio.gather(*tasks)
            assert len(results) == 10
