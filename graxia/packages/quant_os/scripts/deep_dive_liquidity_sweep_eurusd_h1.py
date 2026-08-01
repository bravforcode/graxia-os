"""
Deep Dive Validation: Liquidity Sweep on EURUSD H1
===================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: LiquiditySweepStrategy
Symbol: EURUSD H1 (forex has good liquidity data)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.strategies.liquidity_sweep import LiquiditySweepStrategy
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)
from quant_os.strategies.base import StrategyConfig

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Liquidity Sweep EURUSD H1"

# LiquiditySweep has minimal parameters - use single config
PARAM_GRID = [
    {"config": None},
]

# PBO configurations
PBO_CONFIGS = [
    {"config": None, "name": "LiqSweep_EURUSD_H1"},
]

# Default parameters
DEFAULT_PARAMS = {
    "config": None,
}


def liquidity_sweep_factory(**kwargs) -> LiquiditySweepStrategy:
    config = kwargs.get("config")
    if config is None:
        config = StrategyConfig(name="LiquiditySweep_EURUSD_H1")
    return LiquiditySweepStrategy(config=config)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: LIQUIDITY SWEEP ON EURUSD H1")
    print("=" * 80)

    validator = StrategyValidator(
        strategy_factory=liquidity_sweep_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=STRATEGY_NAME,
        config=ValidationConfig(),
    )

    data_path = ROOT / "data" / "EURUSD_H1.csv"
    data = load_ohlcv_csv(data_path, skip_zero_volume=False)
    timestamps = generate_timestamps(len(data["close"]))

    result = validator.run(data=data, timestamps=timestamps)

    report = validator.generate_report(result)
    print("\n\n" + report)

    report_path = ROOT / "reports" / "liquidity_sweep_eurusd_h1_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
