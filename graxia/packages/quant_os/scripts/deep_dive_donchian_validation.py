"""
Deep Dive Validation: Donchian Breakout Strategy
=================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: DonchianBreakout(period=20, vol_filter=True)
Symbol: XAUUSD D1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # quant_os/
GRAXIA = ROOT.parent  # graxia/packages/
sys.path.insert(0, str(GRAXIA))

from quant_os.strategies.donchian_rsi import DonchianRSI
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Donchian Breakout"

# Parameter grid for walk-forward optimization
PARAM_GRID = [
    {"period": 15, "atr_period": 14, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "vol_filter": True, "vol_filter_pctile": 0.7},
    {"period": 20, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "vol_filter": True, "vol_filter_pctile": 0.7},
    {"period": 25, "atr_period": 14, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5, "vol_filter": True, "vol_filter_pctile": 0.7},
    {"period": 30, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 2.5, "vol_filter": True, "vol_filter_pctile": 0.7},
    {"period": 20, "atr_period": 14, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0, "vol_filter": True, "vol_filter_pctile": 0.7},
    {"period": 20, "atr_period": 14, "atr_sl_mult": 2.5, "atr_tp_mult": 4.0, "vol_filter": True, "vol_filter_pctile": 0.7},
]

# PBO configurations
PBO_CONFIGS = [
    {"period": 15, "atr_period": 14, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "vol_filter": True, "vol_filter_pctile": 0.7, "name": "DC15_SL1.5"},
    {"period": 20, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "vol_filter": True, "vol_filter_pctile": 0.7, "name": "DC20_SL2.0"},
    {"period": 25, "atr_period": 14, "atr_sl_mult": 2.5, "atr_tp_mult": 3.5, "vol_filter": True, "vol_filter_pctile": 0.7, "name": "DC25_SL2.5"},
    {"period": 30, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 2.5, "vol_filter": True, "vol_filter_pctile": 0.7, "name": "DC30_SL2.0"},
    {"period": 20, "atr_period": 14, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0, "vol_filter": True, "vol_filter_pctile": 0.7, "name": "DC20_SL1.5"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "period": 20,
    "atr_period": 14,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
    "vol_filter": True,
    "vol_filter_pctile": 0.7,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def donchian_factory(**kwargs) -> DonchianRSI:
    """Create a DonchianRSI strategy with given parameters."""
    # Filter out keys that DonchianRSI doesn't accept
    valid_keys = {"period", "atr_period", "atr_sl_mult", "atr_tp_mult", "rsi_period", "rsi_overbought", "rsi_oversold", "vol_filter", "vol_filter_pctile", "vol_lookback"}
    filtered = {k: v for k, v in kwargs.items() if k in valid_keys}
    return DonchianRSI(**filtered)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive Donchian Breakout validation."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: DONCHIAN BREAKOUT STRATEGY")
    print("=" * 80)

    # Create validator
    validator = StrategyValidator(
        strategy_factory=donchian_factory,
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
    report_path = ROOT / "reports" / "donchian_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    report = main()
