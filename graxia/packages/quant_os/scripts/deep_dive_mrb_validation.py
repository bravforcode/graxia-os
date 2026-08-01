"""
Deep Dive Validation: Mean Reversion Bollinger (MRB) Strategy
=============================================================
Higher-frequency validation on EURUSD M15 for statistical validity.

Strategy: MeanReversionBollinger (M15 timeframe)
Symbol: EURUSD M15
Data: ~50K bars (15-minute bars from 2020-2026)
"""

import sys
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # quant_os/
GRAXIA = ROOT.parent  # graxia/packages/
sys.path.insert(0, str(GRAXIA))

from quant_os.strategies.mrb import MeanReversionBollinger
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

# ── Strategy Configuration ────────────────────────────────────────────────

STRATEGY_NAME = "Mean Reversion Bollinger (MRB)"

# Parameter grid for walk-forward optimization (simplified for speed)
PARAM_GRID = [
    {"bb_period": 20, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65},
    {"bb_period": 15, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65},
    {"bb_period": 25, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65},
    {"bb_period": 20, "bb_std": 1.5, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65},
]

# PBO configurations (reduced for speed)
PBO_CONFIGS = [
    {"bb_period": 20, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65, "name": "MRB_20_2.0_25"},
    {"bb_period": 15, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65, "name": "MRB_15_2.0_25"},
    {"bb_period": 25, "bb_std": 2.0, "adx_threshold": 25.0, "stoch_oversold": 20, "stoch_overbought": 80, "rsi_oversold": 35, "rsi_overbought": 65, "name": "MRB_25_2.0_25"},
]

# Default parameters for baseline and cost stress tests
DEFAULT_PARAMS = {
    "bb_period": 20,
    "bb_std": 2.0,
    "adx_threshold": 25.0,
    "stoch_oversold": 20,
    "stoch_overbought": 80,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
}


# ── Strategy Factory ──────────────────────────────────────────────────────

def mrb_factory(**kwargs) -> MeanReversionBollinger:
    """Create a MeanReversionBollinger strategy with given parameters."""
    strategy = MeanReversionBollinger()
    # Override parameters
    for k, v in kwargs.items():
        if hasattr(strategy, k):
            setattr(strategy, k, v)
    return strategy


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> str:
    """Run comprehensive MRB validation on EURUSD M15."""
    print("=" * 80)
    print("DEEP DIVE VALIDATION: MEAN REVERSION BOLLINGER (M15)")
    print("=" * 80)

    # Create validator with M15-appropriate settings (optimized for speed)
    config = ValidationConfig(
        n_wf_folds=3,  # Reduced from 5 for speed
        wf_train_ratio=0.7,
        embargo_bars=50,  # More embargo for M15 (50 bars = ~12.5 hours)
        n_bootstrap_resamples=500,
        initial_capital=Decimal("10000"),
        risk_per_trade_bps=100,
        spread_pips=0.1,  # Tighter spread for EURUSD
        slippage_pips=0.05,
        commission_per_lot=Decimal("0.0"),
        annualization_factor=252 * 26,  # M15 = 252 * 26 sessions
        strategy_symbol="EURUSD",
        strategy_timeframe="M15",
    )

    validator = StrategyValidator(
        strategy_factory=mrb_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=STRATEGY_NAME,
        config=config,
    )

    # Load M15 data (limit to 15K bars for speed)
    data_path = ROOT / "data" / "EURUSD_M15.csv"
    full_data = load_ohlcv_csv(data_path)

    # Limit to last 15K bars (~156 days of M15 data)
    max_bars = 15000
    if len(full_data["close"]) > max_bars:
        data = {k: v[-max_bars:] for k, v in full_data.items()}
        print(f"Limited to last {max_bars} bars")
    else:
        data = full_data

    # For M15, generate 15-minute timestamps from the first timestamp
    from datetime import timedelta
    start_date = datetime(2024, 1, 2, tzinfo=UTC)  # Approximate start for limited M15 data
    timestamps = [start_date + timedelta(minutes=15 * i) for i in range(len(data["close"]))]

    # Run validation
    result = validator.run(data=data, timestamps=timestamps)

    # Generate report
    report = validator.generate_report(result)
    print("\n\n" + report)

    # Save report
    report_path = ROOT / "reports" / "mrb_eurusd_m15_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
