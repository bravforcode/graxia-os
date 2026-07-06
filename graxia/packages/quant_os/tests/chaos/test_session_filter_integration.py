"""Session filter integration tests for SignalGateway.

Verifies that signals are blocked outside trading sessions and allowed during
sessions, while existing behavior is preserved when no filter is attached.

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_session_filter_integration.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure quant_os is importable as a package
_PACKAGES = Path(__file__).resolve().parent.parent.parent.parent
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from graxia.packages.quant_os.core.session_filter import SessionFilter
from graxia.packages.quant_os.core.signal_gateway import (
    Signal,
    SignalGateway,
    SignalSource,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RAW = {
    "symbol": "XAUUSD",
    "asset_class": "forex",
    "side": "BUY",
    "conviction": 0.8,
    "strategy": "momentum_v1",
    "entry_price": 2350.0,
    "stop_loss": 2340.0,
    "take_profit": 2370.0,
    "timestamp": "2026-06-29T10:00:00+00:00",  # London session
}


def _make_raw(timestamp_iso: str) -> dict:
    """Return a valid raw payload with the given timestamp."""
    return {**VALID_RAW, "timestamp": timestamp_iso}


async def _ingest(gateway: SignalGateway, raw: dict) -> Signal | None:
    return await gateway.ingest(raw, SignalSource.PYTHON)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionFilterBlockedOutsideSession:
    """Signal blocked when timestamp falls outside all sessions (21:00-00:00 UTC)."""

    async def test_signal_blocked_outside_session(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()  # any instance enables the gate
        gw = SignalGateway(queue=queue, session_filter=sf)

        # 22:00 UTC — market closed
        raw = _make_raw("2026-06-29T22:00:00+00:00")
        result = await _ingest(gw, raw)

        assert result is None
        assert queue.empty()

    async def test_blocked_between_sessions(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()
        gw = SignalGateway(queue=queue, session_filter=sf)

        # 21:30 UTC — after NY close, before Asian open
        raw = _make_raw("2026-06-29T21:30:00+00:00")
        result = await _ingest(gw, raw)

        assert result is None
        assert queue.empty()


@pytest.mark.asyncio
class TestSessionFilterAllowedDuringSession:
    """Signal accepted when timestamp falls within a trading session."""

    async def test_signal_allowed_london_session(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()
        gw = SignalGateway(queue=queue, session_filter=sf)

        # 10:00 UTC — London session
        raw = _make_raw("2026-06-29T10:00:00+00:00")
        result = await _ingest(gw, raw)

        assert result is not None
        assert result.symbol == "XAUUSD"
        assert not queue.empty()

    async def test_signal_allowed_ny_session(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()
        gw = SignalGateway(queue=queue, session_filter=sf)

        # 15:00 UTC — overlap (London + NY)
        raw = _make_raw("2026-06-29T15:00:00+00:00")
        result = await _ingest(gw, raw)

        assert result is not None
        assert not queue.empty()

    async def test_signal_allowed_asian_session(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()
        gw = SignalGateway(queue=queue, session_filter=sf)

        # 04:00 UTC — Asian session
        raw = _make_raw("2026-06-29T04:00:00+00:00")
        result = await _ingest(gw, raw)

        assert result is not None
        assert not queue.empty()


@pytest.mark.asyncio
class TestSessionFilterDisabled:
    """When no session_filter is passed, all signals are accepted (legacy behavior)."""

    async def test_no_filter_allows_all_times(self):
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        gw = SignalGateway(queue=queue)  # no session_filter

        # 22:00 UTC — would be blocked if filter were active
        raw = _make_raw("2026-06-29T22:00:00+00:00")
        result = await _ingest(gw, raw)

        assert result is not None
        assert not queue.empty()


@pytest.mark.asyncio
class TestSessionFilterAuditLog:
    """Verify audit log records signal.blocked_by_session events."""

    async def test_blocked_signal_appends_audit(self, tmp_path):
        audit_path = tmp_path / "audit_log.jsonl"
        queue: asyncio.Queue[Signal] = asyncio.Queue()
        sf = SessionFilter()
        gw = SignalGateway(queue=queue, session_filter=sf)

        raw = _make_raw("2026-06-29T22:00:00+00:00")

        with patch("graxia.packages.quant_os.core.signal_gateway.AUDIT_LOG_PATH", audit_path):
            result = await _ingest(gw, raw)

        assert result is None
        assert audit_path.exists()
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        blocked = [json.loads(l) for l in lines if "blocked_by_session" in l]
        assert len(blocked) == 1
        assert blocked[0]["event"] == "signal.blocked_by_session"
        assert blocked[0]["session"] == "closed"
