"""
Test BotConfig default values are within safe/conservative ranges.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pytest
from graxia.packages.quant_os.gold_bot.core.config import BotConfig


def test_default_sl_distance():
    """Default sl_distance_points should be >= 37."""
    cfg = BotConfig()
    assert cfg.sl_distance_points >= 37


def test_default_risk_percent():
    """Default max_risk_per_trade_pct should be <= 1.0 (100% of capital as fraction)."""
    cfg = BotConfig()
    assert cfg.max_risk_per_trade_pct <= 1.0


def test_default_max_trades():
    """Default max_positions should be <= 5."""
    cfg = BotConfig()
    assert cfg.max_positions <= 5


def test_default_min_score():
    """Default min_score_to_trade should be >= 200."""
    cfg = BotConfig()
    assert cfg.min_score_to_trade >= 200


def test_default_rr_ratio():
    """Default risk_reward_ratio should be >= 1.0."""
    cfg = BotConfig()
    assert cfg.risk_reward_ratio >= 1.0


def test_default_max_drawdown():
    """Default max_drawdown_pct should be <= 20%."""
    cfg = BotConfig()
    assert cfg.max_drawdown_pct <= 20.0


def test_get_mode_risk_limits():
    """get_mode_risk_limits returns expected keys."""
    cfg = BotConfig()
    limits = cfg.get_mode_risk_limits()
    assert "max_risk_per_trade_pct" in limits
    assert "max_daily_loss_pct" in limits
    assert "max_positions" in limits


def test_default_symbol_is_xauusd():
    """Default symbol should be XAUUSD."""
    cfg = BotConfig()
    assert cfg.symbol == "XAUUSD"


def test_default_timeframes_not_empty():
    """Default timeframes list should not be empty."""
    cfg = BotConfig()
    assert len(cfg.timeframes) > 0
    assert "M15" in cfg.timeframes
