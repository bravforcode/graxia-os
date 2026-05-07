"""Tests for Quant OS core module"""

import pytest
from decimal import Decimal

from graxia.packages.quant_os.core.golden_rules import GOLDEN_RULES, validate_golden_rules
from graxia.packages.quant_os.core.enums import OrderStatus, OrderSide, TradingMode, KillSwitchType
from graxia.packages.quant_os.core.config import QuantConfig, get_config
from graxia.packages.quant_os.core.exceptions import RiskViolationError, DuplicateOrderError


class TestGoldenRules:
    """Test golden rules enforcement"""

    def test_live_trading_default_false(self):
        """Live trading must be explicitly enabled"""
        assert GOLDEN_RULES.LIVE_TRADING_DEFAULT == False

    def test_ai_cannot_submit_order(self):
        """AI cannot directly submit orders"""
        assert GOLDEN_RULES.AI_CANNOT_SUBMIT_ORDER == True

    def test_paper_minimum_days(self):
        """Paper trading minimum 60 days"""
        assert GOLDEN_RULES.PAPER_MIN_TRADING_DAYS >= 60

    def test_max_risk_per_trade(self):
        """Max 1% risk per trade"""
        assert GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT == 1.0

    def test_hard_stop_drawdown(self):
        """15% hard stop drawdown"""
        assert GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT == 15.0

    def test_validate_golden_rules(self):
        """All golden rules validation checks pass"""
        result = validate_golden_rules()
        assert result["all_checks_passed"] == True


class TestEnums:
    """Test enum definitions"""

    def test_order_status_transitions(self):
        """Order status enum has valid values"""
        assert OrderStatus.CREATED.value == "CREATED"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.REJECTED.value == "REJECTED"

    def test_trading_mode_values(self):
        """Trading mode enum values"""
        assert TradingMode.PAPER.value == "PAPER"
        assert TradingMode.LIVE_MICRO.value == "LIVE_MICRO"


class TestConfig:
    """Test configuration"""

    def test_default_config(self):
        """Default config is valid"""
        config = QuantConfig()
        assert config.trading_mode == TradingMode.PAPER
        assert config.live_trading_enabled == False

    def test_config_enforces_limits(self):
        """Config enforces risk limits"""
        config = QuantConfig()
        limits = config.get_mode_risk_limits()
        assert "max_risk_per_trade_pct" in limits


class TestExceptions:
    """Test custom exceptions"""

    def test_risk_violation_error(self):
        """Risk violation error includes violation type"""
        error = RiskViolationError("Risk too high", violation_type="MAX_POSITION")
        assert error.violation_type == "MAX_POSITION"
        assert error.error_code == "RISK_VIOLATION"

    def test_duplicate_order_error(self):
        """Duplicate order error includes idempotency key"""
        error = DuplicateOrderError("Duplicate detected", idempotency_key="abc123")
        assert error.idempotency_key == "abc123"
