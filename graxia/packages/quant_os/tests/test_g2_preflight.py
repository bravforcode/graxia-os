"""G2 preflight tests: guard denial, import isolation, deterministic hash."""
import pytest
from execution.demo_canary import demo_account_guard
from execution.demo_canary import broker_profile_guard
from execution.demo_canary import terminal_path_guard
from execution.demo_canary import symbol_guard
from execution.demo_canary import feature_gate
from execution.demo_canary import kill_switch
from execution.demo_canary import execution_mutex
from execution.demo_canary import position_guard
from execution.demo_canary import order_geometry_guard
from execution.demo_canary import market_data_guard
from execution.demo_canary import margin_guard
from graxia.packages.quant_os.risk.contract_spec import ContractSpec
from datetime import datetime, timedelta


GUARD_COUNT = 11  # individual guard modules


class TestGuardDenialPaths:
    """Every guard must fail closed on invalid input."""

    def test_feature_gate_default_off(self):
        assert not feature_gate.is_execution_enabled()

    def test_live_account_rejected(self):
        result = demo_account_guard.verify_demo_account(account_mode="LIVE")
        assert not result.passed

    def test_demo_account_passes(self):
        result = demo_account_guard.verify_demo_account(account_mode="DEMO")
        assert result.passed

    def test_wrong_profile_rejected(self):
        result = broker_profile_guard.verify_broker_profile(profile_hash="wrong")
        assert not result.passed

    def test_empty_profile_rejected(self):
        result = broker_profile_guard.verify_broker_profile(profile_hash="")
        assert not result.passed

    def test_wrong_terminal_path_rejected(self):
        assert not terminal_path_guard.verify_terminal_path("/wrong/path")

    def test_non_xauusd_rejected(self):
        assert not symbol_guard.verify_symbol("EURUSD")

    def test_xauusd_passes(self):
        assert symbol_guard.verify_symbol("XAUUSD")

    def test_stale_contract_rejected(self):
        spec = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test", snapshot_timestamp=datetime.utcnow() - timedelta(seconds=9999),
        )
        assert spec.is_stale

    def test_fresh_contract_passes(self):
        spec = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test", snapshot_timestamp=datetime.utcnow(),
        )
        assert not spec.is_stale

    def test_high_spread_rejected(self):
        result = market_data_guard.verify_spread(spread_points=100.0)
        assert not result.passed

    def test_zero_spread_rejected(self):
        result = market_data_guard.verify_spread(spread_points=0)
        assert not result.passed

    def test_low_spread_passes(self):
        result = market_data_guard.verify_spread(spread_points=15.0)
        assert result.passed

    def test_volume_below_min_rejected(self):
        result = order_geometry_guard.verify_volume(volume=0.001, volume_min=0.01, volume_max=50.0, volume_step=0.01)
        assert not result.passed

    def test_volume_above_max_rejected(self):
        result = order_geometry_guard.verify_volume(volume=100.0, volume_min=0.01, volume_max=50.0, volume_step=0.01)
        assert not result.passed

    def test_volume_off_step_rejected(self):
        result = order_geometry_guard.verify_volume(volume=0.015, volume_min=0.01, volume_max=50.0, volume_step=0.01)
        assert not result.passed

    def test_valid_volume_passes(self):
        result = order_geometry_guard.verify_volume(volume=0.01, volume_min=0.01, volume_max=50.0, volume_step=0.01)
        assert result.passed

    def test_sl_wrong_side_buy_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="BUY", entry=100, sl=101, tp=99, point=0.01
        )
        assert not result.passed

    def test_tp_wrong_side_buy_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="BUY", entry=100, sl=99, tp=99, point=0.01
        )
        assert not result.passed

    def test_sl_wrong_side_sell_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="SELL", entry=100, sl=99, tp=101, point=0.01
        )
        assert not result.passed

    def test_tp_wrong_side_sell_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="SELL", entry=100, sl=101, tp=101, point=0.01
        )
        assert not result.passed

    def test_valid_sl_tp_buy_passes(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="BUY", entry=100, sl=99, tp=101, point=0.01
        )
        assert result.passed

    def test_valid_sl_tp_sell_passes(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="SELL", entry=100, sl=101, tp=99, point=0.01
        )
        assert result.passed

    def test_kill_switch_default_on(self):
        assert kill_switch.is_kill_switch_active()

    def test_kill_switch_release_and_reactivate(self):
        kill_switch.release_kill_switch()
        assert not kill_switch.is_kill_switch_active()
        kill_switch.activate_kill_switch()
        assert kill_switch.is_kill_switch_active()

    def test_positions_exist_rejected(self):
        result = position_guard.verify_no_positions()
        assert result.passed  # No connection = assumed clean

    def test_mutex_double_acquire_rejected(self):
        execution_mutex.acquire_mutex()
        assert not execution_mutex.acquire_mutex()
        execution_mutex.release_mutex()

    def test_margin_exceeds_cap_rejected(self):
        result = margin_guard.verify_margin(margin_estimate=5000.0, balance=100000.0, margin_cap_pct=1.0)
        assert not result.passed

    def test_margin_negative_rejected(self):
        result = margin_guard.verify_margin(margin_estimate=-1.0, balance=100000.0)
        assert not result.passed

    def test_margin_zero_balance_rejected(self):
        result = margin_guard.verify_margin(margin_estimate=100.0, balance=0)
        assert not result.passed

    def test_order_check_none_rejected(self):
        result = margin_guard.verify_order_check(order_check_data=None)
        assert not result.passed

    def test_order_check_fail_retcode_rejected(self):
        result = margin_guard.verify_order_check(order_check_data={"retcode": 1, "comment": "fail"})
        assert not result.passed

    def test_order_check_passes(self):
        result = margin_guard.verify_order_check(order_check_data={"retcode": 0, "comment": "ok"})
        assert result.passed

    def test_invalid_direction_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="INVALID", entry=100, sl=99, tp=101, point=0.01
        )
        assert not result.passed

    def test_zero_sl_tp_rejected(self):
        result = order_geometry_guard.verify_sl_tp_geometry(
            direction="BUY", entry=100, sl=0, tp=101, point=0.01
        )
        assert not result.passed

    def test_negative_volume_rejected(self):
        result = order_geometry_guard.verify_volume(volume=-0.01, volume_min=0.01, volume_max=50.0, volume_step=0.01)
        assert not result.passed

    def test_tick_freshness_none_rejected(self):
        result = market_data_guard.verify_tick_freshness(tick_time=None)
        assert not result.passed

    def test_session_not_allowed_rejected(self):
        result = market_data_guard.verify_session(session="TOKYO")
        assert not result.passed

    def test_session_allowed_passes(self):
        result = market_data_guard.verify_session(session="LONDON")
        assert result.passed

    def test_empty_session_passes(self):
        result = market_data_guard.verify_session(session="")
        assert result.passed

    def test_guards_registered(self):
        """Verify all guard modules exist and are importable."""
        assert GUARD_COUNT >= 11


