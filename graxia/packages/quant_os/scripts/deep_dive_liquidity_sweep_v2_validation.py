"""
Deep Dive Validation: LiquiditySweepV2 Strategy
=================================================
Enhanced sweep strategy with trailing stops, RSI/volume filters, regime-aware sizing.
Symbol: XAUUSD D1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # quant_os/
GRAXIA = ROOT.parent  # graxia/packages/
sys.path.insert(0, str(GRAXIA))

from quant_os.strategies.liquidity_sweep_v2 import LiquiditySweepV2
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

STRATEGY_NAME = "Liquidity Sweep V2"

PARAM_GRID = [
    {"sweep_lookback": 15, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.0},
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.0},
    {"sweep_lookback": 25, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "atr_trail_mult": 2.5},
    {"sweep_lookback": 20, "rsi_period": 10, "rsi_oversold": 30, "rsi_overbought": 70, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0, "atr_trail_mult": 1.5},
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 40, "rsi_overbought": 60, "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "atr_trail_mult": 2.0},
    {"sweep_lookback": 15, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 1.0, "atr_tp_mult": 2.0, "atr_trail_mult": 1.5},
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 2.0, "atr_tp_mult": 3.5, "atr_trail_mult": 2.5, "volume_spike_mult": 1.5},
]

PBO_CONFIGS = [
    {"sweep_lookback": 15, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.0, "name": "LS2_LB15"},
    {"sweep_lookback": 20, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.0, "name": "LS2_LB20"},
    {"sweep_lookback": 25, "rsi_oversold": 35, "rsi_overbought": 65, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "atr_trail_mult": 2.5, "name": "LS2_LB25"},
    {"sweep_lookback": 20, "rsi_oversold": 30, "rsi_overbought": 70, "atr_sl_mult": 1.5, "atr_tp_mult": 2.0, "atr_trail_mult": 1.5, "name": "LS2_RSI30"},
    {"sweep_lookback": 20, "rsi_oversold": 40, "rsi_overbought": 60, "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "atr_trail_mult": 2.0, "name": "LS2_RSI40"},
]

DEFAULT_PARAMS = {
    "sweep_lookback": 20,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "volume_sma_period": 20,
    "volume_spike_mult": 1.2,
    "atr_period": 14,
    "atr_sl_mult": 1.5,
    "atr_tp_mult": 2.5,
    "atr_trail_mult": 2.0,
    "regime_filter": False,
}


def sweep_v2_factory(**kwargs) -> LiquiditySweepV2:
    return LiquiditySweepV2(**kwargs)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: LIQUIDITY SWEEP V2")
    print("=" * 80)

    validator = StrategyValidator(
        strategy_factory=sweep_v2_factory,
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

    report_path = ROOT / "reports" / "liquidity_sweep_v2_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
