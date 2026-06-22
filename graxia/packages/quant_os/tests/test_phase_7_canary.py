import pytest
from canary.config import CanaryConfig
from canary.broker_validator import BrokerValidator, BrokerValidationReport
from canary.order_lifecycle import (
    CanaryOrder, OrderState, PostFillVerifier, TERMINAL_STATES, VALID_TRANSITIONS
)

class TestCanaryConfig:
    def test_default_config(self):
        c = CanaryConfig()
        assert c.execution_enabled is False
        assert c.account_mode_required == "DEMO"
        assert c.max_open_positions == 1
    
    def test_validate_valid(self):
        c = CanaryConfig()
        ok, issues = c.validate()
        assert ok is True
    
    def test_validate_non_demo(self):
        c = CanaryConfig(account_mode_required="LIVE")
        ok, issues = c.validate()
        assert ok is False
    
    def test_validate_auto_resume(self):
        c = CanaryConfig(auto_resume_after_kill_switch=True)
        ok, issues = c.validate()
        assert ok is False
    
    def test_check_symbol_allowed(self):
        c = CanaryConfig()
        ok, reason = c.check_symbol("XAUUSD")
        assert ok is True
    
    def test_check_symbol_not_allowed(self):
        c = CanaryConfig()
        ok, reason = c.check_symbol("BTCUSD")
        assert ok is False
    
    def test_check_strategy_allowed(self):
        c = CanaryConfig()
        ok, reason = c.check_strategy("liquidity_sweep_locked_version")
        assert ok is True
    
    def test_fingerprint(self):
        c = CanaryConfig()
        f = c.fingerprint()
        assert len(f) == 64

class TestBrokerValidator:
    def test_account_mode_demo(self):
        v = BrokerValidator()
        check = v.validate_account_mode("DEMO")
        assert check.passed is True
    
    def test_account_mode_live(self):
        v = BrokerValidator()
        check = v.validate_account_mode("LIVE")
        assert check.passed is False
    
    def test_symbol_valid(self):
        v = BrokerValidator()
        check = v.validate_symbol("XAUUSD", {"contract_size": 100})
        assert check.passed is True
    
    def test_symbol_no_specs(self):
        v = BrokerValidator()
        check = v.validate_symbol("XAUUSD", {})
        assert check.passed is False
    
    def test_stop_loss_valid(self):
        v = BrokerValidator()
        check = v.validate_stop_loss({"stop_loss": 2340.0})
        assert check.passed is True
    
    def test_stop_loss_missing(self):
        v = BrokerValidator()
        check = v.validate_stop_loss({"stop_loss": 0})
        assert check.passed is False
    
    def test_position_limits(self):
        v = BrokerValidator()
        check = v.validate_position_limits(0, 1)
        assert check.passed is True
    
    def test_position_limit_exceeded(self):
        v = BrokerValidator()
        check = v.validate_position_limits(1, 1)
        assert check.passed is False

class TestCanaryOrder:
    def test_create(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        assert o.state == OrderState.SIGNAL_CREATED
    
    def test_valid_transition(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        ok, msg = o.transition(OrderState.RISK_ACCEPTED)
        assert ok is True
        assert o.state == OrderState.RISK_ACCEPTED
    
    def test_invalid_transition(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        ok, msg = o.transition(OrderState.FILLED)
        assert ok is False
        assert "INVALID_TRANSITION" in msg
    
    def test_terminal_state_blocks(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        o.state = OrderState.AUDITED
        ok, msg = o.transition(OrderState.RISK_ACCEPTED)
        assert ok is False
        assert "INVALID_TRANSITION" in msg
    
    def test_happy_path_to_audited(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        steps = [
            OrderState.RISK_ACCEPTED,
            OrderState.ORDER_INTENT_CREATED,
            OrderState.ORDER_CHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.BROKER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
            OrderState.CLOSED,
            OrderState.DEAL_RECONCILED,
            OrderState.AUDITED,
        ]
        for step in steps:
            ok, msg = o.transition(step)
            assert ok is True, f"Failed at {step}: {msg}"
        assert o.is_terminal() is True
    
    def test_critical_incident(self):
        o = CanaryOrder(
            order_id="ORD-001", symbol="XAUUSD", direction="BUY",
            volume=0.1, entry_price=2350.0, stop_loss=2340.0,
            take_profit=2370.0, strategy_id="strat_1",
        )
        ok, msg = o.transition(OrderState.CRITICAL_INCIDENT)
        assert ok is True
        assert o.is_terminal() is True

class TestPostFillVerifier:
    def test_fill_price_verified(self):
        v = PostFillVerifier()
        ok, msg = v.verify_fill_price(2350.0, 2350.005)
        assert ok is True
    
    def test_fill_price_mismatch(self):
        v = PostFillVerifier()
        ok, msg = v.verify_fill_price(2350.0, 2355.0)
        assert ok is False
    
    def test_sl_tp_verified(self):
        v = PostFillVerifier()
        ok, msg = v.verify_sl_tp_exists(2340.0, 2370.0, 2340.0, 2370.0)
        assert ok is True
    
    def test_sl_mismatch(self):
        v = PostFillVerifier()
        ok, msg = v.verify_sl_tp_exists(2340.0, 2370.0, 2335.0, 2370.0)
        assert ok is False
