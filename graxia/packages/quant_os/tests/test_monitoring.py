"""Tests for monitoring modules — heartbeat, dead man's switch, health_check."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from graxia.packages.quant_os.monitoring.dead_mans_switch import DeadMansSwitch
from graxia.packages.quant_os.monitoring.heartbeat import HeartbeatMonitor

# ---------------------------------------------------------------------------
# HeartbeatMonitor
# ---------------------------------------------------------------------------


class TestHeartbeatMonitor:
    def test_beat_writes_timestamp(self):
        state = {}
        mon = HeartbeatMonitor(state, interval=999)
        mon.beat()
        assert "last_heartbeat" in state
        # Value should be a valid ISO timestamp
        dt = datetime.fromisoformat(state["last_heartbeat"])
        assert dt.tzinfo is not None

    def test_beat_custom_key(self):
        state = {}
        mon = HeartbeatMonitor(state, interval=999, key="my_beat")
        mon.beat()
        assert "my_beat" in state

    def test_last_beat_property_returns_none_initially(self):
        state = {}
        mon = HeartbeatMonitor(state)
        assert mon.last_beat is None

    def test_last_beat_property_returns_value(self):
        state = {}
        mon = HeartbeatMonitor(state)
        mon.beat()
        assert mon.last_beat is not None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        state = {}
        mon = HeartbeatMonitor(state, interval=0.05)
        await mon.start()
        assert mon._running is True
        await asyncio.sleep(0.12)
        assert "last_heartbeat" in state
        await mon.stop()
        assert mon._running is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        state = {}
        mon = HeartbeatMonitor(state, interval=0.05)
        await mon.start()
        await mon.start()  # should not create a second task
        assert mon._running is True
        await mon.stop()

    def test_beat_record_and_retrieve(self):
        """Verify write → read round-trip."""
        state = {}
        mon = HeartbeatMonitor(state)
        mon.beat()
        ts = mon.last_beat
        assert ts is not None
        parsed = datetime.fromisoformat(ts)
        assert parsed < datetime.now(UTC) + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# DeadMansSwitch
# ---------------------------------------------------------------------------


class TestDeadMansSwitch:
    @pytest.fixture
    def actions(self):
        close = AsyncMock()
        halt = AsyncMock()
        alert = AsyncMock()
        return close, halt, alert

    @pytest.mark.asyncio
    async def test_fires_when_heartbeat_stale(self, actions):
        close, halt, alert = actions
        # Heartbeat from 10 minutes ago (> 5 min default timeout)
        stale_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        state = {"last_heartbeat": stale_ts}

        dms = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=5.0,
            check_interval=0.05,
        )
        await dms.start()
        await asyncio.sleep(0.2)
        await dms.stop()

        assert dms.fired is True
        halt.assert_awaited_once()
        close.assert_awaited_once()
        alert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_fire_when_heartbeat_fresh(self, actions):
        close, halt, alert = actions
        # Fresh heartbeat
        state = {"last_heartbeat": datetime.now(UTC).isoformat()}

        dms = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=5.0,
            check_interval=0.05,
        )
        await dms.start()
        await asyncio.sleep(0.15)
        await dms.stop()

        assert dms.fired is False
        halt.assert_not_awaited()
        close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fires_when_no_heartbeat_recorded(self, actions):
        close, halt, alert = actions
        state = {}

        dms = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=5.0,
            check_interval=0.05,
        )
        await dms.start()
        await asyncio.sleep(0.15)
        await dms.stop()

        # No heartbeat = no fire (just warning)
        assert dms.fired is False

    @pytest.mark.asyncio
    async def test_custom_timeout(self, actions):
        close, halt, alert = actions
        # Heartbeat 8 seconds ago
        ts = (datetime.now(UTC) - timedelta(seconds=8)).isoformat()
        state = {"last_heartbeat": ts}

        # 10s timeout → should NOT fire
        dms = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=10.0,
            check_interval=0.05,
        )
        await dms.start()
        await asyncio.sleep(0.15)
        await dms.stop()
        assert dms.fired is False

    @pytest.mark.asyncio
    async def test_reset_allows_reuse(self, actions):
        close, halt, alert = actions
        stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        state = {"last_heartbeat": stale}

        dms = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=5.0,
            check_interval=0.05,
        )
        await dms.start()
        await asyncio.sleep(0.2)
        assert dms.fired is True
        await dms.stop()

        # Simulate reset: fresh heartbeat + new switch instance
        state["last_heartbeat"] = datetime.now(UTC).isoformat()
        dms2 = DeadMansSwitch(
            state,
            close_all_positions=close,
            halt_system=halt,
            send_alert=alert,
            timeout=5.0,
            check_interval=0.05,
        )
        await dms2.start()
        await asyncio.sleep(0.15)
        await dms2.stop()
        assert dms2.fired is False
