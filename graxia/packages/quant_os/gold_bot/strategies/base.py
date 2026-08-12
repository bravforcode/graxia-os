"""
Base Strategy for Gold Bot
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, List

import sys, os
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.gold_bot.core.engine import StrategySignal, SignalDirection


class GoldStrategy(ABC):
    """Base class for all gold trading strategies"""
    
    name: str = "base"
    description: str = ""
    min_timeframe: str = "M15"
    
    def analyze(
        self,
        data: Dict,
        current_price: float,
        symbol: str = "XAUUSD",
    ) -> Optional[StrategySignal]:
        """
        Analyze market data and generate a signal.
        
        Args:
            data: Dict of OHLCV data per timeframe
            current_price: Current mid price
            symbol: Trading symbol
        
        Returns:
            StrategySignal if signal found, None otherwise
        """
        pass
    
    def _get_close(self, data: Dict, tf: str = "M15") -> List[float]:
        """Get close prices for timeframe"""
        return data.get(tf, {}).get("close", [])
    
    def _get_high(self, data: Dict, tf: str = "M15") -> List[float]:
        return data.get(tf, {}).get("high", [])
    
    def _get_low(self, data: Dict, tf: str = "M15") -> List[float]:
        return data.get(tf, {}).get("low", [])
    
    def _get_volume(self, data: Dict, tf: str = "M15") -> List[float]:
        return data.get(tf, {}).get("volume", [])
    
    def _calc_ema(self, prices: List[float], period: int) -> List[float]:
        """Calculate EMA"""
        if len(prices) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema = [sum(prices[:period]) / period]
        
        for price in prices[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        
        return ema
    
    def _calc_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return None
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calc_atr(self, high: List[float], low: List[float], close: List[float], period: int = 14) -> Optional[float]:
        """Calculate ATR"""
        if len(close) < period + 1:
            return None
        
        trs = []
        for i in range(1, len(close)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            trs.append(tr)
        
        return sum(trs[-period:]) / period
