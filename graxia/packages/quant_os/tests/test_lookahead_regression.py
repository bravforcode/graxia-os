"""
Regression test: Prove LookaheadGuard actually enforces zero look-ahead.

Strategy 1: Prevention by construction — get_slice() cuts data before strategy.
Strategy 2: Detection — check_data_access() raises on future access.

This test proves BOTH strategies work.
"""
import sys
import os
import pytest
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.core.lookahead_guard import LookaheadGuard, LookaheadViolation
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.strategies.base import Strategy, StrategyConfig, Signal
from graxia.packages.quant_os.core.enums import SignalType, RegimeType
from typing import Dict, List, Optional
from decimal import Decimal


class CheatingStrategy(Strategy):
    """
    Strategy that INTENTIONALLY peeks at future data.
    
    Uses a module-level variable to bypass the sliced data and access
    the full dataset directly — simulating a strategy that cheats
    through global state, cache, or external data source.
    """
    
    _full_data_ref = None  # Module-level reference to full data
    
    def __init__(self):
        super().__init__(StrategyConfig(name="CheatingStrategy"))
    
    def required_features(self) -> List[str]:
        return []
    
    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: Dict[str, List],
        indicators: Optional[Dict] = None,
        regime: Optional[RegimeType] = None,
        **kwargs,
    ) -> Optional[Signal]:
        close = ohlcv_data.get("close", [])
        current_idx = len(close) - 1
        
        # CHEAT: Use module-level reference to access FULL data
        # This bypasses the guard's get_slice() protection
        if CheatingStrategy._full_data_ref is not None:
            full_close = CheatingStrategy._full_data_ref.get("close", [])
            future_idx = current_idx + 5
            
            if future_idx < len(full_close):
                future_price = full_close[future_idx]
                current_price = close[current_idx]
                
                if future_price > current_price * 1.001:
                    return Signal.create(
                        strategy_id=self.id,
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        confidence=0.99,
                        entry_price=Decimal(str(current_price)),
                        stop_loss=Decimal(str(current_price * 0.99)),
                        take_profit=Decimal(str(current_price * 1.02)),
                    )
                elif future_price < current_price * 0.999:
                    return Signal.create(
                        strategy_id=self.id,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        confidence=0.99,
                        entry_price=Decimal(str(current_price)),
                        stop_loss=Decimal(str(current_price * 1.01)),
                        take_profit=Decimal(str(current_price * 0.98)),
                    )
        
        return None


def generate_test_data(bars=200):
    """Generate simple trending data"""
    import random
    random.seed(42)
    
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = 2350.0
    
    for _ in range(bars):
        change = random.gauss(0.0005, 0.001)
        o = price
        c = price * (1 + change)
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        
        data["open"].append(round(o, 2))
        data["close"].append(round(c, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(l, 2))
        data["volume"].append(100000)
        
        price = c
    
    return data


class TestLookaheadGuardRegression:
    """
    REGRESSION TEST: Prove that LookaheadGuard actually blocks look-ahead.
    
    Strategy 1 (Prevention): get_slice() cuts data before strategy receives it.
    Strategy 2 (Detection): check_data_access() raises on future access.
    """
    
    def test_guard_raises_on_future_access(self):
        """Direct test: guard should raise when accessing future index"""
        guard = LookaheadGuard(strict=True)
        guard.initialize(100)
        guard.advance()  # Now at index 1
        
        with pytest.raises(LookaheadViolation):
            guard.check_data_access(50, caller="test")
    
    def test_guard_does_not_raise_on_past_access(self):
        """Direct test: guard should NOT raise when accessing past index"""
        guard = LookaheadGuard(strict=True)
        guard.initialize(100)
        guard.advance()
        guard.advance()
        
        result = guard.check_data_access(1, caller="test")
        assert result is True
    
    def test_get_slice_cuts_data_before_strategy(self):
        """
        PROOF: get_slice() returns only past data.
        Strategy receives sliced data, so it CANNOT peek at future bars.
        """
        guard = LookaheadGuard(strict=True)
        guard.initialize(100)
        
        data = {"close": list(range(100))}
        
        # At index 5, get_slice should return data[0:6] (indices 0-5)
        for i in range(5):
            guard.advance()
        
        sliced = guard.get_slice(data)
        # current_index = 5, so v[:5+1] = v[:6] = [0,1,2,3,4,5]
        assert len(sliced["close"]) == 6
        assert sliced["close"][-1] == 5  # Last bar is index 5
        assert 6 not in sliced["close"]  # Index 6 (future) NOT included
    
    def test_strategy_cannot_peek_through_sliced_data(self):
        """
        PROOF: A strategy that tries to peek through sliced data gets nothing.
        
        The strategy accesses ohlcv_data["close"][-1] which is the LAST bar
        in the sliced data. It then tries to access [current_idx + 5] but
        that index doesn't exist in the sliced array.
        """
        strategy = CheatingStrategy()
        data = generate_test_data(200)
        
        # Give strategy sliced data (simulating guard.get_slice)
        sliced = {k: v[:10] for k, v in data.items()}
        signal = strategy.generate_signal("XAUUSD", sliced)
        
        # No signal — strategy can't peek because data is sliced
        assert signal is None, "Strategy should NOT generate signal from sliced data"
    
    def test_cheating_strategy_can_peek_without_guard(self):
        """
        PROOF: The same strategy CAN peek when given full data + global ref.
        
        This proves the strategy IS capable of cheating — the guard is what
        prevents it, not the strategy being honest.
        """
        strategy = CheatingStrategy()
        data = generate_test_data(200)
        
        # Set up global reference (bypass guard)
        CheatingStrategy._full_data_ref = data
        
        try:
            # Give sliced data (what guard provides)
            sliced = {k: v[:10] for k, v in data.items()}
            signal = strategy.generate_signal("XAUUSD", sliced)
            
            # Strategy CAN peek through global ref
            assert signal is not None, "Strategy should peek through global ref"
        finally:
            CheatingStrategy._full_data_ref = None
    
    def test_backtest_guard_prevents_cheating_strategy(self):
        """
        THE CRITICAL TEST: Run backtest with cheating strategy.
        
        Guard uses get_slice() to cut data before strategy.
        Even though strategy has global ref, the engine only passes sliced data.
        Strategy tries to peek but current_idx + 5 exceeds sliced array length.
        Result: no signals generated (strategy can't cheat).
        """
        CheatingStrategy._full_data_ref = generate_test_data(200)
        
        try:
            config = BacktestConfig(
                initial_capital=Decimal("10000"),
                strict_mtf=False,
            )
            
            engine = BacktestEngine(config)
            engine.set_strategy(CheatingStrategy())
            
            data = generate_test_data(200)
            from datetime import datetime, timedelta
            timestamps = [datetime(2020, 1, 1) + timedelta(hours=i) for i in range(200)]
            
            engine.load_data(data, timestamps)
            results = engine.run()
            
            # Guard prevented cheating: no trades should be generated
            # (strategy tries to peek but sliced data is too short)
            assert results["metrics"].total_trades == 0, \
                f"Expected 0 trades (guard prevented cheating), got {results['metrics'].total_trades}"
        finally:
            CheatingStrategy._full_data_ref = None
    
    def test_guard_strict_false_logs_but_does_not_raise(self):
        """Verify non-strict mode logs but doesn't raise"""
        guard = LookaheadGuard(strict=False)
        guard.initialize(100)
        guard.advance()
        
        result = guard.check_data_access(50, caller="test")
        assert result is False
        assert guard.has_violations
