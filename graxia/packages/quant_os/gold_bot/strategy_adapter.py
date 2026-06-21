from decimal import Decimal


class GoldStrategyAdapter:
    """
    Adapts gold_bot strategies (which expect multi-timeframe nested dict)
    to work with backtest engine (which passes flat ohlcv_data per bar).
    
    Gold strategies expect: data["M15"]["close"] = [...]
    Backtest engine provides: ohlcv_data["close"] = [...] (current TF only)
    
    If multi_tf_data is provided (dict mapping TF strings to ohlcv dicts),
    uses real data for each timeframe. Otherwise maps all TFs to same data.
    """
    
    def __init__(self, gold_strategy, multi_tf_data=None):
        self.gold_strategy = gold_strategy
        self.id = gold_strategy.__class__.__name__
        self.target_tf = getattr(gold_strategy, 'min_timeframe', 'M15')
        # Store real multi-TF data if provided
        self.multi_tf_data = multi_tf_data or {}
    
    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None):
        # Build nested data: use real multi-TF data where available,
        # fall back to current bar data for missing TFs
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
