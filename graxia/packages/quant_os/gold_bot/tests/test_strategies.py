"""
Tests for Gold Bot strategies
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pytest
from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
from graxia.packages.quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
from graxia.packages.quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from graxia.packages.quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
from graxia.packages.quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
from graxia.packages.quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
from graxia.packages.quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
from graxia.packages.quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
from graxia.packages.quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
from graxia.packages.quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
from graxia.packages.quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
from graxia.packages.quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
from graxia.packages.quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy
from graxia.packages.quant_os.gold_bot.core.engine import SignalDirection

import random
random.seed(42)


def generate_mock_data(bars=200, base_price=2350.0):
    """Generate mock OHLCV data for testing"""
    data = {}
    for tf in ["M1", "M5", "M15", "H1", "H4"]:
        closes = []
        highs = []
        lows = []
        opens = []
        volumes = []
        
        price = base_price
        for _ in range(bars):
            change = random.gauss(0, 0.001)
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.0005)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.0005)))
            v = 100000 * (1 + random.gauss(0, 0.3))
            
            opens.append(round(o, 2))
            closes.append(round(c, 2))
            highs.append(round(h, 2))
            lows.append(round(l, 2))
            volumes.append(max(0, v))
            
            price = c
        
        data[tf] = {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    
    return data


class TestBaseStrategy:
    """Test base strategy utilities"""
    
    def test_calc_ema(self):
        from graxia.packages.quant_os.gold_bot.strategies.base import GoldStrategy
        
        class TestStrategy(GoldStrategy):
            name = "test"
        
        s = TestStrategy()
        prices = [100 + i * 0.1 for i in range(50)]
        ema = s._calc_ema(prices, 20)
        assert len(ema) > 0
        assert ema[-1] > prices[0]
    
    def test_calc_rsi(self):
        from graxia.packages.quant_os.gold_bot.strategies.base import GoldStrategy
        
        class TestStrategy(GoldStrategy):
            name = "test"
        
        s = TestStrategy()
        prices = [100 + i * 0.1 for i in range(30)]
        rsi = s._calc_rsi(prices, 14)
        assert rsi is not None
        assert 0 <= rsi <= 100
    
    def test_calc_atr(self):
        from graxia.packages.quant_os.gold_bot.strategies.base import GoldStrategy
        
        class TestStrategy(GoldStrategy):
            name = "test"
        
        s = TestStrategy()
        high = [105 + i for i in range(30)]
        low = [95 + i for i in range(30)]
        close = [100 + i for i in range(30)]
        atr = s._calc_atr(high, low, close, 14)
        assert atr is not None
        assert atr > 0


class TestOrderBlock:
    def test_strategy_init(self):
        s = OrderBlockStrategy()
        assert s.name == "order_block"
        assert s.min_timeframe == "H1"
    
    def test_analyze_returns_signal_or_none(self):
        s = OrderBlockStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        # May return None if no signal, that's ok
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
            assert 0 <= result.score <= 100


class TestSupplyDemand:
    def test_strategy_init(self):
        s = SupplyDemandStrategy()
        assert s.name == "supply_demand"
    
    def test_analyze(self):
        s = SupplyDemandStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestEMACross:
    def test_strategy_init(self):
        s = EMACrossStrategy()
        assert s.name == "ema_cross"
    
    def test_analyze(self):
        s = EMACrossStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
            assert result.score >= 50


class TestRSIDivergence:
    def test_strategy_init(self):
        s = RSIDivergenceStrategy()
        assert s.name == "rsi_divergence"
    
    def test_analyze(self):
        s = RSIDivergenceStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestLondonBreakout:
    def test_strategy_init(self):
        s = LondonBreakoutStrategy()
        assert s.name == "london_breakout"
    
    def test_analyze(self):
        s = LondonBreakoutStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestFibonacci:
    def test_strategy_init(self):
        s = FibonacciStrategy()
        assert s.name == "fibonacci"
    
    def test_analyze(self):
        s = FibonacciStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestVWAPRejection:
    def test_strategy_init(self):
        s = VWAPRejectionStrategy()
        assert s.name == "vwap_rejection"
    
    def test_analyze(self):
        s = VWAPRejectionStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestNewsFade:
    def test_strategy_init(self):
        s = NewsFadeStrategy()
        assert s.name == "news_fade"
    
    def test_analyze(self):
        s = NewsFadeStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestMultiTFAlign:
    def test_strategy_init(self):
        s = MultiTFAlignStrategy()
        assert s.name == "multi_tf_align"
    
    def test_analyze(self):
        s = MultiTFAlignStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestBOSCHoCH:
    def test_strategy_init(self):
        s = BOSCHoCHStrategy()
        assert s.name == "bos_choch"
    
    def test_analyze(self):
        s = BOSCHoCHStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestLiquiditySweep:
    def test_strategy_init(self):
        s = LiquiditySweepStrategy()
        assert s.name == "liquidity_sweep"
    
    def test_analyze(self):
        s = LiquiditySweepStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestFairValueGap:
    def test_strategy_init(self):
        s = FairValueGapStrategy()
        assert s.name == "fair_value_gap"
    
    def test_analyze(self):
        s = FairValueGapStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


class TestOpeningRange:
    def test_strategy_init(self):
        s = OpeningRangeStrategy()
        assert s.name == "opening_range"
    
    def test_analyze(self):
        s = OpeningRangeStrategy()
        data = generate_mock_data()
        result = s.analyze(data, 2350.0, "XAUUSD")
        if result is not None:
            assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
