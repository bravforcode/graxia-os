"""
Deep Dive Validation: Volume Breakout Strategy
================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: VolumeBreakout(lookback=20, volume_threshold=2.0)
Symbol: XAUUSD D1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.strategies.volume_breakout import VolumeBreakout
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Volume Breakout"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"lookback": 15, "volume_threshold": 1.5},
    {"lookback": 20, "volume_threshold": 2.0},
    {"lookback": 25, "volume_threshold": 2.5},
    {"lookback": 20, "volume_threshold": 1.5},
    {"lookback": 20, "volume_threshold": 2.5},
]

# PBO configurations
PBO_CONFIGS = [
    {"lookback": 15, "volume_threshold": 1.5, "name": "VB_LB15_VT1.5"},
    {"lookback": 20, "volume_threshold": 2.0, "name": "VB_LB20_VT2.0"},
    {"lookback": 25, "volume_threshold": 2.5, "name": "VB_LB25_VT2.5"},
    {"lookback": 20, "volume_threshold": 1.5, "name": "VB_LB20_VT1.5"},
    {"lookback": 20, "volume_threshold": 2.5, "name": "VB_LB20_VT2.5"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "lookback": 20,
    "volume_threshold": 2.0,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def volume_breakout_factory(**kwargs) -> VolumeBreakout:
    """Create a VolumeBreakout strategy with given parameters."""
    return VolumeBreakout(**kwargs)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive Volume Breakout validation."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: VOLUME BREAKOUT STRATEGY")
    print("=" * 80)
    
    # Create validator
    validator = StrategyValidator(
        strategy_factory=volume_breakout_factory,
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
    report_path = ROOT / "reports" / "volume_breakout_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")
    
    return report


if __name__ == "__main__":
    report = main()
