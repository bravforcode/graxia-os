"""
Deep Dive Validation: COT Positioning Strategy
================================================
Runs comprehensive validation with:
1. Walk-forward analysis (5-fold, purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests (1.5x, 2x, 3x)

Strategy: COTPositioning (CFTC contrarian signal)
Symbol: XAUUSD D1 (weekly COT data forward-filled onto daily bars)

Uses REAL CFTC disaggregated COT parquet data (data/cot/cot_xauusd_disaggregated_fut_*.parquet)
via strategies/cot_positioning.py's pre-registered signal generator, not synthetic/price-derived
data. The COT signal is precomputed once per parameter set and looked up point-in-time (as-of,
no lookahead) for each daily bar using the bar's real calendar date.

generate_timestamps() (from strategy_validator) assigns FAKE sequential dates starting at
2007-01-02 to bars, regardless of the CSV's real dates. That lets us recover each bar's true
calendar date from current_time (bar_idx = (current_time - fake_start).days) and look it up
against the real weekly COT date index, independent of which WFA fold / PBO period slice the
strategy happens to be running against (BacktestEngine's `indicators` dict is always overwritten
with engine-internal technical indicators each bar and cannot carry external COT data through).

Real COT coverage is only ~2024-01 to ~2026-06 (129 weekly rows). The OHLCV series is truncated
to that window (plus warmup buffer) before validation so WFA folds / PBO periods aren't mostly
empty of any possible signal.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.core.enums import RegimeType
from quant_os.strategies.base import Signal, Strategy, StrategyConfig
from quant_os.strategies.cot_positioning import (
    COTPositioningConfig,
    compute_cot_positioning_signals,
    load_cot_data,
)
from quant_os.strategies.path_b_wrappers import _signal_with_atr_sl_tp
from quant_os.validation.strategy_validator import (
    StrategyValidator,
    ValidationConfig,
    load_ohlcv_csv,
    generate_timestamps,
)

_FAKE_START = datetime.fromisoformat("2007-01-02").replace(tzinfo=UTC)
_COT_RAW = load_cot_data(ROOT / "data" / "cot")
_REAL_DATES: list[datetime] = []  # populated by main() before validator.run()


def _load_real_dates(path: Path, skip_zero_volume: bool = True) -> list[datetime]:
    """Real calendar dates for the rows load_ohlcv_csv() keeps, in the same order."""
    df = pd.read_csv(path)
    if skip_zero_volume:
        df = df[df["volume"].astype(float) > 0]
    return [pd.Timestamp(t).to_pydatetime().replace(tzinfo=UTC) for t in df["time"]]


class COTPositioningStrategy(Strategy):
    """Wrapper for COTPositioning to work with BacktestEngine.

    Precomputes the real COT contrarian signal (via compute_cot_positioning_signals)
    once at construction, then does a point-in-time as-of lookup per bar using the
    bar's real calendar date recovered from current_time.
    """

    def __init__(self, lookback_weeks: int = 52, entry_z: float = 2.0, exit_z: float = 0.5):
        config = StrategyConfig(
            name="COTPositioning",
            version="1.0",
            symbols=["XAUUSD"],
            timeframes=["D1"],
        )
        super().__init__(config)
        self.lookback_weeks = lookback_weeks
        self.entry_z = entry_z
        self.exit_z = exit_z

        cot_config = COTPositioningConfig(
            lookback_weeks=lookback_weeks, entry_z=entry_z, exit_z=exit_z
        )
        result = compute_cot_positioning_signals(
            _COT_RAW["date"], _COT_RAW["net_positioning"], cot_config
        )
        aligned_dates = pd.DatetimeIndex(
            pd.DataFrame({
                "date": pd.to_datetime(_COT_RAW["date"]),
                "net_positioning": _COT_RAW["net_positioning"],
            }).dropna().sort_values("date").reset_index(drop=True)["date"]
        )
        self._cot_signal = pd.Series(result.signal.values, index=aligned_dates)
        self._cot_zscore = pd.Series(result.zscore.values, index=aligned_dates)

    def required_features(self) -> list[str]:
        return ["close"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data.get("close", [])
        current_time = kwargs.get("current_time")
        if not close or current_time is None or not _REAL_DATES:
            return None

        bar_idx = (current_time - _FAKE_START).days
        if bar_idx < 0 or bar_idx >= len(_REAL_DATES):
            return None
        real_date = pd.Timestamp(_REAL_DATES[bar_idx]).tz_localize(None)

        pos = self._cot_signal.asof(real_date)
        if pd.isna(pos) or pos == 0:
            return None

        z = self._cot_zscore.asof(real_date)
        confidence = min(abs(float(z)) / 3.0, 1.0) if pd.notna(z) else 0.5
        signal_value = confidence if pos > 0 else -confidence

        return _signal_with_atr_sl_tp(signal_value, symbol, self.id, ohlcv_data)


STRATEGY_NAME = "COT Positioning XAUUSD D1"

PARAM_GRID = [
    {"lookback_weeks": 26, "entry_z": 1.5, "exit_z": 0.3},
    {"lookback_weeks": 52, "entry_z": 2.0, "exit_z": 0.5},
    {"lookback_weeks": 78, "entry_z": 2.5, "exit_z": 0.7},
    {"lookback_weeks": 52, "entry_z": 1.8, "exit_z": 0.4},
    {"lookback_weeks": 52, "entry_z": 2.2, "exit_z": 0.6},
]

PBO_CONFIGS = [
    {"lookback_weeks": 26, "entry_z": 1.5, "exit_z": 0.3, "name": "COT_W26_Z1.5"},
    {"lookback_weeks": 52, "entry_z": 2.0, "exit_z": 0.5, "name": "COT_W52_Z2.0"},
    {"lookback_weeks": 78, "entry_z": 2.5, "exit_z": 0.7, "name": "COT_W78_Z2.5"},
]

DEFAULT_PARAMS = {
    "lookback_weeks": 52,
    "entry_z": 2.0,
    "exit_z": 0.5,
}


def cot_positioning_factory(**kwargs) -> COTPositioningStrategy:
    return COTPositioningStrategy(**kwargs)


def main() -> str:
    global _REAL_DATES

    print("=" * 80)
    print("DEEP DIVE VALIDATION: COT POSITIONING STRATEGY (real CFTC data)")
    print("=" * 80)

    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    data = load_ohlcv_csv(data_path)
    real_dates = _load_real_dates(data_path)
    assert len(real_dates) == len(data["close"]), (
        f"date/row alignment mismatch: {len(real_dates)} dates vs {len(data['close'])} bars"
    )

    cot_min_date = pd.Timestamp(_COT_RAW["date"].min()).to_pydatetime().replace(tzinfo=UTC)
    start_idx = next((i for i, d in enumerate(real_dates) if d >= cot_min_date), 0)
    start_idx = max(0, start_idx - 20)  # ATR/indicator warmup buffer

    data = {k: v[start_idx:] for k, v in data.items()}
    real_dates = real_dates[start_idx:]
    print(f"  Scoped to COT-covered window: {real_dates[0].date()} .. {real_dates[-1].date()} "
          f"({len(real_dates)} bars, from {len(_load_real_dates(data_path))} total)")

    _REAL_DATES = real_dates
    timestamps = generate_timestamps(len(data["close"]))

    validator = StrategyValidator(
        strategy_factory=cot_positioning_factory,
        param_grid=PARAM_GRID,
        pbo_configs=PBO_CONFIGS,
        default_params=DEFAULT_PARAMS,
        strategy_name=STRATEGY_NAME,
        config=ValidationConfig(),
    )

    result = validator.run(data=data, timestamps=timestamps)

    report = validator.generate_report(result)
    print("\n\n" + report)

    report_path = ROOT / "reports" / "cot_positioning_edge_verification.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
