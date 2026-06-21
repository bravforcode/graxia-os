"""Pipeline pair filters from Freqtrade pattern"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class BacktestSupport(Enum):
    SAFE = "safe"
    BIASED = "biased"
    UNSUPPORTED = "unsupported"

class PairFilter(ABC):
    backtest_support: BacktestSupport = BacktestSupport.UNSUPPORTED
    
    @abstractmethod
    def filter(self, pairs: List[str], context: Dict) -> List[str]:
        """Filter and return allowed pairs"""
        pass

class MinVolumeFilter(PairFilter):
    backtest_support = BacktestSupport.SAFE
    
    def __init__(self, min_volume: float = 1_000_000):
        self.min_volume = min_volume
    
    def filter(self, pairs, context):
        tickers = context.get("tickers", {})
        return [p for p in pairs if tickers.get(p, {}).get("volume", 0) >= self.min_volume]

class SpreadFilter(PairFilter):
    backtest_support = BacktestSupport.SAFE
    
    def __init__(self, max_spread_pct: float = 0.5):
        self.max_spread_pct = max_spread_pct
    
    def filter(self, pairs, context):
        tickers = context.get("tickers", {})
        return [p for p in pairs 
                if tickers.get(p, {}).get("spread_pct", 100) <= self.max_spread_pct]

class PairFilterPipeline:
    def __init__(self, filters: List[PairFilter] = None):
        self.filters = filters or []
    
    def add_filter(self, f: PairFilter):
        self.filters.append(f)
        return self
    
    def apply(self, pairs: List[str], context: Dict) -> List[str]:
        for f in self.filters:
            pairs = f.filter(pairs, context)
        return pairs
    
    def validate_for_backtest(self) -> List[str]:
        """Warn about biased or unsupported filters"""
        warnings = []
        for f in self.filters:
            if f.backtest_support == BacktestSupport.UNSUPPORTED:
                warnings.append(f"{f.__class__.__name__} is not supported in backtesting")
            elif f.backtest_support == BacktestSupport.BIASED:
                warnings.append(f"{f.__class__.__name__} introduces lookahead bias")
        return warnings
