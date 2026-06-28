"""
Walk-forward validation automation for strategies.

Automates the train/test walk-forward protocol:
1. Split historical data into rolling (train, test) windows with embargo gap.
2. Run the strategy on each window's train split (in-sample), then on the
   test split (out-of-sample).
3. Aggregate metrics across folds and compute overfitting indicators.

Overfitting metrics
-------------------
- **OOS degradation ratio** — how much OOS Sharpe drops vs IS Sharpe.
- **Stability score** — cross-fold std of OOS Sharpe (lower = more stable).
- **Deflated Sharpe ratio** — accounts for multiple testing.
- **Probability of overfitting** — POOMA heuristic from Bailey et al.

Usage
-----
    validator = WalkForwardValidator(strategy, data, n_folds=5)
    results   = validator.run_validation()
    summary   = validator.get_results()
    compare   = WalkForwardValidator.compare_strategies(strat_a, strat_b, data)
"""

from __future__ import annotations

import math
import structlog
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

try:
    from ..core.enums import RegimeType
except ImportError:
    from core.enums import RegimeType

logger = structlog.get_logger(__name__)

# ── protocols ───────────────────────────────────────────────────────────

class StrategyLike(Protocol):
    """Minimal interface for strategies usable in walk-forward validation."""

    @property
    def id(self) -> str: ...

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def required_features(self) -> list[str]: ...


# ── data classes ────────────────────────────────────────────────────────

@dataclass
class FoldMetrics:
    """Metrics for a single train or test fold."""

    total_bars: int
    signals_generated: int
    trades_taken: int
    wins: int
    losses: int
    win_rate: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0

    def __post_init__(self) -> None:
        if self.trades_taken > 0 and self.win_rate == 0.0:
            self.win_rate = self.wins / self.trades_taken


@dataclass
class WalkForwardFold:
    """Result of one walk-forward fold."""

    fold_index: int
    train_slice: tuple[int, int]
    test_slice: tuple[int, int]
    in_sample: FoldMetrics
    out_of_sample: FoldMetrics


@dataclass
class WalkForwardResults:
    """Aggregated walk-forward results across all folds."""

    strategy_id: str
    n_folds: int
    folds: list[WalkForwardFold]

    # aggregated OOS metrics
    oos_win_rate: float = 0.0
    oos_sharpe: float = 0.0
    oos_total_pnl_pct: float = 0.0
    oos_max_drawdown_pct: float = 0.0

    # IS metrics (averaged)
    is_win_rate: float = 0.0
    is_sharpe: float = 0.0

    # overfitting indicators
    oos_degradation_ratio: float = 0.0  # OOS_sharpe / IS_sharpe
    stability_score: float = 0.0  # 1 - normalised_std(OOS_sharpe)
    deflated_sharpe: float = 0.0
    probability_of_overfitting: float = 0.0

    # recommendation
    recommendation: str = ""
    passed: bool = False


@dataclass
class StrategyComparison:
    """Head-to-head comparison of two strategies via walk-forward."""

    strategy_a_id: str
    strategy_b_id: str
    results_a: WalkForwardResults
    results_b: WalkForwardResults
    winner: str  # strategy_id
    margin: float  # difference in OOS Sharpe
    details: dict[str, Any] = field(default_factory=dict)


# ── helpers ─────────────────────────────────────────────────────────────

def _sharpe(returns: Sequence[float], risk_free: float = 0.0, annualise: bool = True) -> float:
    """Annualised Sharpe from a list of per-trade returns."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 1e-9
    sr = (mean - risk_free) / std
    if annualise:
        sr *= math.sqrt(252)
    return sr


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    """Maximum drawdown percentage from an equity curve."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0


def _profit_factor(trades: Sequence[float]) -> float:
    """Profit factor (gross_profit / gross_loss)."""
    gross_profit = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _deflated_sharpe(sharpe_obs: float, n_trials: int, var_sharpe: float = 1.0) -> float:
    """
    Bailey & Lopez de Prado deflated Sharpe ratio.

    Adjusts observed Sharpe for multiple-testing bias.
    """
    if n_trials <= 1:
        return sharpe_obs
    # Expected max Sharpe under null (Euler-Mascheroni corrected)
    e_max = math.sqrt(2 * math.log(n_trials)) - (math.log(math.pi) + 0.5772) / (
        2 * math.sqrt(2 * math.log(n_trials))
    )
    # Deflated Sharpe
    deflated = (sharpe_obs - e_max * math.sqrt(var_sharpe)) / math.sqrt(var_sharpe)
    return deflated


