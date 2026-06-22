"""Tests for Phase 10 — Micro-live canary policy and emergency kill switch."""
import json
import tempfile
from pathlib import Path

from graxia.packages.quant_os.canary.micro_live_policy import MicroLivePolicy
from graxia.packages.quant_os.canary.emergency_kill_switch import EmergencyKillSwitch


def test_micro_live_policy_default():
    p = MicroLivePolicy()
    ok, issues = p.validate()
    assert ok is True
    assert issues == []


def test_micro_live_policy_validate():
    p = MicroLivePolicy(
        max_symbols=1,
        max_open_positions=1,
        max_orders_per_day=1,
        risk_per_trade_bps=5,
        max_daily_loss_bps=20,
        max_weekly_loss_bps=50,
        max_total_drawdown_bps=100,
        emergency_kill_switch=True,
    )
    ok, issues = p.validate()
    assert ok is True
    assert issues == []


def test_micro_live_policy_rejects_high_risk():
    p = MicroLivePolicy(max_symbols=5, risk_per_trade_bps=10, emergency_kill_switch=False)
    ok, issues = p.validate()
    assert ok is False
    assert len(issues) == 3


def test_emergency_kill_switch_activate():
    ks = EmergencyKillSwitch()
    assert ks.is_active() is False
    ks.activate("testing", "unit_test")
    assert ks.is_active() is True
    state = ks.get_state()
    assert state.reason == "testing"
    assert state.activated_by == "unit_test"
    assert state.activated_at != ""


def test_emergency_kill_switch_deactivate():
    ks = EmergencyKillSwitch()
    ks.activate("testing")
    assert ks.is_active() is True
    ks.deactivate()
    assert ks.is_active() is False


def test_emergency_kill_switch_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = str(Path(tmp) / "kill_switch.json")
        ks = EmergencyKillSwitch(state_file)
        ks.activate("persist_test")
        assert ks.is_active() is True

        ks2 = EmergencyKillSwitch(state_file)
        assert ks2.is_active() is True
        assert ks2.get_state().reason == "persist_test"
