from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, List


class GoldStrategyAdapter:
    """
    Adapts gold_bot strategies to the backtest engine with point-in-time MTF data.
    
    When a MultiTimeframeCursor is set (via engine.set_multi_timeframe),
    lower TF data is sliced to timestamp <= current_time before passing
    to the strategy. This prevents look-ahead leakage.
    
    Without cursor, falls back to static multi_tf_data (legacy, leaky).
    """
    
    def __init__(self, gold_strategy, multi_tf_data=None):
        self.gold_strategy = gold_strategy
        self.id = gold_strategy.__class__.__name__
        self.target_tf = getattr(gold_strategy, 'min_timeframe', 'M15')
        # Legacy static data (leaky — use cursor instead)
        self.multi_tf_data = multi_tf_data or {}
        # Cursor for point-in-time slicing (set by engine each bar)
        self._sliced_data = None
    
    def _set_mtf_cursor(self, sliced_data: Dict[str, Dict[str, List]]):
        """Called by engine each bar with point-in-time sliced data."""
        self._sliced_data = sliced_data
    
    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        current_time = kwargs.get("current_time")
        
        # Prefer point-in-time sliced data from cursor
        if self._sliced_data is not None:
            nested_data = self._sliced_data
        else:
            # Fallback: static data (LEAKY — only for backward compat)
            nested_data = {}
            for tf in ["M1", "M5", "M15", "H1", "H4", "D1"]:
                nested_data[tf] = self.multi_tf_data.get(tf, ohlcv_data)
        
        current_price = ohlcv_data["close"][-1] if ohlcv_data.get("close") else 0
        
        gold_signal = self.gold_strategy.analyze(nested_data, current_price, symbol)

        if gold_signal is None:
            return None

        from graxia.packages.quant_os.strategies.base import Signal
        from graxia.packages.quant_os.core.enums import SignalType

        signal_type = SignalType.BUY if gold_signal.direction.value == "BUY" else SignalType.SELL

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=gold_signal.confidence,
            entry_price=Decimal(str(gold_signal.entry_price)) if gold_signal.entry_price else None,
            stop_loss=Decimal(str(gold_signal.stop_loss)) if gold_signal.stop_loss else None,
            take_profit=Decimal(str(gold_signal.take_profit)) if gold_signal.take_profit else None,
        )

    def required_features(self):
        return []