def _pooma(is_sharpe: float, oos_sharpe: float, n_folds: int) -> float:
    """
    Probability of Overfitting via Minimum Backtest Length (POOMA) heuristic.

    Rough estimate: high when OOS Sharpe degrades significantly relative to
    IS Sharpe across few folds.
    """
    degradation = 1.0 - (oos_sharpe / is_sharpe if is_sharpe != 0 else 0.0)
    fold_penalty = 1.0 / max(n_folds, 1)
    return min(max(degradation * fold_penalty, 0.0), 1.0)


# ── walk-forward split ──────────────────────────────────────────────────

def _generate_splits(
    n_bars: int,
    n_folds: int,
    train_ratio: float,
    embargo_bars: int,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Yield ((train_start, train_end), (test_start, test_end)) index ranges.
    """
    fold_size = n_bars // n_folds
    train_size = int(fold_size * train_ratio)

    splits: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for i in range(n_folds):
        fold_start = i * fold_size
        train_start = fold_start
        train_end = fold_start + train_size
        test_start = train_end + embargo_bars
        test_end = min(fold_start + fold_size, n_bars)

        if test_start < test_end and train_end <= n_bars:
            splits.append(((train_start, train_end), (test_start, test_end)))

    return splits


# ── metrics evaluation ──────────────────────────────────────────────────

def _evaluate_strategy(
    strategy: StrategyLike,
    ohlcv_data: dict[str, list],
    start: int,
    end: int,
    symbol: str,
    regime: RegimeType | None = None,
) -> FoldMetrics:
    """
    Run a strategy on a slice of data and compute fold metrics.
    """
    signals = 0
    trades: list[float] = []
    wins = 0
    losses = 0
    equity = [10_000.0]  # arbitrary starting equity
    peak = equity[0]

    n_bars = min(end, len(ohlcv_data.get("close", [])))

    for i in range(max(start, strategy.required_features().__len__()), n_bars):
        # build sub-slice visible to strategy
        window = {
            k: v[max(0, i - 200): i + 1] for k, v in ohlcv_data.items() if isinstance(v, list)
        }

        sig = strategy.generate_signal(symbol, window, regime=regime)
        if sig is None:
            continue

        signals += 1
        # simulate simple trade: entry at current, exit 5 bars later (placeholder)
        entry_idx = i
        exit_idx = min(i + 5, n_bars - 1)
        if exit_idx <= entry_idx:
            continue

        entry_price = ohlcv_data.get("close", [0])[entry_idx]
        exit_price = ohlcv_data.get("close", [0])[exit_idx]

        if entry_price == 0:
            continue

        if sig.signal_type.value == "BUY":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        elif sig.signal_type.value == "SELL":
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:
            continue

        trades.append(pnl_pct)
        if pnl_pct > 0:
            wins += 1
        else:
            losses += 1

        equity.append(equity[-1] * (1 + pnl_pct / 100))

    total = len(trades)
    avg_pnl = sum(trades) / total if total > 0 else 0.0

    return FoldMetrics(
        total_bars=end - start,
        signals_generated=signals,
        trades_taken=total,
        wins=wins,
        losses=losses,
        win_rate=wins / total if total > 0 else 0.0,
        total_pnl_pct=sum(trades),
        max_drawdown_pct=_max_drawdown(equity),
        sharpe_ratio=_sharpe(trades),
        profit_factor=_profit_factor(trades),
    )


# ── main validator ──────────────────────────────────────────────────────

class WalkForwardValidator:
    """
    Automated walk-forward validation for any Strategy-compatible object.

    Parameters
    ----------
    strategy : StrategyLike
        The strategy under test.
    ohlcv_data : dict[str, list]
        Full historical OHLCV data (keys: open, high, low, close, volume).
    n_folds : int
        Number of walk-forward folds (default 5).
    train_ratio : float
        Fraction of each fold used for training (default 0.7).
    embargo_bars : int
        Gap between train and test to prevent leakage (default 0).
    symbol : str
        Symbol identifier (default "EURUSD").
    regime : RegimeType, optional
        Fixed regime for the run (if applicable).
    n_trials : int
        Total strategies tested (for deflated Sharpe correction).
    """

    def __init__(
        self,
        strategy: StrategyLike,
        ohlcv_data: dict[str, list],
        n_folds: int = 5,
        train_ratio: float = 0.7,
        embargo_bars: int = 0,
        symbol: str = "EURUSD",
        regime: RegimeType | None = None,
        n_trials: int = 1,
    ) -> None:
        self._strategy = strategy
        self._ohlcv = ohlcv_data
        self._n_folds = n_folds
        self._train_ratio = train_ratio
        self._embargo = embargo_bars
        self._symbol = symbol
        self._regime = regime
        self._n_trials = n_trials

        self._results: WalkForwardResults | None = None

        n_bars = len(ohlcv_data.get("close", []))
        self._splits = _generate_splits(n_bars, n_folds, train_ratio, embargo_bars)

        logger.info(
            "wf_init",
            strategy=strategy.id,
            n_bars=n_bars,
            n_folds=n_folds,
            actual_folds=len(self._splits),
        )

    # ── public API ─────────────────────────────────────────────────────

    def run_validation(self) -> WalkForwardResults:
        """
        Execute walk-forward validation across all splits.

        Returns ``WalkForwardResults`` with per-fold and aggregated metrics.
        """
        folds: list[WalkForwardFold] = []

        for idx, ((tr_s, tr_e), (te_s, te_e)) in enumerate(self._splits):
            logger.info(
                "wf_fold",
                fold=idx,
                train=(tr_s, tr_e),
                test=(te_s, te_e),
            )

            is_metrics = _evaluate_strategy(
                self._strategy, self._ohlcv, tr_s, tr_e, self._symbol, self._regime,
            )
            oos_metrics = _evaluate_strategy(
                self._strategy, self._ohlcv, te_s, te_e, self._symbol, self._regime,
            )

            folds.append(
                WalkForwardFold(
                    fold_index=idx,
                    train_slice=(tr_s, tr_e),
                    test_slice=(te_s, te_e),
                    in_sample=is_metrics,
                    out_of_sample=oos_metrics,
                )
            )

        results = self._aggregate(folds)
        self._results = results

        logger.info(
            "wf_complete",
            strategy=self._strategy.id,
            n_folds=len(folds),
            oos_sharpe=round(results.oos_sharpe, 4),
            degradation=round(results.oos_degradation_ratio, 4),
            recommendation=results.recommendation,
        )

        return results

    def get_results(self) -> WalkForwardResults | None:
        """
        Return cached results.  ``run_validation()`` must have been called.
        """
        return self._results

    @staticmethod
    def compare_strategies(
        strategy_a: StrategyLike,
        strategy_b: StrategyLike,
        ohlcv_data: dict[str, list],
        **kwargs: Any,
    ) -> StrategyComparison:
        """
        Head-to-head walk-forward comparison of two strategies.

        Parameters
        ----------
        strategy_a, strategy_b : StrategyLike
            The two strategies to compare.
        ohlcv_data : dict[str, list]
            Shared historical data.
        **kwargs
            Forwarded to both ``WalkForwardValidator`` constructors.

        Returns
        -------
        StrategyComparison
        """
        v_a = WalkForwardValidator(strategy_a, ohlcv_data, **kwargs)
        v_b = WalkForwardValidator(strategy_b, ohlcv_data, **kwargs)

        r_a = v_a.run_validation()
        r_b = v_b.run_validation()

        winner = r_a.strategy_id if r_a.oos_sharpe >= r_b.oos_sharpe else r_b.strategy_id
        margin = abs(r_a.oos_sharpe - r_b.oos_sharpe)

        comp = StrategyComparison(
            strategy_a_id=r_a.strategy_id,
            strategy_b_id=r_b.strategy_id,
            results_a=r_a,
            results_b=r_b,
            winner=winner,
            margin=margin,
            details={
                "a_oos_sharpe": round(r_a.oos_sharpe, 4),
                "b_oos_sharpe": round(r_b.oos_sharpe, 4),
                "a_oos_degradation": round(r_a.oos_degradation_ratio, 4),
                "b_oos_degradation": round(r_b.oos_degradation_ratio, 4),
                "a_stability": round(r_a.stability_score, 4),
                "b_stability": round(r_b.stability_score, 4),
            },
        )

        logger.info(
            "wf_compare",
            winner=winner,
            margin=round(margin, 4),
        )

        return comp

    # ── aggregation ────────────────────────────────────────────────────

    def _aggregate(self, folds: list[WalkForwardFold]) -> WalkForwardResults:
        """Compute aggregated metrics and overfitting indicators."""
        if not folds:
            return WalkForwardResults(
                strategy_id=self._strategy.id,
                n_folds=0,
                folds=[],
                recommendation="NO_DATA",
            )

        # IS aggregates
        is_sharpes = [f.in_sample.sharpe_ratio for f in folds]
        is_win_rates = [f.in_sample.win_rate for f in folds]

        # OOS aggregates
        oos_sharpes = [f.out_of_sample.sharpe_ratio for f in folds]
        oos_win_rates = [f.out_of_sample.win_rate for f in folds]
        oos_pnls = [f.out_of_sample.total_pnl_pct for f in folds]
        oos_drawdowns = [f.out_of_sample.max_drawdown_pct for f in folds]

        avg_is_sharpe = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0.0
        avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0
        avg_oos_win_rate = sum(oos_win_rates) / len(oos_win_rates) if oos_win_rates else 0.0
        total_oos_pnl = sum(oos_pnls)
        worst_dd = max(oos_drawdowns) if oos_drawdowns else 0.0

        # overfitting indicators
        degradation = 1.0 - (avg_oos_sharpe / avg_is_sharpe) if avg_is_sharpe != 0 else 1.0
        oos_std = (
            math.sqrt(sum((s - avg_oos_sharpe) ** 2 for s in oos_sharpes) / len(oos_sharpes))
            if len(oos_sharpes) > 1
            else 0.0
        )
        normalised_std = oos_std / (abs(avg_oos_sharpe) + 1e-9) if avg_oos_sharpe != 0 else 1.0
        stability = max(0.0, 1.0 - min(normalised_std, 1.0))

        deflated = _deflated_sharpe(avg_oos_sharpe, self._n_trials)
        pooma = _pooma(avg_is_sharpe, avg_oos_sharpe, len(folds))

        # ── recommendation logic ───────────────────────────────────────
        passed = True
        reasons: list[str] = []

        if avg_oos_sharpe < 0.5:
            passed = False
            reasons.append("low_oos_sharpe")
        if degradation > 0.5:
            passed = False
            reasons.append("high_degradation")
        if worst_dd > 15.0:
            passed = False
            reasons.append("excessive_drawdown")
        if stability < 0.4:
            passed = False
            reasons.append("unstable_across_folds")
        if poodma > 0.7 if (poodma := pooma) else False:
            passed = False
            reasons.append("high_overfitting_probability")

        recommendation = "PASS" if passed else f"FAIL: {', '.join(reasons)}"

        return WalkForwardResults(
            strategy_id=self._strategy.id,
            n_folds=len(folds),
            folds=folds,
            oos_win_rate=round(avg_oos_win_rate, 4),
            oos_sharpe=round(avg_oos_sharpe, 4),
            oos_total_pnl_pct=round(total_oos_pnl, 4),
            oos_max_drawdown_pct=round(worst_dd, 4),
            is_win_rate=round(sum(is_win_rates) / len(is_win_rates), 4) if is_win_rates else 0.0,
            is_sharpe=round(avg_is_sharpe, 4),
            oos_degradation_ratio=round(degradation, 4),
            stability_score=round(stability, 4),
            deflated_sharpe=round(deflated, 4),
            probability_of_overfitting=round(pooma, 4),
            recommendation=recommendation,
            passed=passed,
        )
