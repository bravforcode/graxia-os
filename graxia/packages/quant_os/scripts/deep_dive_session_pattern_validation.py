"""
Deep Dive Validation: Session Pattern Strategy
================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: SessionPattern (session-based mean reversion/momentum)
Symbol: XAUUSD D1
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
from quant_os.strategies.session_pattern import SPConfig, compute_sp_signals
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)


# ── Wrapper Strategy Class ────────────────────────────────────────────────

class SessionPatternStrategy(Strategy):
    """Wrapper for SessionPattern to work with BacktestEngine."""

    def __init__(self, session_window: int = 20, threshold_atr: float = 0.5, atr_period: int = 14):
        config = StrategyConfig(
            name="SessionPattern",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
        )
        super().__init__(config)
        self.session_window = session_window
        self.threshold_atr = threshold_atr
        self.atr_period = atr_period

    def required_features(self) -> list[str]:
        return ["close", "high", "low"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])

        if len(close) < 50:
            return None

        # Convert to pandas Series with DatetimeIndex
        timestamps = kwargs.get("current_time")
        if timestamps is None:
            timestamps = datetime.now(UTC)

        # Create a simple index for the last N bars
        n_bars = min(100, len(close))
        idx = pd.DatetimeIndex([timestamps - timedelta(days=i) for i in range(n_bars)][::-1])

        close_series = pd.Series(close[-n_bars:], index=idx)
        high_series = pd.Series(high[-n_bars:], index=idx)
        low_series = pd.Series(low[-n_bars:], index=idx)

        # Compute SP signals
        sp_config = SPConfig(
            session_window=self.session_window,
            threshold_atr=self.threshold_atr,
            atr_period=self.atr_period,
        )

        result = compute_sp_signals(
            close=close_series,
            highs=high_series,
            lows=low_series,
            timestamps=idx,
            config=sp_config,
        )

        # Get the last signal
        last_signal = result.signal.iloc[-1]

        if last_signal == 0:
            return None

        current_price = float(close[-1])
        atr = float(result.atr.iloc[-1]) if not pd.isna(result.atr.iloc[-1]) else current_price * 0.01

        if atr <= 0:
            atr = current_price * 0.01

        entry_price = Decimal(str(current_price))

        if last_signal == 1:  # Long
            stop_loss = Decimal(str(current_price - atr * 1.5))
            take_profit = Decimal(str(current_price + atr * 2.0))
            signal_type = SignalType.BUY
        else:  # Short
            stop_loss = Decimal(str(current_price + atr * 1.5))
            take_profit = Decimal(str(current_price - atr * 2.0))
            signal_type = SignalType.SELL

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=0.6,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Session Pattern XAUUSD D1"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"session_window": 15, "threshold_atr": 0.3, "atr_period": 10},
    {"session_window": 20, "threshold_atr": 0.5, "atr_period": 14},
    {"session_window": 25, "threshold_atr": 0.7, "atr_period": 14},
    {"session_window": 20, "threshold_atr": 0.4, "atr_period": 14},
    {"session_window": 20, "threshold_atr": 0.6, "atr_period": 14},
]

# PBO configurations
PBO_CONFIGS = [
    {"session_window": 15, "threshold_atr": 0.3, "atr_period": 10, "name": "SP_W15_T0.3"},
    {"session_window": 20, "threshold_atr": 0.5, "atr_period": 14, "name": "SP_W20_T0.5"},
    {"session_window": 25, "threshold_atr": 0.7, "atr_period": 14, "name": "SP_W25_T0.7"},
]

# Default parameters
DEFAULT_PARAMS = {
    "session_window": 20,
    "threshold_atr": 0.5,
    "atr_period": 14,
}


def session_pattern_factory(**kwargs) -> SessionPatternStrategy:
    return SessionPatternStrategy(**kwargs)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: SESSION PATTERN STRATEGY")
    print("=" * 80)

    validator = StrategyValidator(
        strategy_factory=session_pattern_factory,
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

    report_path = ROOT / "reports" / "session_pattern_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
