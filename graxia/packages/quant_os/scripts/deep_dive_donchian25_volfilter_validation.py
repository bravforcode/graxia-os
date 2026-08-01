"""
Deep Dive Validation: Donchian(25) + Vol Filter (>1.0x median ATR ratio)
=========================================================================
Tie-breaker run for the config claimed as "GENUINE EDGE p<0.001" in
reports/final_strategy_summary.json (2026-07-10T21:48), which contradicts
the same-day search report (reports/final_strategy_search_report.json,
17:56) that found this exact Donchian(25) config only at p=0.08
("SUGGESTIVE ... Accept no edge found").

The original script behind the "GENUINE EDGE" claim (a 100-shuffle
permutation test on trade-level Sharpe) was never located in the repo and
was never run through the standard 5-gate harness (walk-forward, DSR, PBO,
bootstrap, cost stress) that every other strategy in this repo went
through. This script closes that gap using the existing StrategyValidator
harness, on the same symbols (EURUSD, GBPUSD) the claim was made on.

Strategy: DonchianRSI(period=25, vol_filter=True, vol_filter_pctile=1.0)
with the RSI filter disabled (thresholds at 100/0) so the tested logic
matches the claimed strategy: "Breakout above 25-bar high (long) or below
25-bar low (short)" + "Only trade when daily ATR > 1.0x median ATR ratio".
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # quant_os/
GRAXIA = ROOT.parent  # graxia/packages/
REPO_ROOT = GRAXIA.parent.parent  # graxia os/ (parent of graxia/)
sys.path.insert(0, str(GRAXIA))
sys.path.insert(0, str(REPO_ROOT))

from quant_os.strategies.donchian_rsi import DonchianRSI
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

STRATEGY_NAME = "Donchian(25)+VolFilter(1.0x median ATR)"

# RSI thresholds disabled (100/0) so the RSI confirmation filter never
# rejects a signal -- matches the claimed strategy, which has no RSI logic.
NO_RSI = {"rsi_overbought": 100.0, "rsi_oversold": 0.0}

PARAM_GRID = [
    {"period": 20, "vol_filter": True, "vol_filter_pctile": 0.9, **NO_RSI},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 0.9, **NO_RSI},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 1.0, **NO_RSI},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 1.1, **NO_RSI},
    {"period": 30, "vol_filter": True, "vol_filter_pctile": 1.0, **NO_RSI},
    {"period": 30, "vol_filter": True, "vol_filter_pctile": 1.1, **NO_RSI},
]

PBO_CONFIGS = [
    {"period": 20, "vol_filter": True, "vol_filter_pctile": 0.9, **NO_RSI, "name": "DC20_VF0.9"},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 0.9, **NO_RSI, "name": "DC25_VF0.9"},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 1.0, **NO_RSI, "name": "DC25_VF1.0"},
    {"period": 25, "vol_filter": True, "vol_filter_pctile": 1.1, **NO_RSI, "name": "DC25_VF1.1"},
    {"period": 30, "vol_filter": True, "vol_filter_pctile": 1.0, **NO_RSI, "name": "DC30_VF1.0"},
]

DEFAULT_PARAMS = {
    "period": 25,
    "atr_period": 14,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
    "vol_filter": True,
    "vol_filter_pctile": 1.0,
    **NO_RSI,
}


def donchian_factory(**kwargs) -> DonchianRSI:
    """Create a DonchianRSI strategy with given parameters."""
    valid_keys = {
        "period", "atr_period", "atr_sl_mult", "atr_tp_mult", "rsi_period",
        "rsi_overbought", "rsi_oversold", "vol_filter", "vol_filter_pctile",
        "vol_lookback",
    }
    filtered = {k: v for k, v in kwargs.items() if k in valid_keys}
    return DonchianRSI(**filtered)


def run_symbol(symbol: str, csv_name: str, report_name: str) -> str:
    print("=" * 80)
    print(f"DEEP DIVE VALIDATION: {STRATEGY_NAME} -- {symbol}")
    print("=" * 80)

    validator = StrategyValidator(
        strategy_factory=donchian_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=f"{STRATEGY_NAME} ({symbol})",
        config=ValidationConfig(strategy_symbol=symbol, strategy_timeframe="D1"),
    )

    data_path = ROOT / "data" / csv_name
    # FX spot data has no real centralized volume (mostly 0) -- unlike the
    # skip_zero_volume default (built for XAUUSD pre-2007 synthetic bars),
    # don't drop bars here or almost the whole series is discarded.
    data = load_ohlcv_csv(data_path, skip_zero_volume=False)
    timestamps = generate_timestamps(len(data["close"]))

    result = validator.run(data=data, timestamps=timestamps)
    report = validator.generate_report(result)
    print("\n\n" + report)

    report_path = ROOT / "reports" / report_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


def main() -> None:
    run_symbol("EURUSD", "EURUSD_D1.csv", "donchian25_volfilter_eurusd_edge_verification.txt")
    run_symbol("GBPUSD", "GBPUSD_D1.csv", "donchian25_volfilter_gbpusd_edge_verification.txt")


if __name__ == "__main__":
    main()
