"""Test all execution guards."""
from execution.demo_canary import demo_account_guard
from execution.demo_canary import broker_profile_guard
from execution.demo_canary import terminal_path_guard
from execution.demo_canary import symbol_guard
from execution.demo_canary import feature_gate
from execution.demo_canary import kill_switch
from execution.demo_canary import execution_mutex

class TestDemoAccountGuard:
    def test_demo_account_passes(self):
        result = demo_account_guard.verify_demo_account(account_mode="DEMO")
        assert result.passed
    
    def test_live_account_rejected(self):
        result = demo_account_guard.verify_demo_account(account_mode="LIVE")
        assert not result.passed

class TestBrokerProfileGuard:
    def test_correct_hash_passes(self):
        result = broker_profile_guard.verify_broker_profile(
            "b2a952e42de3af5e5c5e8eecfaec788c794f9cb3bb75d1b407badf26694ef3cb"
        )
        assert result.passed
    
    def test_wrong_hash_rejected(self):
        result = broker_profile_guard.verify_broker_profile("wrong")
        assert not result.passed
    
    def test_empty_hash_rejected(self):
        result = broker_profile_guard.verify_broker_profile("")
        assert not result.passed

class TestTerminalPathGuard:
    def test_correct_path_passes(self):
        from execution.demo_canary.terminal_path_guard import APPROVED_TERMINAL_PATH_HASH
        import hashlib
        path = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
        assert hashlib.sha256(path.encode()).hexdigest() == APPROVED_TERMINAL_PATH_HASH
    
    def test_wrong_path_rejected(self):
        assert not terminal_path_guard.verify_terminal_path("wrong_path")

class TestSymbolGuard:
    def test_xauusd_passes(self):
        assert symbol_guard.verify_symbol("XAUUSD")
    
    def test_eurusd_rejected(self):
        assert not symbol_guard.verify_symbol("EURUSD")

class TestFeatureGate:
    def test_default_off(self):
        assert not feature_gate.is_execution_enabled()
    
    def test_enable_toggle(self):
        feature_gate.enable_execution()
        assert feature_gate.is_execution_enabled()
        feature_gate.disable_execution()
        assert not feature_gate.is_execution_enabled()

class TestKillSwitch:
    def test_default_active(self):
        assert kill_switch.is_kill_switch_active()
    
    def test_release_and_reactivate(self):
        kill_switch.release_kill_switch()
        assert not kill_switch.is_kill_switch_active()
        kill_switch.activate_kill_switch()
        assert kill_switch.is_kill_switch_active()

class TestExecutionMutex:
    def test_acquire_release(self):
        assert execution_mutex.acquire_mutex()
        assert execution_mutex.is_mutex_held()
        execution_mutex.release_mutex()
        assert not execution_mutex.is_mutex_held()
    
    def test_double_acquire_fails(self):
        execution_mutex.acquire_mutex()
        assert not execution_mutex.acquire_mutex()
        execution_mutex.release_mutex()
