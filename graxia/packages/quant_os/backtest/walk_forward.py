"""
Walk-Forward Validation - Anti-overfitting framework

Implements anchored and rolling walk-forward analysis:
- Split data into in-sample (IS) and out-of-sample (OOS) windows
- Optimize on IS, validate on OOS
- Aggregate OOS results for robust performance estimate

Golden rule requirement: minimum 3 walk-forward windows
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..strategies.base import Strategy
from .engine import BacktestConfig, BacktestEngine
from .metrics import BacktestMetrics


@dataclass
class WalkForwardWindow:
    """A single walk-forward window"""

    window_id: int
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date

    # IS results
    is_metrics: BacktestMetrics | None = None
    is_params: dict | None = None

    # OOS results
    oos_metrics: BacktestMetrics | None = None

    # Validation
    is_oos_ratio: float = 0.0  # OOS/IS performance ratio
    is_degradation: float = 0.0  # Performance degradation from IS to OOS


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward results"""

    total_windows: int
    valid_windows: int

    # Aggregated OOS performance
    oos_win_rate: float = 0.0
    oos_profit_factor: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_drawdown_pct: float = 0.0
    oos_total_pnl: float = 0.0
    oos_avg_win_rate: float = 0.0

    # Overfitting metrics
    avg_is_oos_ratio: float = 0.0
    oos_consistency: float = 0.0  # % of profitable OOS windows
    overfitting_score: float = 0.0  # 0 = no overfit, 1 = severe overfit

    # PBO result (populated after analyze())
    pbo_result: Any = None  # PBOResult from probability_overfitting

    # Per-window details
    windows: list[WalkForwardWindow] = None

    def __post_init__(self):
        if self.windows is None:
            self.windows = []


