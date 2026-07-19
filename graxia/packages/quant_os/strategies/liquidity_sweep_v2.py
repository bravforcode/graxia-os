"""Liquidity Sweep V2 — Enhanced with trailing stops, RSI/volume filters, regime-aware sizing.

Key improvements over V1:
1. RSI confirmation filter: only trade sweeps confirmed by RSI extreme
2. Volume confirmation: require volume spike on sweep bar
3. Trailing stop: ATR-based trailing stop that ratchets as price moves favorably
4. Regime-aware TP: wider targets in trends, tighter in ranges
5. Multi-timeframe ATR: longer lookback for more stable volatility measurement
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..core.enums import RegimeType, SignalType
from ..regime import RegimeDetector
from .base import Signal, Strategy, StrategyConfig


class LiquiditySweepV2(Strategy):
    """Enhanced liquidity sweep with trailing stops, RSI/volume filters, regime-aware sizing.

    Parameters:
        sweep_lookback: bars for swing high/low detection
        rsi_period: RSI calculation period
        rsi_oversold: RSI threshold for BUY confirmation (RSI < oversold after sweep low)
        rsi_overbought: RSI threshold for SELL confirmation (RSI > overbought after sweep high)
        volume_sma_period: period for volume moving average
        volume_spike_mult: volume must be > SMA * mult to confirm
        atr_period: ATR period for SL/TP and trailing stop
        atr_sl_mult: ATR multiplier for initial stop loss
        atr_tp_mult: ATR multiplier for take profit
        atr_trail_mult: ATR multiplier for trailing stop distance
        regime_filter: if True, skip signals in UNCLEAR regime
    """

    def __init__(
        self,
        sweep_lookback: int = 20,
        rsi_period: int = 14,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        volume_sma_period: int = 20,
        volume_spike_mult: float = 1.2,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        atr_trail_mult: float = 2.0,
        regime_filter: bool = False,
    ):
        config = StrategyConfig(
            name="LiquiditySweepV2",
            version="2.0.0",
            symbols=["XAUUSD", "EURUSD", "GBPUSD"],
            timeframes=["D1", "H1", "M15"],
            min_confidence=0.0,
            min_risk_reward=0.0,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self._sweep_lookback = sweep_lookback
        self._rsi_period = rsi_period
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._volume_sma_period = volume_sma_period
        self._volume_spike_mult = volume_spike_mult
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_mult
        self._atr_tp_mult = atr_tp_mult
        self._atr_trail_mult = atr_trail_mult
        self._regime_filter = regime_filter
        self._regime_detector = RegimeDetector()

    def required_features(self) -> list[str]:
        return []

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        if len(close) < max(self._sweep_lookback, self._rsi_period, self._atr_period, self._volume_sma_period) + 10:
            return None

        closes = [float(c) for c in close]
        highs = [float(h) for h in ohlcv_data.get("high", close)]
        lows = [float(l) for l in ohlcv_data.get("low", close)]
        volumes = [float(v) for v in ohlcv_data.get("volume", [0] * len(close))]

        current_price = closes[-1]
        if current_price <= 0:
            return None

        # Phase 1: Regime detection
        if regime is not None:
            regime_str = regime.name if hasattr(regime, "name") else str(regime)
        else:
            regime_result = self._regime_detector.detect(closes, highs, lows)
            regime_str = regime_result.regime

        if self._regime_filter and regime_str == "UNCLEAR":
            return None

        # Phase 2: ATR calculation
        atr = self._compute_atr(highs, lows, closes, self._atr_period)
        if atr <= 0:
            return None

        # Phase 3: Sweep detection (exclude current bar from lookback)
        lookback = self._sweep_lookback
        recent_low = min(lows[-(lookback + 1):-1])
        recent_high = max(highs[-(lookback + 1):-1])

        sweep_low = lows[-1] < recent_low
        sweep_high = highs[-1] > recent_high

        if not sweep_low and not sweep_high:
            return None

        # Phase 4: RSI confirmation
        rsi = self._compute_rsi(closes, self._rsi_period)
        if rsi is None:
            return None

        # Phase 5: Volume confirmation
        vol_sma = sum(volumes[-self._volume_sma_period:]) / self._volume_sma_period if len(volumes) >= self._volume_sma_period else 0
        current_volume = volumes[-1]
        vol_confirmed = current_volume > vol_sma * self._volume_spike_mult if vol_sma > 0 else True

        # Phase 6: Regime-aware TP sizing
        if regime_str in ("TREND_UP", "TREND_DOWN"):
            regime_tp_mult = self._atr_tp_mult * 1.3  # Wider TP in trends
            regime_sl_mult = self._atr_sl_mult * 0.9  # Tighter SL in trends (quick exit if wrong)
        elif regime_str == "RANGE":
            regime_tp_mult = self._atr_tp_mult * 0.8  # Tighter TP in ranges
            regime_sl_mult = self._atr_sl_mult * 1.1  # Wider SL in ranges (more room)
        else:
            regime_tp_mult = self._atr_tp_mult
            regime_sl_mult = self._atr_sl_mult

        # BUY: sweep below recent low + close above + RSI oversold + volume spike
        if sweep_low and closes[-1] > recent_low:
            # RSI must show oversold condition (price swept low, RSI confirms exhaustion)
            if rsi > self._rsi_oversold:
                return None
            if not vol_confirmed:
                return None

            sl = Decimal(str(current_price - atr * regime_sl_mult))
            tp = Decimal(str(current_price + atr * regime_tp_mult))
            trail_dist = Decimal(str(atr * self._atr_trail_mult))

            # Confidence: composite of RSI extremity + volume ratio + regime match
            rsi_score = min((self._rsi_oversold - rsi) / self._rsi_oversold, 1.0) if self._rsi_oversold > 0 else 0
            vol_ratio = current_volume / vol_sma if vol_sma > 0 else 1.0
            vol_score = min((vol_ratio - 1.0) / 1.0, 1.0)  # 0 at 1x, 1 at 2x+
            regime_bonus = 0.15 if regime_str in ("TREND_UP", "RANGE") else 0
            confidence = min(0.5 + 0.2 * rsi_score + 0.15 * vol_score + regime_bonus, 0.95)

            regime_type = RegimeType.TREND_STRONG_UP if regime_str == "TREND_UP" else RegimeType.RANGE_BOUND

            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
                trailing_stop_distance=trail_dist,
                regime=regime_type,
                indicator_values={"rsi": rsi, "atr": atr, "volume_ratio": current_volume / vol_sma if vol_sma > 0 else 0},
            )

        # SELL: sweep above recent high + close below + RSI overbought + volume spike
        if sweep_high and closes[-1] < recent_high:
            if rsi < self._rsi_overbought:
                return None
            if not vol_confirmed:
                return None

            sl = Decimal(str(current_price + atr * regime_sl_mult))
            tp = Decimal(str(current_price - atr * regime_tp_mult))
            trail_dist = Decimal(str(atr * self._atr_trail_mult))

            rsi_score = min((rsi - self._rsi_overbought) / (100.0 - self._rsi_overbought), 1.0)
            vol_ratio = current_volume / vol_sma if vol_sma > 0 else 1.0
            vol_score = min((vol_ratio - 1.0) / 1.0, 1.0)
            regime_bonus = 0.15 if regime_str in ("TREND_DOWN", "RANGE") else 0
            confidence = min(0.5 + 0.2 * rsi_score + 0.15 * vol_score + regime_bonus, 0.95)

            regime_type = RegimeType.TREND_STRONG_DOWN if regime_str == "TREND_DOWN" else RegimeType.RANGE_BOUND

            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=confidence,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
                trailing_stop_distance=trail_dist,
                regime=regime_type,
                indicator_values={"rsi": rsi, "atr": atr, "volume_ratio": current_volume / vol_sma if vol_sma > 0 else 0},
            )

        return None

    @staticmethod
    def _compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Compute ATR using Wilder's smoothing."""
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        # Wilder smoothing
        atr = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
        return atr

    @staticmethod
    def _compute_rsi(closes: list, period: int = 14) -> float | None:
        """Compute RSI using Wilder's smoothing."""
        if len(closes) < period + 2:
            return None
        gains = []
        losses = []
        for i in range(1, period + 1):
            change = closes[i] - closes[i - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        for i in range(period + 1, len(closes)):
            change = closes[i] - closes[i - 1]
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
