"""Phase 10 integration tests — micro-live canary."""
from graxia.packages.quant_os.canary.micro_live_policy import MicroLivePolicy
from graxia.packages.quant_os.canary.emergency_kill_switch import EmergencyKillSwitch


def test_micro_live_policy_exists():
    """MicroLivePolicy must exist."""
    policy = MicroLivePolicy()
    assert policy.max_symbols == 1
    assert policy.max_orders_per_day == 1
    assert policy.risk_per_trade_bps == 5


def test_micro_live_policy_validates():
    """MicroLivePolicy must validate."""
    policy = MicroLivePolicy()
    ok, issues = policy.validate()
    assert ok is True


def test_micro_live_policy_rejects_violations():
    """MicroLivePolicy must reject violations."""
    policy = MicroLivePolicy(max_symbols=2)
    ok, issues = policy.validate()
    assert ok is False


def test_emergency_kill_switch_works():
    """EmergencyKillSwitch must work."""
    switch = EmergencyKillSwitch()
    assert not switch.is_active()
    switch.activate("test reason")
    assert switch.is_active()
    switch.deactivate()
    assert not switch.is_active()


def test_emergency_kill_switch_state():
    """EmergencyKillSwitch must report state."""
    switch = EmergencyKillSwitch()
    state = switch.get_state()
    assert state.active is False