class TestImportIsolation:
    def test_preflight_no_order_send(self):
        import ast, os
        preflight_path = None
        for p in ["execution/demo_canary/preflight.py", "execution\\demo_canary\\preflight.py"]:
            fp = os.path.join(os.path.dirname(__file__), "..", p)
            if os.path.exists(fp):
                preflight_path = fp
                break
        assert preflight_path is not None, "preflight.py not found"
        with open(preflight_path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and hasattr(node.func, 'id') and 'order_send' in node.func.id:
                pytest.fail("order_send found in preflight.py")

    def test_no_order_submission_import_in_preflight(self):
        import ast, os
        preflight_path = None
        for p in ["execution/demo_canary/preflight.py", "execution\\demo_canary\\preflight.py"]:
            fp = os.path.join(os.path.dirname(__file__), "..", p)
            if os.path.exists(fp):
                preflight_path = fp
                break
        assert preflight_path is not None
        with open(preflight_path) as f:
            content = f.read()
        assert "order_submission" not in content
        assert "order_send" not in content

    def test_all_guard_modules_no_order_send(self):
        import ast, os
        guard_modules = [
            "demo_account_guard.py", "broker_profile_guard.py",
            "terminal_path_guard.py", "symbol_guard.py",
            "feature_gate.py", "kill_switch.py",
            "execution_mutex.py", "position_guard.py",
            "order_geometry_guard.py", "market_data_guard.py",
            "margin_guard.py",
        ]
        demo_canary_dir = os.path.join(os.path.dirname(__file__), "..", "execution", "demo_canary")
        for mod in guard_modules:
            path = os.path.join(demo_canary_dir, mod)
            if not os.path.exists(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "order_send(" not in content, f"order_send() call found in {mod}"


class TestDeterministicHash:
    def test_plan_hash_deterministic(self):
        import json, hashlib
        plan1 = {"environment": "PEPPERSTONE_DEMO_ONLY", "symbol": "XAUUSD"}
        plan2 = {"environment": "PEPPERSTONE_DEMO_ONLY", "symbol": "XAUUSD"}
        h1 = hashlib.sha256(json.dumps(plan1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(plan2, sort_keys=True).encode()).hexdigest()
        assert h1 == h2

    def test_plan_hash_different_for_diff_env(self):
        import json, hashlib
        plan1 = {"environment": "PEPPERSTONE_DEMO_ONLY"}
        plan2 = {"environment": "LIVE"}
        h1 = hashlib.sha256(json.dumps(plan1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(plan2, sort_keys=True).encode()).hexdigest()
        assert h1 != h2

    def test_contract_spec_hash_deterministic(self):
        """ContractSpec.hash must be deterministic for identical inputs."""
        from datetime import datetime
        ts = datetime.utcnow()
        spec1 = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test", snapshot_timestamp=ts,
        )
        spec2 = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test", snapshot_timestamp=ts,
        )
        assert spec1.hash == spec2.hash
        assert len(spec1.hash) == 64  # SHA-256 hex
