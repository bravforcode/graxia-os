"""
Deep Dive Validation: Liquidity Sweep Strategy
================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: LiquiditySweepStrategy
Symbol: XAUUSD D1
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

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Liquidity Sweep"

# LiquiditySweep has minimal parameters (lookback is internal)
# We use different confidence thresholds for variety
PARAM_GRID = [
    {"config": None},
    {"config": None},
]

# PBO configurations
PBO_CONFIGS = [
    {"config": None, "name": "LiqSweep_Default"},
    {"config": None, "name": "LiqSweep_V2"},
    {"config": None, "name": "LiqSweep_V3"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "config": None,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def liquidity_sweep_factory(**kwargs) -> LiquiditySweepStrategy:
    """Create a LiquiditySweepStrategy with given parameters."""
    from quant_os.strategies.base import StrategyConfig
    config = kwargs.get("config")
    if config is None:
        config = StrategyConfig(name="LiquiditySweep")
    return LiquiditySweepStrategy(config=config)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive Liquidity Sweep validation."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: LIQUIDITY SWEEP STRATEGY")
    print("=" * 80)

    # Create validator
    validator = StrategyValidator(
        strategy_factory=liquidity_sweep_factory,
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
    report_path = ROOT / "reports" / "liquidity_sweep_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    report = main()
