"""
Volume Breakout — Price breakout confirmed by volume spike.

Expected improvement: +10-15% through better entries.

ponytail: Simple breakout + volume filter. Upgrade path: volatility-adjusted thresholds.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from ..core.enums import SignalType, RegimeType
from .base import Signal, Strategy, StrategyConfig


class VolumeBreakout(Strategy):
    """Strategy based on price breakout with volume confirmation.

    Signals:
    - BUY: Price breaks above N-period high with volume > 2x average
    - SELL: Price breaks below N-period low with volume > 2x average

    Example:
        strategy = VolumeBreakout(lookback=20, volume_threshold=2.0)
        signal = strategy.generate_signal('XAUUSD', ohlcv_data)
    """

    def __init__(
        self,
        lookback: int = 20,
        volume_threshold: float = 2.0,
        config: StrategyConfig | None = None,
    ):
        super().__init__(
            config
            or StrategyConfig(
                name="VolumeBreakout",
                version="1.0.0",
                symbols=["XAUUSD", "BTCUSD", "EURUSD"],
                min_confidence=0.65,
            )
        )
        self.lookback = lookback
        self.volume_threshold = volume_threshold

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """Generate signal on volume-confirmed breakout.

        Args:
            symbol: Trading symbol
            ohlcv_data: Dict with 'open', 'high', 'low', 'close', 'volume'
            indicators: Pre-computed indicators
            regime: Current market regime
            **kwargs: Additional parameters

        Returns:
            Signal if breakout confirmed, None otherwise
        """
        close = np.array(ohlcv_data.get("close", []))
        high = np.array(ohlcv_data.get("high", []))
        low = np.array(ohlcv_data.get("low", []))
        volume = np.array(ohlcv_data.get("volume", []))

        if len(close) < self.lookback + 1:
            return None

        # Calculate levels
        recent_high = np.max(high[-self.lookback - 1 : -1])
        recent_low = np.min(low[-self.lookback - 1 : -1])
        vol_window = max(self.lookback, 20)  # Use lookback or minimum 20 for volume SMA
        volume_sma = np.mean(volume[-vol_window:])
        current_volume = volume[-1]

        # Breakout detection
        breakout_up = close[-1] > recent_high
        breakout_down = close[-1] < recent_low
        high_volume = current_volume > volume_sma * self.volume_threshold

        if not high_volume:
            return None  # No volume confirmation

        current_price = Decimal(str(close[-1]))

        if breakout_up:
            # Bullish breakout — SL below breakout level, TP = 2x range
            stop_loss = Decimal(str(recent_low))
            range_size = close[-1] - recent_low
            take_profit = Decimal(str(close[-1] + 2 * range_size))

            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.75,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                notes=f"Bullish breakout above {recent_high:.5f} with volume {current_volume / volume_sma:.1f}x",
                indicator_values={
                    "breakout_level": recent_high,
                    "volume_ratio": current_volume / volume_sma,
                    "direction": "up",
                },
            )

        elif breakout_down:
            # Bearish breakout — SL above breakout level, TP = 2x range
            stop_loss = Decimal(str(recent_high))
            range_size = recent_high - close[-1]
            take_profit = Decimal(str(close[-1] - 2 * range_size))

            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.75,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                notes=f"Bearish breakout below {recent_low:.5f} with volume {current_volume / volume_sma:.1f}x",
                indicator_values={
                    "breakout_level": recent_low,
                    "volume_ratio": current_volume / volume_sma,
                    "direction": "down",
                },
            )

        return None

    def required_features(self) -> list[str]:
        return ["high", "low", "close", "volume"]
