"""
Deep Dive Validation: Momentum Factor Rotation Strategy
========================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: MomentumFactorRotation (multi-asset TSMOM rotation)
Symbol: XAUUSD D1 (single asset for validation)
"""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.core.enums import RegimeType, SignalType
from quant_os.strategies.base import Signal, Strategy, StrategyConfig
from quant_os.strategies.momentum_factor_rotation import (
    MomentumFactorRotationConfig,
    compute_momentum_factor_rotation,
)
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)


# ── Wrapper Strategy Class ────────────────────────────────────────────────

class MomentumFactorRotationStrategy(Strategy):
    """Wrapper for MomentumFactorRotation to work with BacktestEngine.

    Note: This is a simplified single-asset version for validation.
    The full multi-asset rotation requires multiple price series.
    """

    def __init__(self, lookback: int = 63, vol_target: float = 0.10, min_signal_strength: float = 0.3):
        config = StrategyConfig(
            name="MomentumFactorRotation",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
        )
        super().__init__(config)
        self.lookback = lookback
        self.vol_target = vol_target
        self.min_signal_strength = min_signal_strength

    def required_features(self) -> list[str]:
        return ["close"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])

        if len(close) < self.lookback + 20:
            return None

        # Simple TSMOM signal for single asset
        # Compare current price to N-bar ago price
        returns = []
        for i in range(1, min(self.lookback + 1, len(close))):
            if close[-i - 1] > 0:
                ret = (float(close[-1]) / float(close[-i - 1])) - 1.0
                returns.append(ret)

        if not returns:
            return None

        # Annualize the return
        ann_return = float(close[-1]) / float(close[-self.lookback - 1]) if close[-self.lookback - 1] > 0 else 1.0
        ann_return = ann_return ** (252.0 / self.lookback) - 1.0

        # Simple momentum signal
        if ann_return > self.min_signal_strength:
            signal_type = SignalType.BUY
            confidence = min(ann_return / 0.5, 1.0)
        elif ann_return < -self.min_signal_strength:
            signal_type = SignalType.SELL
            confidence = min(abs(ann_return) / 0.5, 1.0)
        else:
            return None

        current_price = float(close[-1])

        # ATR for SL/TP
        if len(close) >= 20:
            recent = [float(c) for c in close[-20:]]
            atr = (max(recent) - min(recent)) / 20.0
        else:
            atr = current_price * 0.01

        if atr <= 0:
            atr = current_price * 0.01

        entry_price = Decimal(str(current_price))

        if signal_type == SignalType.BUY:
            stop_loss = Decimal(str(current_price - atr * 2.0))
            take_profit = Decimal(str(current_price + atr * 3.0))
        else:
            stop_loss = Decimal(str(current_price + atr * 2.0))
            take_profit = Decimal(str(current_price - atr * 3.0))

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Momentum Factor Rotation XAUUSD D1"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"lookback": 21, "vol_target": 0.10, "min_signal_strength": 0.2},
    {"lookback": 63, "vol_target": 0.10, "min_signal_strength": 0.3},
    {"lookback": 126, "vol_target": 0.10, "min_signal_strength": 0.3},
    {"lookback": 63, "vol_target": 0.15, "min_signal_strength": 0.25},
    {"lookback": 63, "vol_target": 0.08, "min_signal_strength": 0.35},
]

# PBO configurations
PBO_CONFIGS = [
    {"lookback": 21, "vol_target": 0.10, "min_signal_strength": 0.2, "name": "MFR_LB21"},
    {"lookback": 63, "vol_target": 0.10, "min_signal_strength": 0.3, "name": "MFR_LB63"},
    {"lookback": 126, "vol_target": 0.10, "min_signal_strength": 0.3, "name": "MFR_LB126"},
]

# Default parameters
DEFAULT_PARAMS = {
    "lookback": 63,
    "vol_target": 0.10,
    "min_signal_strength": 0.3,
}


def momentum_factor_rotation_factory(**kwargs) -> MomentumFactorRotationStrategy:
    return MomentumFactorRotationStrategy(**kwargs)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: MOMENTUM FACTOR ROTATION STRATEGY")
    print("=" * 80)

    validator = StrategyValidator(
        strategy_factory=momentum_factor_rotation_factory,
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

    report_path = ROOT / "reports" / "momentum_factor_rotation_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
