"""Automated research pipeline — zero-human-intervention strategy validation.

Chains together:
  1. Parameter sweep (grid search with auto-trial tracking)
  2. Walk-forward validation (IS/OOS consistency)
  3. Full backtest with best params (metrics + returns)
  4. Overfitting detection (DSR, PBO, bootstrap, cost stress, param stability, MinBTL)
  5. Go/no-go decision

Usage:
    pipeline = ResearchPipeline(
        strategy_factory=lambda params: MyStrategy(params),
        data=ohlcv_data,
        timestamps=timestamps,
        param_grid={"ema_fast": [10, 15, 20], "ema_slow": [50, 60, 70]},
        strategy_id="my_strategy_v1",
    )
    result = pipeline.run()
    print(result.decision)  # "PROCEED" | "RETURN_TO_RESEARCH" | "ARCHIVE_NO_EDGE"
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from ..backtest.engine import BacktestConfig, BacktestEngine
from ..backtest.metrics import BacktestMetrics
from ..backtest.walk_forward import WalkForwardAnalyzer, WalkForwardResult
from ..strategies.base import Strategy
from ..validation.overfitting_detector import (
    OverfittingConfig,
    OverfittingDetector,
    OverfittingReport,
)
from ..validation.search_budget import SearchBudgetSummary, SearchBudgetTracker


@dataclass
class SweepResult:
    """Result of a parameter grid sweep."""

    best_params: dict[str, Any]
    best_score: float  # best IS sharpe
    all_results: list[dict[str, Any]] = field(default_factory=list)
    n_trials: int = 0
    budget_summary: SearchBudgetSummary | None = None


@dataclass
class PipelineResult:
    """Full pipeline output — one object tells the whole story."""

    strategy_id: str
    timestamp: str
    # Decision
    decision: str  # "PROCEED" | "RETURN_TO_RESEARCH" | "ARCHIVE_NO_EDGE"
    # Phase outputs
    sweep_result: SweepResult | None = None
    walk_forward_result: WalkForwardResult | None = None
    backtest_result: dict[str, Any] | None = None
    backtest_metrics: BacktestMetrics | None = None
    overfitting_report: OverfittingReport | None = None
    # Human-readable
    summary: str = ""
    errors: list[str] = field(default_factory=list)


class ResearchPipeline:
    """Fully automated strategy research → validation → go/no-go pipeline.

    Args:
        strategy_factory: Callable(params) -> Strategy instance.
            The factory must accept a dict of hyperparameters and return
            a configured Strategy ready for backtesting.
        data: OHLCV dict with 'open', 'high', 'low', 'close', 'volume' lists.
        timestamps: List of datetime for each bar.
        param_grid: Dict mapping parameter names to lists of values.
            All combinations are tested (grid search).
        strategy_id: Unique identifier for this strategy (used in trial tracking).
        config: Optional BacktestConfig override.
        overfit_config: Optional OverfittingConfig override.
        search_budget: Max trials per strategy (default 1000).
        walk_forward_windows: Number of walk-forward windows (default 5).
        enable_sweep: Whether to run the parameter sweep (default True).
            If False, uses default params from the factory.
    """

    def __init__(
        self,
        strategy_factory: Callable[[dict[str, Any]], Strategy],
        data: dict[str, list],
        timestamps: list[datetime],
        param_grid: dict[str, list[Any]] | None = None,
        strategy_id: str = "unknown",
        config: BacktestConfig | None = None,
        overfit_config: OverfittingConfig | None = None,
        search_budget: int = 1000,
        walk_forward_windows: int = 5,
        enable_sweep: bool = True,
    ):
        self.strategy_factory = strategy_factory
        self.data = data
        self.timestamps = timestamps
        self.param_grid = param_grid or {}
        self.strategy_id = strategy_id
        self.config = config or BacktestConfig()
        self.overfit_config = overfit_config or OverfittingConfig()
        self.search_budget = search_budget
        self.walk_forward_windows = walk_forward_windows
        self.enable_sweep = enable_sweep

        # Shared trial tracker
        self._budget_tracker = SearchBudgetTracker(max_trials=search_budget)

    # ── Public API ────────────────────────────────────────────────

    def run(self) -> PipelineResult:
        """Execute the full pipeline and return a go/no-go decision."""
        ts = datetime.now(UTC).isoformat()
        logger.info("pipeline.run: starting strategy_id=%s timestamp=%s", self.strategy_id, ts)
        result = PipelineResult(
            strategy_id=self.strategy_id,
            timestamp=ts,
            decision="ARCHIVE_NO_EDGE",
        )

        # Phase 1: Parameter sweep
        try:
            logger.info("pipeline.run: phase1_sweep grid_size=%d", len(list(itertools.product(*self.param_grid.values()))) if self.param_grid else 0)
            result.sweep_result = self._run_sweep()
            logger.info("pipeline.run: phase1_complete n_trials=%d best_sharpe=%.4f", result.sweep_result.n_trials, result.sweep_result.best_score)
        except Exception as exc:
            logger.error("pipeline.run: phase1_sweep_failed error=%s", exc)
            result.errors.append(f"sweep_failed: {exc}")
            result.sweep_result = SweepResult(best_params={}, best_score=0.0, n_trials=0)

        best_params = result.sweep_result.best_params

        # Phase 2: Walk-forward validation
        try:
            logger.info("pipeline.run: phase2_walk_forward windows=%d", self.walk_forward_windows)
            result.walk_forward_result = self._run_walk_forward(best_params)
            wf = result.walk_forward_result
            logger.info("pipeline.run: phase2_complete oos_consistency=%.2f overfitting_score=%.3f", wf.oos_consistency, wf.overfitting_score)
        except Exception as exc:
            logger.error("pipeline.run: phase2_walk_forward_failed error=%s", exc)
            result.errors.append(f"walk_forward_failed: {exc}")

        # Phase 3: Full backtest with best params
        try:
            logger.info("pipeline.run: phase3_full_backtest best_params=%s", best_params)
            bt_result, bt_metrics = self._run_full_backtest(best_params)
            result.backtest_result = bt_result
            result.backtest_metrics = bt_metrics
            logger.info("pipeline.run: phase3_complete trades=%d sharpe=%.3f max_dd=%.1f%%", bt_metrics.total_trades, bt_metrics.sharpe_ratio, bt_metrics.max_drawdown_pct)
        except Exception as exc:
            logger.error("pipeline.run: phase3_backtest_failed error=%s", exc)
            result.errors.append(f"backtest_failed: {exc}")

        # Phase 4: Overfitting detection
        try:
            logger.info("pipeline.run: phase4_overfitting_detection")
            result.overfitting_report = self._run_overfitting_detection(
                bt_result=result.backtest_result,
                bt_metrics=result.backtest_metrics,
                wf_result=result.walk_forward_result,
                sweep_result=result.sweep_result,
            )
            ovr = result.overfitting_report
            logger.info("pipeline.run: phase4_complete score=%.3f recommendation=%s blockers=%d warnings=%d", ovr.score, ovr.recommendation, len(ovr.blockers), len(ovr.warnings))
        except Exception as exc:
            logger.error("pipeline.run: phase4_overfitting_failed error=%s", exc)
            result.errors.append(f"overfitting_failed: {exc}")

        # Phase 5: Decision
        result.decision = self._make_decision(result)
        result.summary = self._build_summary(result)
        logger.info("pipeline.run: final_decision=%s strategy_id=%s", result.decision, self.strategy_id)

        return result

    # ── Phase 1: Parameter Sweep ──────────────────────────────────

    def _run_sweep(self) -> SweepResult:
        """Grid-search all parameter combinations, record every trial."""
        if not self.enable_sweep or not self.param_grid:
            return SweepResult(best_params={}, best_score=0.0, n_trials=0)

        # Build full parameter combinations
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        combinations = list(itertools.product(*values))

        all_results: list[dict[str, Any]] = []
        best_score = float("-inf")
        best_params: dict[str, Any] = {}

        for combo in combinations:
            params = dict(zip(keys, combo, strict=False))

            try:
                strategy = self.strategy_factory(params)
                metrics = self._quick_backtest(strategy)
                sharpe = metrics.sharpe_ratio

                self._budget_tracker.record_trial(
                    strategy_id=self.strategy_id,
                    params=params,
                    is_sharpe=sharpe,
                )

                trial_result = {"params": params, "sharpe": sharpe, "metrics": metrics}
                all_results.append(trial_result)

                if sharpe > best_score:
                    best_score = sharpe
                    best_params = params

            except Exception as exc:
                all_results.append(
                    {
                        "params": params,
                        "sharpe": 0.0,
                        "error": str(exc),
                    }
                )
                # Still record failed trial for budget tracking
                self._budget_tracker.record_trial(
                    strategy_id=self.strategy_id,
                    params=params,
                    is_sharpe=0.0,
                )

        n_trials = self._budget_tracker.get_trial_count(self.strategy_id)
        budget_summary = self._budget_tracker.summary(self.strategy_id)

        return SweepResult(
            best_params=best_params,
            best_score=best_score,
            all_results=all_results,
            n_trials=n_trials,
            budget_summary=budget_summary,
        )

    def _quick_backtest(self, strategy: Strategy) -> BacktestMetrics:
        """Run a fast backtest for sweep evaluation — returns metrics only."""
        engine = BacktestEngine(config=self.config)
        engine.set_strategy(strategy)
        engine.load_data(self.data, self.timestamps)
        result = engine.run()
        return result["metrics"]

    # ── Phase 2: Walk-Forward ─────────────────────────────────────

    def _run_walk_forward(self, best_params: dict[str, Any]) -> WalkForwardResult:
        """Run walk-forward analysis to validate IS/OOS consistency."""

        def _factory() -> Strategy:
            return self.strategy_factory(best_params)

        analyzer = WalkForwardAnalyzer(
            strategy_factory=_factory,
            config=self.config,
            is_ratio=0.7,
            min_windows=self.walk_forward_windows,
        )

        return analyzer.analyze(
            data=self.data,
            timestamps=self.timestamps,
            n_windows=self.walk_forward_windows,
        )

    # ── Phase 3: Full Backtest ────────────────────────────────────

    def _run_full_backtest(self, best_params: dict[str, Any]) -> tuple[dict[str, Any], BacktestMetrics]:
        """Run the definitive backtest with best parameters."""
        strategy = self.strategy_factory(best_params)
        engine = BacktestEngine(config=self.config)
        engine.set_strategy(strategy)
        engine.load_data(self.data, self.timestamps)
        result = engine.run()
        metrics = result["metrics"]
        return result, metrics

    # ── Phase 4: Overfitting Detection ────────────────────────────

    def _run_overfitting_detection(
        self,
        bt_result: dict[str, Any] | None,
        bt_metrics: BacktestMetrics | None,
        wf_result: WalkForwardResult | None,
        sweep_result: SweepResult | None,
    ) -> OverfittingReport:
        """Run the full overfitting detection pipeline."""
        detector = OverfittingDetector(config=self.overfit_config)

        # Extract bar-level returns from equity curve
        returns = self._extract_returns(bt_result)

        # Cost data from backtest
        cost_pnl, total_costs = self._extract_costs(bt_result)

        # N trials from sweep
        n_trials = sweep_result.n_trials if sweep_result else 1

        # Observations = number of return bars
        n_observations = max(len(returns), 1)

        # Build strategy matrix for proper CSCV (sweep configs × WF windows)
        strategy_matrix = self._build_strategy_matrix(sweep_result, wf_result)

        # Parameter values and PnLs from sweep for stability analysis
        param_values, param_pnls = self._extract_param_stability_data(sweep_result)

        return detector.evaluate(
            strategy_id=self.strategy_id,
            returns=returns,
            n_trials=n_trials,
            n_observations=n_observations,
            oos_returns_per_fold=[],  # deprecated — strategy_matrix used instead
            cost_pnl=cost_pnl,
            total_costs=total_costs,
            param_values=param_values,
            param_pnls=param_pnls,
            data_length=len(self.data.get("close", [])),
            sharpe=bt_metrics.sharpe_ratio if bt_metrics else None,
            strategy_matrix=strategy_matrix,
        )

    # ── Phase 5: Decision ─────────────────────────────────────────

    def _make_decision(self, result: PipelineResult) -> str:
        """Derive go/no-go from overfitting report and walk-forward."""
        # If overfitting detection ran and has a clear verdict, use it
        if result.overfitting_report is not None:
            return result.overfitting_report.recommendation

        # Fallback: check walk-forward consistency
        if result.walk_forward_result is not None:
            wf = result.walk_forward_result
            if wf.oos_consistency >= 0.6 and wf.overfitting_score < 0.4:
                return "PROCEED"
            if wf.oos_consistency < 0.3:
                return "ARCHIVE_NO_EDGE"
            return "RETURN_TO_RESEARCH"

        # If we have a backtest but no validation, be conservative
        if result.backtest_metrics is not None:
            m = result.backtest_metrics
            if m.total_trades >= 30 and m.sharpe_ratio > 1.0 and m.max_drawdown_pct < 20:
                return "RETURN_TO_RESEARCH"  # promising but not validated
            return "ARCHIVE_NO_EDGE"

        return "ARCHIVE_NO_EDGE"

    # ── Summary Builder ───────────────────────────────────────────

    def _build_summary(self, result: PipelineResult) -> str:
        """Build a human-readable summary of the entire pipeline run."""
        lines = [
            f"{'=' * 60}",
            f"RESEARCH PIPELINE — {result.strategy_id}",
            f"Timestamp: {result.timestamp}",
            f"Decision: {result.decision}",
            f"{'=' * 60}",
        ]

        # Sweep summary
        if result.sweep_result is not None and result.sweep_result.n_trials > 0:
            sr = result.sweep_result
            lines.append("")
            lines.append("PHASE 1: Parameter Sweep")
            lines.append(f"  Trials tested: {sr.n_trials}")
            lines.append(f"  Best IS Sharpe: {sr.best_score:.3f}")
            lines.append(f"  Best params: {sr.best_params}")
            if sr.budget_summary:
                lines.append(
                    f"  Budget: {sr.budget_summary.total_trials}/{sr.budget_summary.max_trials} "
                    f"({'within' if sr.budget_summary.within_budget else 'EXCEEDED'} budget)"
                )
        else:
            lines.append("")
            lines.append("PHASE 1: Parameter Sweep — SKIPPED")

        # Walk-forward summary
        if result.walk_forward_result is not None:
            wf = result.walk_forward_result
            lines.append("")
            lines.append("PHASE 2: Walk-Forward Validation")
            lines.append(f"  Windows: {wf.valid_windows}/{wf.total_windows}")
            lines.append(f"  OOS Consistency: {wf.oos_consistency:.1%}")
            lines.append(f"  Avg IS/OOS Ratio: {wf.avg_is_oos_ratio:.3f}")
            lines.append(f"  OOS Sharpe: {wf.oos_sharpe:.3f}")
            lines.append(f"  Overfitting Score: {wf.overfitting_score:.3f}")
        else:
            lines.append("")
            lines.append("PHASE 2: Walk-Forward — SKIPPED or FAILED")

        # Backtest summary
        if result.backtest_metrics is not None:
            m = result.backtest_metrics
            lines.append("")
            lines.append("PHASE 3: Full Backtest")
            lines.append(f"  Total Trades: {m.total_trades}")
            lines.append(f"  Win Rate: {m.win_rate:.1%}")
            lines.append(f"  Total PnL: ${m.total_pnl:,.2f}")
            lines.append(f"  Sharpe Ratio: {m.sharpe_ratio:.3f}")
            lines.append(f"  Sortino Ratio: {m.sortino_ratio:.3f}")
            lines.append(f"  Max Drawdown: {m.max_drawdown_pct:.1f}%")
            lines.append(f"  Profit Factor: {m.profit_factor:.2f}")
            lines.append(f"  Expectancy: ${m.expectancy:,.2f}")
        else:
            lines.append("")
            lines.append("PHASE 3: Full Backtest — FAILED")

        # Overfitting summary
        if result.overfitting_report is not None:
            ovr = result.overfitting_report
            lines.append("")
            lines.append("PHASE 4: Overfitting Detection")
            lines.append(f"  Composite Score: {ovr.score:.3f}")
            lines.append(f"  Passed: {'YES' if ovr.passed else 'NO'}")
            lines.append(f"  Recommendation: {ovr.recommendation}")
            if ovr.blockers:
                lines.append(f"  Blockers ({len(ovr.blockers)}):")
                for b in ovr.blockers:
                    lines.append(f"    - {b}")
            if ovr.warnings:
                lines.append(f"  Warnings ({len(ovr.warnings)}):")
                for w in ovr.warnings:
                    lines.append(f"    - {w}")
        else:
            lines.append("")
            lines.append("PHASE 4: Overfitting Detection — SKIPPED or FAILED")

        # Errors
        if result.errors:
            lines.append("")
            lines.append(f"ERRORS ({len(result.errors)}):")
            for e in result.errors:
                lines.append(f"  - {e}")

        lines.append(f"{'=' * 60}")
        return "\n".join(lines)

    # ── Extraction Helpers ─────────────────────────────────────────

    @staticmethod
    def _extract_returns(bt_result: dict[str, Any] | None) -> list[float]:
        """Extract bar-level returns from the equity curve."""
        if bt_result is None:
            return []

        equity_curve = bt_result.get("equity_curve", [])
        if len(equity_curve) < 2:
            return []

        returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]["equity"]
            curr = equity_curve[i]["equity"]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    @staticmethod
    def _extract_costs(bt_result: dict[str, Any] | None) -> tuple[float, float]:
        """Extract cost_pnl and total_costs from backtest result."""
        if bt_result is None:
            return 0.0, 0.0

        execution = bt_result.get("execution", {})
        total_spread = execution.get("total_spread_cost", 0.0)
        total_slippage = execution.get("total_slippage_cost", 0.0)
        total_costs = total_spread + total_slippage

        trades = bt_result.get("trades", [])
        cost_pnl = sum(t.get("pnl", 0.0) for t in trades)

        return cost_pnl, total_costs

    @staticmethod
    def _extract_oos_returns(
        wf_result: WalkForwardResult | None,
    ) -> list[list[float]]:
        """Extract OOS returns per fold from walk-forward result.

        Returns real per-bar OOS returns from WalkForwardWindow.oos_returns
        (stored by the walk-forward analyzer since the CSCV redesign).
        Falls back to empty list if not available.
        """
        if wf_result is None or not wf_result.windows:
            return []

        oos_returns_per_fold: list[list[float]] = []
        for window in wf_result.windows:
            if window.oos_returns and len(window.oos_returns) > 0:
                oos_returns_per_fold.append(window.oos_returns)
        return oos_returns_per_fold

    @staticmethod
    def _build_strategy_matrix(
        sweep_result: SweepResult | None,
        wf_result: WalkForwardResult | None,
    ) -> dict[str, list[list[float]]] | None:
        """Build strategy matrix for CSCV: sweep configs × WF windows.

        Returns dict mapping config_id -> list of per-window OOS return arrays.
        Each config_id is a stringified parameter combination.
        Returns None if insufficient data.
        """
        if sweep_result is None or not sweep_result.all_results:
            return None
        if wf_result is None or not wf_result.windows:
            return None

        # Get window OOS returns (must have real returns, not synthetic)
        window_returns: list[list[float]] = []
        for w in wf_result.windows:
            if w.oos_returns and len(w.oos_returns) > 0:
                window_returns.append(w.oos_returns)

        if len(window_returns) < 2:
            return None

        n_windows = len(window_returns)

        # Build strategy matrix: for each sweep config, run backtest on each
        # window's OOS period and collect returns.
        # Since we don't have per-config per-window data from the sweep,
        # we approximate: use the sweep's all_results to get config params,
        # and for each config, estimate per-window returns from the config's
        # aggregate metrics scaled by the window's return distribution.
        #
        # This is an approximation — the ideal implementation would re-run
        # each config on each window's OOS data. For now, we use the
        # available data to construct a reasonable proxy.
        strategy_matrix: dict[str, list[list[float]]] = {}

        for trial in sweep_result.all_results:
            params = trial.get("params", {})
            if not params:
                continue
            config_id = str(sorted(params.items()))
            trial_sharpe = trial.get("sharpe", 0.0)

            # For each window, create a proxy return series by scaling the
            # window's actual OOS returns by the config's relative Sharpe.
            # This preserves the correlation structure across windows while
            # scaling by the config's performance level.
            config_returns: list[list[float]] = []
            for wr in window_returns:
                if trial_sharpe != 0:
                    # Scale window returns by config's Sharpe ratio
                    # (approximation: assumes all configs have similar return
                    #  distribution shape but different performance levels)
                    mean_wr = sum(wr) / len(wr) if wr else 0.0
                    if mean_wr != 0:
                        scaled = [r * (trial_sharpe / mean_wr) for r in wr]
                    else:
                        scaled = list(wr)
                else:
                    scaled = list(wr)
                config_returns.append(scaled)

            strategy_matrix[config_id] = config_returns

        return strategy_matrix if len(strategy_matrix) >= 2 else None

    @staticmethod
    def _extract_param_stability_data(
        sweep_result: SweepResult | None,
    ) -> tuple[list[float], list[float]]:
        """Extract parameter values and PnLs for stability analysis.

        Uses the first parameter from the grid and the corresponding
        sharpe scores as a proxy for PnL.
        """
        if sweep_result is None or not sweep_result.all_results:
            return [], []

        # Use the first parameter's values for stability analysis
        first_key: str | None = None
        for trial in sweep_result.all_results:
            params = trial.get("params", {})
            if params and first_key is None:
                first_key = next(iter(params))
                break

        if first_key is None:
            return [], []

        param_values: list[float] = []
        param_pnls: list[float] = []
        for trial in sweep_result.all_results:
            params = trial.get("params", {})
            if first_key in params:
                param_values.append(float(params[first_key]))
                param_pnls.append(float(trial.get("sharpe", 0.0)))

        return param_values, param_pnls
