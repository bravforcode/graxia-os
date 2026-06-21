"""
Tests for Gold Bot engine, league system, and risk manager
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pytest
from graxia.packages.quant_os.gold_bot.core.engine import (
    GoldBotEngine, LeagueSystem, RiskManager,
    SignalDirection, StrategySignal, AggregatedSignal, TradeRecord
)
from graxia.packages.quant_os.gold_bot.core.config import BotConfig


class TestLeagueSystem:
    def test_init(self):
        league = LeagueSystem()
        assert league.BENCH_CONSECUTIVELOSSES == 3
    
    def test_new_strategy_starts_a(self):
        league = LeagueSystem()
        stats = {"test": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "active": True, "league_tier": "A"}}
        league.update(stats)
        assert stats["test"]["league_tier"] == "A"
    
    def test_win_rate_s_tier(self):
        league = LeagueSystem()
        stats = {"test": {"trades": 15, "wins": 10, "losses": 5, "pnl": 500.0, "active": True, "league_tier": "A"}}
        league.update(stats)
        assert stats["test"]["league_tier"] == "S"
    
    def test_consecutive_losses_bench(self):
        league = LeagueSystem()
        stats = {"test": {"trades": 5, "wins": 2, "losses": 3, "pnl": -100.0, "active": True, "league_tier": "B"}}
        
        # Simulate 3 consecutive losses
        for _ in range(3):
            stats["test"]["losses"] += 1
            league.update(stats)
        
        assert stats["test"]["league_tier"] == "BENCH"
        assert stats["test"]["active"] == False


class TestRiskManager:
    def test_init(self):
        config = BotConfig()
        rm = RiskManager(config)
        assert rm.daily_loss == 0.0
    
    def test_position_sizing(self):
        config = BotConfig(max_risk_per_trade_pct=1.0)
        rm = RiskManager(config)
        
        qty = rm.calculate_position_size(
            balance=10000,
            entry_price=2350.0,
            stop_loss=2340.0,
        )
        
        assert qty > 0
        assert qty <= config.max_position_size_lots
    
    def test_risk_check_max_positions(self):
        config = BotConfig(max_positions=2)
        rm = RiskManager(config)
        
        signal = AggregatedSignal(
            direction=SignalDirection.BUY,
            total_score=500,
            active_strategies=5,
            buy_score=500,
            sell_score=0,
            signals=[],
        )
        
        open_trades = [1, 2]  # Already at max
        assert rm.check(signal, open_trades, 0.0) == False
    
    def test_risk_check_daily_loss(self):
        config = BotConfig(initial_capital=10000, max_daily_loss_pct=3.0)
        rm = RiskManager(config)
        
        signal = AggregatedSignal(
            direction=SignalDirection.BUY,
            total_score=500,
            active_strategies=5,
            buy_score=500,
            sell_score=0,
            signals=[],
        )
        
        # Daily loss exceeded
        assert rm.check(signal, [], -350.0) == False
    
    def test_risk_check_pass(self):
        config = BotConfig(min_score_to_trade=300, min_active_strategies=3)
        rm = RiskManager(config)
        
        signal = AggregatedSignal(
            direction=SignalDirection.BUY,
            total_score=500,
            active_strategies=5,
            buy_score=500,
            sell_score=0,
            signals=[],
        )
        
        assert rm.check(signal, [], 0.0) == True


class TestAggregatedSignal:
    def test_creation(self):
        signal = AggregatedSignal(
            direction=SignalDirection.BUY,
            total_score=500,
            active_strategies=5,
            buy_score=500,
            sell_score=0,
            signals=[],
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.total_score == 500


class TestStrategySignal:
    def test_creation(self):
        signal = StrategySignal(
            strategy_name="test",
            direction=SignalDirection.BUY,
            confidence=0.75,
            score=75,
            entry_price=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            reasoning="Test signal",
        )
        assert signal.strategy_name == "test"
        assert signal.score == 75


class TestTradeRecord:
    def test_creation(self):
        from datetime import datetime
        trade = TradeRecord(
            id="test_001",
            symbol="XAUUSD",
            direction=SignalDirection.BUY,
            entry_price=2350.0,
            quantity=0.1,
            stop_loss=2340.0,
            take_profit=2370.0,
            entry_time=datetime.utcnow(),
        )
        assert trade.symbol == "XAUUSD"
        assert trade.status == "OPEN"


class TestGoldBotEngine:
    def test_init(self):
        config = BotConfig()
        engine = GoldBotEngine(config)
        assert engine.is_running == False
        assert engine.cycle_count == 0
    
    def test_register_strategy(self):
        config = BotConfig()
        engine = GoldBotEngine(config)
        
        class MockStrategy:
            def analyze(self, **kwargs):
                return None
        
        engine.register_strategy("test", MockStrategy(), 1.0)
        assert "test" in engine.strategies
        assert engine.strategy_weights["test"] == 1.0
    
    def test_generate_mock_data(self):
        config = BotConfig()
        engine = GoldBotEngine(config)
        data = engine._generate_mock_data()
        
        assert "M15" in data
        assert "close" in data["M15"]
        assert len(data["M15"]["close"]) == 200
        assert engine.price_cache["mid"] > 0
