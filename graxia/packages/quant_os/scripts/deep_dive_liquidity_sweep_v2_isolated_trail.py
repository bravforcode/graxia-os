"""
Deep Dive Validation: LiquiditySweepV2 (ISOLATED TRAIL TEST)
=============================================================
Isolates the effect of widening trailing stop from 2.0 to 3.0 ATR.
Keeps RSI at original 35/65 to avoid flooding with low-quality signals.

Key insight from previous run:
- Wider trail alone improved Sharpe (-2.19 -> better) by giving moves room
- But loosening RSI to 40/60 flooded in noise (win rate dropped 39% -> 33%)
- This test keeps RSI tight to isolate the trail effect

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

STRATEGY_NAME = "Liquidity Sweep V2 (Isolated Trail Test: trail=3.0, RSI=35/65)"

# Isolate trail effect: keep RSI original, vary trail + TP + SL
PARAM_GRID = [
    # Core: trail=3.0, RSI=35/65 (original), TP=2.5
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 3.0},
    # Wider TP with wider trail
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "atr_trail_mult": 3.0},
    # Even wider TP + tighter SL (high R:R bet)
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.0, "atr_tp_mult": 3.5, "atr_trail_mult": 3.0},
    # Shorter lookback + wide trail
    {"sweep_lookback": 15, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 3.0},
    # Longer lookback + wide trail
    {"sweep_lookback": 25, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "atr_trail_mult": 3.0},
    # Wide trail + conservative SL
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 2.0, "atr_tp_mult": 3.5, "atr_trail_mult": 3.0},
    # Trail=2.5 (middle ground between 2.0 and 3.0)
    {"sweep_lookback": 20, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.5},
]

PBO_CONFIGS = [
    {"sweep_lookback": 20, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 3.0, "name": "LS2_T3_TP25"},
    {"sweep_lookback": 20, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "atr_trail_mult": 3.0, "name": "LS2_T3_TP30"},
    {"sweep_lookback": 20, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.0, "atr_tp_mult": 3.5, "atr_trail_mult": 3.0, "name": "LS2_T3_TP35"},
    {"sweep_lookback": 15, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 3.0, "name": "LS2_LB15_T3"},
    {"sweep_lookback": 20, "rsi_oversold": 35, "rsi_overbought": 65,
     "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "atr_trail_mult": 2.5, "name": "LS2_T25"},
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
    "atr_trail_mult": 3.0,
    "regime_filter": False,
}


def sweep_v2_factory(**kwargs) -> LiquiditySweepV2:
    return LiquiditySweepV2(**kwargs)


def main() -> str:
    print("=" * 80)
    print("DEEP DIVE VALIDATION: LIQUIDITY SWEEP V2 (ISOLATED TRAIL TEST)")
    print("Isolating trail effect: trail 2.0->3.0, RSI stays 35/65")
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

    report_path = ROOT / "reports" / "liquidity_sweep_v2_isolated_trail_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