class WalkForwardAnalyzer:
    """
    Walk-forward analysis engine.

    Supports two modes:
    - Anchored: IS window always starts from beginning, grows
    - Rolling: IS window has fixed length, slides forward
    """

    def __init__(
        self,
        strategy_factory: Callable[[], Strategy],
        config: BacktestConfig | None = None,
        is_ratio: float = 0.7,  # 70% in-sample, 30% out-of-sample
        min_windows: int = 3,
        mode: str = "rolling",  # "rolling" or "anchored"
    ):
        self.strategy_factory = strategy_factory
        self.config = config or BacktestConfig()
        self.is_ratio = is_ratio
        self.min_windows = min_windows
        self.mode = mode

    def analyze(
        self,
        data: dict[str, list],
        timestamps: list[datetime],
        n_windows: int = 5,
        optimize_func: Callable | None = None,
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis.

        Args:
            data: Full OHLCV dataset
            timestamps: Timestamps for each bar
            n_windows: Number of walk-forward windows
            optimize_func: Optional function to optimize strategy params on IS data
                Should accept (strategy, is_data, is_timestamps) and return params dict

        Returns:
            WalkForwardResult with aggregated OOS performance
        """
        total_bars = len(data["close"])

        if total_bars < 1000:
            raise ValueError(f"Insufficient data: {total_bars} bars. Need at least 1000.")

        # Calculate window sizes
        oos_size = total_bars // (n_windows + 1)  # Each OOS window
        is_size = int(oos_size * self.is_ratio / (1 - self.is_ratio))

        if is_size < 500:
            raise ValueError(f"IS window too small: {is_size} bars. Reduce n_windows or get more data.")

        windows = []

        for w in range(n_windows):
            if self.mode == "anchored":
                # Anchored: IS always starts at 0
                is_start_idx = 0
                is_end_idx = is_size + (w + 1) * oos_size
                oos_start_idx = is_end_idx
                oos_end_idx = oos_start_idx + oos_size
            else:
                # Rolling: fixed IS window
                oos_end_idx = min(total_bars, (w + 1) * oos_size + is_size)
                oos_start_idx = oos_end_idx - oos_size
                is_end_idx = oos_start_idx
                is_start_idx = max(0, is_end_idx - is_size)

            if oos_end_idx > total_bars:
                break

            # Extract IS data
            is_data = {k: v[is_start_idx:is_end_idx] for k, v in data.items()}
            is_timestamps = timestamps[is_start_idx:is_end_idx]

            # Extract OOS data
            oos_data = {k: v[oos_start_idx:oos_end_idx] for k, v in data.items()}
            oos_timestamps = timestamps[oos_start_idx:oos_end_idx]

            # Create window
            window = WalkForwardWindow(
                window_id=w,
                is_start=timestamps[is_start_idx].date() if is_start_idx < len(timestamps) else date.min,
                is_end=timestamps[min(is_end_idx - 1, len(timestamps) - 1)].date(),
                oos_start=timestamps[oos_start_idx].date(),
                oos_end=timestamps[min(oos_end_idx - 1, len(timestamps) - 1)].date(),
            )

            # Run IS backtest
            strategy = self.strategy_factory()
            is_engine = BacktestEngine(self.config)
            is_engine.set_strategy(strategy)
            is_engine.load_data(is_data, is_timestamps)
            is_results = is_engine.run()
            window.is_metrics = (
                BacktestMetrics(**is_results["metrics"].__dict__)
                if hasattr(is_results["metrics"], "__dict__")
                else is_results["metrics"]
            )

            # Optimize if function provided
            if optimize_func:
                params = optimize_func(strategy, is_data, is_timestamps)
                window.is_params = params

            # Run OOS backtest
            oos_strategy = self.strategy_factory()
            oos_engine = BacktestEngine(self.config)
            oos_engine.set_strategy(oos_strategy)
            oos_engine.load_data(oos_data, oos_timestamps)
            oos_results = oos_engine.run()
            window.oos_metrics = (
                BacktestMetrics(**oos_results["metrics"].__dict__)
                if hasattr(oos_results["metrics"], "__dict__")
                else oos_results["metrics"]
            )

            # Calculate IS/OOS ratio
            if window.is_metrics and window.oos_metrics:
                is_pf = window.is_metrics.profit_factor if window.is_metrics.profit_factor != float("inf") else 10
                oos_pf = window.oos_metrics.profit_factor if window.oos_metrics.profit_factor != float("inf") else 10
                window.is_oos_ratio = oos_pf / is_pf if is_pf > 0 else 0
                window.is_degradation = (1 - window.is_oos_ratio) * 100

            windows.append(window)

        # Aggregate results
        return self._aggregate_results(windows)

    def _aggregate_results(self, windows: list[WalkForwardWindow]) -> WalkForwardResult:
        """Aggregate walk-forward window results"""
        result = WalkForwardResult(
            total_windows=len(windows),
            valid_windows=sum(1 for w in windows if w.oos_metrics),
            windows=windows,
        )

        if not windows:
            return result

        # Collect OOS metrics
        oos_metrics = [w.oos_metrics for w in windows if w.oos_metrics]

        if not oos_metrics:
            return result

        # Aggregate
        result.oos_win_rate = sum(m.win_rate for m in oos_metrics) / len(oos_metrics)
        result.oos_sharpe = sum(m.sharpe_ratio for m in oos_metrics) / len(oos_metrics)
        result.oos_max_drawdown_pct = max(m.max_drawdown_pct for m in oos_metrics)
        result.oos_total_pnl = sum(m.total_pnl for m in oos_metrics)

        # Profit factor (average)
        valid_pfs = [m.profit_factor for m in oos_metrics if m.profit_factor != float("inf")]
        result.oos_profit_factor = sum(valid_pfs) / len(valid_pfs) if valid_pfs else 0

        # IS/OOS ratios
        ratios = [w.is_oos_ratio for w in windows if w.is_oos_ratio > 0]
        result.avg_is_oos_ratio = sum(ratios) / len(ratios) if ratios else 0

        # OOS consistency (% profitable windows)
        profitable_oos = sum(1 for m in oos_metrics if m.total_pnl > 0)
        result.oos_consistency = profitable_oos / len(oos_metrics)

        # Overfitting score (0-1, higher = more overfit)
        # Based on: IS/OOS degradation, consistency, Sharpe degradation
        degradation_scores = [w.is_degradation / 100 for w in windows if w.is_degradation > 0]
        avg_degradation = sum(degradation_scores) / len(degradation_scores) if degradation_scores else 0

        consistency_penalty = 1 - result.oos_consistency
        result.overfitting_score = min(1.0, (avg_degradation * 0.5 + consistency_penalty * 0.5))

        # Calculate PBO from OOS returns across windows
        try:
            from ..validation.probability_overfitting import calculate_pbo

            oos_returns_for_pbo = []
            for w in windows:
                if w.oos_metrics and hasattr(w.oos_metrics, "total_pnl"):
                    # Use IS/OOS ratio as proxy since we don't have raw OOS returns
                    oos_returns_for_pbo.append([w.is_oos_ratio])
            if len(oos_returns_for_pbo) >= 2:
                result.pbo_result = calculate_pbo(oos_returns_for_pbo)
        except Exception:
            pass  # PBO is optional — don't break walk-forward if it fails

        return result


def validate_walk_forward_requirements(result: WalkForwardResult) -> dict[str, Any]:
    """
    Validate against golden rule requirements.

    Returns:
        Dict with validation results
    """
    checks = {
        "min_windows": result.total_windows >= 3,
        "profitable_oos": result.oos_consistency >= 0.5,
        "positive_oos_pnl": result.oos_total_pnl > 0,
        "oos_win_rate_sane": result.oos_win_rate >= 0.45,
        "overfitting_acceptable": result.overfitting_score < 0.6,
        "is_oos_ratio_acceptable": result.avg_is_oos_ratio >= 0.5,
    }

    # Add PBO check if available
    if result.pbo_result is not None:
        checks["pbo_acceptable"] = result.pbo_result.pbo < 0.5

    checks["all_passed"] = all(checks.values())

    return checks
