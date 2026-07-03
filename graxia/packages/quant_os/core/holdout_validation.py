"""
Final Holdout Validation + Deflated Sharpe Ratio

Ensures strategy performance is validated on data never seen during development.
Includes multiple testing correction (deflated Sharpe) for 13 strategies.
"""

import math
from dataclasses import dataclass


@dataclass
class HoldoutResult:
    """Holdout validation result"""

    # Holdout performance
    holdout_sharpe: float
    holdout_win_rate: float
    holdout_profit_factor: float
    holdout_max_drawdown_pct: float
    holdout_total_pnl: float
    holdout_trades: int

    # Development performance (for comparison)
    dev_sharpe: float
    dev_win_rate: float

    # Degradation
    sharpe_degradation: float  # (dev - holdout) / dev
    win_rate_degradation: float

    # Deflated Sharpe
    deflated_sharpe: float
    deflated_sharpe_threshold: float
    deflated_sharpe_pass: bool

    # Overall
    passed: bool
    warnings: list[str]


class HoldoutValidator:
    """
    Final holdout validation — data never touched during development.

    Usage:
        validator = HoldoutValidator(n_strategies=13, n_trials=100)
        result = validator.validate(
            dev_results=dev_metrics,
            holdout_results=holdout_metrics,
        )

        if not result.passed:
            print("Strategy NOT validated!")
            print(f"Deflated Sharpe: {result.deflated_sharpe:.2f} < {result.deflated_sharpe_threshold:.2f}")
    """

    def __init__(self, n_strategies: int = 13, n_trials: int = 100):
        """
        Args:
            n_strategies: Number of strategies tested (for multiple testing correction)
            n_trials: Number of parameter combinations tested
        """
        self.n_strategies = n_strategies
        self.n_trials = n_trials
        self.total_tests = n_strategies * n_trials

    def validate(
        self,
        dev_results: dict[str, float],
        holdout_results: dict[str, float],
        max_acceptable_degradation: float = 0.5,
    ) -> HoldoutResult:
        """
        Validate strategy on holdout data.

        Args:
            dev_results: Performance on development data
            holdout_results: Performance on holdout data (never seen)
            max_acceptable_degradation: Max allowed performance drop (0.5 = 50%)
        """
        warnings = []

        # Extract metrics
        dev_sharpe = dev_results.get("sharpe_ratio", 0)
        dev_win_rate = dev_results.get("win_rate", 0)
        dev_pf = dev_results.get("profit_factor", 0)

        holdout_sharpe = holdout_results.get("sharpe_ratio", 0)
        holdout_win_rate = holdout_results.get("win_rate", 0)
        holdout_pf = holdout_results.get("profit_factor", 0)
        holdout_dd = holdout_results.get("max_drawdown_pct", 0)
        holdout_pnl = holdout_results.get("total_pnl", 0)
        holdout_trades = holdout_results.get("total_trades", 0)

        # Calculate degradation
        sharpe_deg = (dev_sharpe - holdout_sharpe) / dev_sharpe if dev_sharpe > 0 else 1.0
        wr_deg = (dev_win_rate - holdout_win_rate) / dev_win_rate if dev_win_rate > 0 else 1.0

        # Deflated Sharpe Ratio
        deflated_sharpe, threshold = self._deflated_sharpe(holdout_sharpe, holdout_trades)

        # Warnings
        if sharpe_deg > max_acceptable_degradation:
            warnings.append(f"Sharpe degradation {sharpe_deg:.1%} > {max_acceptable_degradation:.1%}")
        if wr_deg > max_acceptable_degradation:
            warnings.append(f"Win rate degradation {wr_deg:.1%} > {max_acceptable_degradation:.1%}")
        if holdout_trades < 30:
            warnings.append(f"Holdout trades {holdout_trades} < 30 (low statistical significance)")
        if holdout_dd > 15:
            warnings.append(f"Holdout max DD {holdout_dd:.1f}% > 15%")

        # Pass criteria
        passed = (
            deflated_sharpe > threshold
            and sharpe_deg < max_acceptable_degradation
            and holdout_trades >= 30
            and holdout_pf > 1.0
        )

        return HoldoutResult(
            holdout_sharpe=holdout_sharpe,
            holdout_win_rate=holdout_win_rate,
            holdout_profit_factor=holdout_pf,
            holdout_max_drawdown_pct=holdout_dd,
            holdout_total_pnl=holdout_pnl,
            holdout_trades=holdout_trades,
            dev_sharpe=dev_sharpe,
            dev_win_rate=dev_win_rate,
            sharpe_degradation=sharpe_deg,
            win_rate_degradation=wr_deg,
            deflated_sharpe=deflated_sharpe,
            deflated_sharpe_threshold=threshold,
            deflated_sharpe_pass=deflated_sharpe > threshold,
            passed=passed,
            warnings=warnings,
        )

    def _deflated_sharpe(
        self,
        observed_sharpe: float,
        n_trades: int,
        annualization: float = None,
    ) -> tuple:
        """
        Deflated Sharpe Ratio (Bailey & López de Prado, 2014)

        Adjusts Sharpe for multiple testing. More tests = higher threshold.

        ASSUMPTION: observed_sharpe is already annualized.
        n_trades = number of trades (used as proxy for observations)

        NOTE: This is an approximation. For rigorous use, pass n_observations
        (number of return periods) instead of n_trades.

        Formula:
            PSR(SR*) = Φ((SR* - E[max_SR]) / std[max_SR])

        Where:
            E[max_SR] ≈ sqrt(2 * ln(N)) * annualization / sqrt(T)
            std[max_SR] ≈ annualization / sqrt(T)
        """
        if n_trades < 5:
            return 0.0, 1.0

        if annualization is None:
            annualization = math.sqrt(252)

        n = max(self.total_tests, 1)
        T = n_trades

        # Expected max Sharpe under null hypothesis
        expected_max = math.sqrt(2 * math.log(n)) * annualization / math.sqrt(T)

        # Std of max Sharpe under null (simplified)
        std_max = annualization / math.sqrt(T)

        # Deflated Sharpe (z-score)
        if std_max == 0:
            deflated = 0.0
        else:
            deflated = (observed_sharpe - expected_max) / std_max

        # Threshold: need deflated > 1.96 for 95% confidence
        threshold = 1.96

        return round(deflated, 4), round(threshold, 4)
