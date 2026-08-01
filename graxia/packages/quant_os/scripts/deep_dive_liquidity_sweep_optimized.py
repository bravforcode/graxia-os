"""
Deep Dive Validation: Optimized Liquidity Sweep Strategy
=========================================================
Runs comprehensive validation with parameterized SL/TP and lookback.

Strategy: LiquiditySweepOptimized (configurable parameters)
Symbol: XAUUSD D1

Current issues from previous validation:
- 648 trades but Sharpe=0.0000 (break-even)
- Walk-Forward: 1/5 positive
- Bootstrap CI includes zero

Optimization approach:
1. Test different SL/TP multipliers (1.0-3.0x ATR)
2. Test different lookback periods (10-30 bars)
3. Test regime filter options
"""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.core.enums import RegimeType, SignalType
from quant_os.strategies.base import Signal, Strategy, StrategyConfig
from quant_os.strategies.liquidity_sweep import LiquiditySweepStrategy
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)


# ── Optimized Wrapper Strategy Class ──────────────────────────────────────

class LiquiditySweepOptimized(Strategy):
    """Optimized Liquidity Sweep with configurable parameters."""

    def __init__(
        self,
        sweep_lookback: int = 20,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.0,
        regime_filter: bool = True,
        min_confidence: float = 0.5,
    ):
        config = StrategyConfig(
            name="LiquiditySweepOptimized",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
        )
        super().__init__(config)
        self.sweep_lookback = sweep_lookback
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.regime_filter = regime_filter
        self.min_confidence = min_confidence

        # Import regime detector
        from quant_os.regime import RegimeDetector
        self._regime_detector = RegimeDetector()

    def required_features(self) -> list[str]:
        return []

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        if len(close) < 60:
            return None

        closes = [float(c) for c in close]
        highs = [float(h) for h in ohlcv_data.get("high", close)]
        lows = [float(l) for l in ohlcv_data.get("low", close)]

        # Phase 1: Regime detection (optional)
        if self.regime_filter:
            if regime is not None:
                regime_str = regime.name if hasattr(regime, "name") else str(regime)
            else:
                regime_result = self._regime_detector.detect(closes, highs, lows)
                regime_str = regime_result.regime
            if regime_str == "UNCLEAR":
                return None

        # Phase 2: Sweep detection with configurable lookback
        lookback = self.sweep_lookback
        current_price = closes[-1]

        # Exclude current bar from lookback window
        recent_low = min(lows[-(lookback + 1):-1])
        recent_high = max(highs[-(lookback + 1):-1])

        # Calculate ATR
        atr = self._atr(closes[-20:], highs[-20:], lows[-20:])
        if atr <= 0:
            return None

        # Sweep below recent low + close above = BUY
        if lows[-1] < recent_low and closes[-1] > recent_low:
            sl = Decimal(str(current_price - atr * self.atr_sl_mult))
            tp = Decimal(str(current_price + atr * self.atr_tp_mult))
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=self.min_confidence,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
            )

        # Sweep above recent high + close below = SELL
        if highs[-1] > recent_high and closes[-1] < recent_high:
            sl = Decimal(str(current_price + atr * self.atr_sl_mult))
            tp = Decimal(str(current_price - atr * self.atr_tp_mult))
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=self.min_confidence,
                entry_price=Decimal(str(current_price)),
                stop_loss=sl,
                take_profit=tp,
            )

        return None

    @staticmethod
    def _atr(closes: list, highs: list, lows: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        return sum(trs[-period:]) / period


# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Liquidity Sweep Optimized XAUUSD D1"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    # Tight SL/TP (1.0/1.5) with different lookbacks
    {"sweep_lookback": 15, "atr_sl_mult": 1.0, "atr_tp_mult": 1.5, "regime_filter": False, "min_confidence": 0.4},
    {"sweep_lookback": 20, "atr_sl_mult": 1.0, "atr_tp_mult": 1.5, "regime_filter": False, "min_confidence": 0.4},
    {"sweep_lookback": 25, "atr_sl_mult": 1.0, "atr_tp_mult": 1.5, "regime_filter": False, "min_confidence": 0.4},
    # Medium SL/TP (1.5/2.5) with different lookbacks
    {"sweep_lookback": 15, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "regime_filter": False, "min_confidence": 0.5},
    {"sweep_lookback": 20, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "regime_filter": False, "min_confidence": 0.5},
    {"sweep_lookback": 25, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "regime_filter": False, "min_confidence": 0.5},
    # Wide SL/TP (2.0/3.0) with different lookbacks
    {"sweep_lookback": 15, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "regime_filter": False, "min_confidence": 0.6},
    {"sweep_lookback": 20, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "regime_filter": False, "min_confidence": 0.6},
    {"sweep_lookback": 25, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "regime_filter": False, "min_confidence": 0.6},
]

# PBO configurations
PBO_CONFIGS = [
    {"sweep_lookback": 15, "atr_sl_mult": 1.0, "atr_tp_mult": 1.5, "regime_filter": False, "min_confidence": 0.4, "name": "LS_Tight15"},
    {"sweep_lookback": 20, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "regime_filter": False, "min_confidence": 0.5, "name": "LS_Med20"},
    {"sweep_lookback": 25, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "regime_filter": False, "min_confidence": 0.6, "name": "LS_Wide25"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "sweep_lookback": 20,
    "atr_sl_mult": 1.5,
    "atr_tp_mult": 2.5,
    "regime_filter": False,
    "min_confidence": 0.5,
}


def liquidity_sweep_optimized_factory(**kwargs) -> LiquiditySweepOptimized:
    return LiquiditySweepOptimized(**kwargs)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: OPTIMIZED LIQUIDITY SWEEP STRATEGY")
    print("=" * 80)
    print("\nOptimization goals:")
    print("- Test different SL/TP multipliers (1.0-2.0x ATR)")
    print("- Test different lookback periods (15-25 bars)")
    print("- Disable regime filter to capture more signals")
    print("- Adjust confidence threshold")

    validator = StrategyValidator(
        strategy_factory=liquidity_sweep_optimized_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=STRATEGY_NAME,
        config=ValidationConfig(),
    )

    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    data = load_ohlcv_csv(data_path)
    timestamps = generate_timestamps(len(data["close"]))

    result = validator.run(data=data, timestamps=timestamps)

    report = validator.generate_report(result)
    print("\n\n" + report)

    # Save report
    report_path = ROOT / "reports" / "liquidity_sweep_optimized_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
