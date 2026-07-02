"""Candle pipelines from Jesse pattern for Monte Carlo simulation"""
from abc import ABC, abstractmethod
from typing import List, Dict
import random

class BaseCandlesPipeline(ABC):
    """Base class for candle regeneration pipelines"""

    def __init__(self, batch_size: int = 1000):
        self._batch_size = batch_size

    @abstractmethod
    def process(self, original_candles: Dict[str, List[float]],
                output: Dict[str, List[float]]) -> bool:
        """Regenerate candles. Return True if output was modified."""
        pass

    def get_candles(self, candles: Dict[str, List[float]],
                    index: int) -> Dict[str, List[float]]:
        """Get candle at index, regenerating batch if needed"""
        result = {}
        for key in candles:
            if index < len(candles[key]):
                result[key] = candles[key][index]
        return result

class MovingBlockBootstrapPipeline(BaseCandlesPipeline):
    """Bootstrap blocks of price changes to generate synthetic candles"""

    def __init__(self, block_size: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.block_size = block_size

    def process(self, original_candles: Dict[str, List[float]],
                output: Dict[str, List[float]]) -> bool:
        close = original_candles.get("close", [])
        high = original_candles.get("high", [])
        low = original_candles.get("low", [])

        if len(close) < self.block_size + 1:
            return False

        # Calculate deltas
        delta_close = [close[i] - close[i-1] for i in range(1, len(close))]
        delta_high = [high[i] - close[i-1] for i in range(1, len(close))]
        delta_low = [close[i-1] - low[i] for i in range(1, len(close))]

        # Bootstrap blocks
        n = len(delta_close)
        boot_close = [close[0]]
        for i in range(n):
            block_start = random.randint(0, n - self.block_size)
            for j in range(self.block_size):
                idx = (block_start + j) % n
                boot_close.append(boot_close[-1] + delta_close[idx])

        # Generate output
        output["close"] = boot_close[:len(close)]
        output["open"] = [boot_close[0]] + boot_close[:-1]
        output["high"] = [max(o, c) + abs(random.gauss(0, 0.001))
                         for o, c in zip(output["open"], output["close"])]
        output["low"] = [min(o, c) - abs(random.gauss(0, 0.001))
                        for o, c in zip(output["open"], output["close"])]
        output["volume"] = original_candles.get("volume", [0] * len(close))

        return True

class GaussianNoisePipeline(BaseCandlesPipeline):
    """Add Gaussian noise to candles"""

    def __init__(self, noise_pct: float = 0.001, **kwargs):
        super().__init__(**kwargs)
        self.noise_pct = noise_pct

    def process(self, original_candles: Dict[str, List[float]],
                output: Dict[str, List[float]]) -> bool:
        for key in original_candles:
            output[key] = [
                v * (1 + random.gauss(0, self.noise_pct))
                for v in original_candles[key]
            ]
        return True
