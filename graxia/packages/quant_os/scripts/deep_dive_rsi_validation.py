"""
Deep Dive Validation: RSI Mean Reversion Strategy
===================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: RSIMeanReversion(rsi_period=14, oversold=30, overbought=70)
Symbol: XAUUSD D1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.strategies.rsi_mean_reversion import RSIMeanReversion
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "RSI Mean Reversion"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"rsi_period": 14, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
    {"rsi_period": 14, "oversold": 25, "overbought": 75, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
    {"rsi_period": 14, "oversold": 20, "overbought": 80, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5},
    {"rsi_period": 10, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
    {"rsi_period": 21, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5},
    {"rsi_period": 14, "oversold": 35, "overbought": 65, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
    {"rsi_period": 14, "oversold": 30, "overbought": 70, "ema_period": 50, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
]

# PBO configurations
PBO_CONFIGS = [
    {"rsi_period": 14, "oversold": 25, "overbought": 75, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "name": "RSI14_25_75"},
    {"rsi_period": 14, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "name": "RSI14_30_70"},
    {"rsi_period": 14, "oversold": 35, "overbought": 65, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "name": "RSI14_35_65"},
    {"rsi_period": 10, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "name": "RSI10_30_70"},
    {"rsi_period": 21, "oversold": 30, "overbought": 70, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5, "name": "RSI21_30_70"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "rsi_period": 14,
    "oversold": 30,
    "overbought": 70,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def rsi_factory(**kwargs) -> RSIMeanReversion:
    """Create an RSIMeanReversion strategy with given parameters."""
    return RSIMeanReversion(**kwargs)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive RSI Mean Reversion validation."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: RSI MEAN REVERSION")
    print("=" * 80)

    # Create validator
    validator = StrategyValidator(
        strategy_factory=rsi_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=STRATEGY_NAME,
        config=ValidationConfig(),
    )

    # Load data
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    data = load_ohlcv_csv(data_path)
    timestamps = generate_timestamps(len(data["close"]))

    # Run validation
    result = validator.run(data=data, timestamps=timestamps)

    # Generate report
    report = validator.generate_report(result)
    print("\n\n" + report)

    # Save report
    report_path = ROOT / "reports" / "rsi_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
