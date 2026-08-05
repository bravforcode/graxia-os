"""
Deep Dive Validation: Bollinger Squeeze Breakout Strategy
=========================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: BollingerSqueeze(bb_period=20, bb_std=2.0)
Symbol: XAUUSD D1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.strategies.bollinger_squeeze import BollingerSqueeze
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Bollinger Squeeze Breakout"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"bb_period": 15, "bb_std": 1.5, "squeeze_pctile": 0.15, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.20, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
    {"bb_period": 25, "bb_std": 2.5, "squeeze_pctile": 0.25, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.15, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.25, "atr_sl_mult": 2.5, "atr_tp_mult": 4.0},
]

# PBO configurations
PBO_CONFIGS = [
    {"bb_period": 15, "bb_std": 1.5, "squeeze_pctile": 0.15, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "name": "BB15_Std1.5"},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.20, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "name": "BB20_Std2.0"},
    {"bb_period": 25, "bb_std": 2.5, "squeeze_pctile": 0.25, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5, "name": "BB25_Std2.5"},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.15, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0, "name": "BB20_SQ15"},
    {"bb_period": 20, "bb_std": 2.0, "squeeze_pctile": 0.25, "atr_sl_mult": 2.5, "atr_tp_mult": 4.0, "name": "BB20_SQ25"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "bb_period": 20,
    "bb_std": 2.0,
    "squeeze_lookback": 120,
    "squeeze_pctile": 0.2,
    "atr_period": 14,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def bollinger_squeeze_factory(**kwargs) -> BollingerSqueeze:
    """Create a BollingerSqueeze strategy with given parameters."""
    return BollingerSqueeze(**kwargs)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive Bollinger Squeeze validation."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: BOLLINGER SQUEEZE BREAKOUT STRATEGY")
    print("=" * 80)

    # Create validator
    validator = StrategyValidator(
        strategy_factory=bollinger_squeeze_factory,
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
    report_path = ROOT / "reports" / "bollinger_squeeze_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    report = main()
