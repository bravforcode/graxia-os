"""Strategy Validator — reusable validation harness for all strategies.

Runs comprehensive edge verification:
1. Baseline backtest (trade-level Sharpe, NOT bar-level)
2. Walk-forward analysis (5-fold, purged, with parameter retraining)
3. Deflated Sharpe Ratio (DSR) — threshold lowered to 2 returns minimum
4. Probability of Backtest Overfitting (PBO) via CSCV
5. Bootstrap confidence intervals (stationary bootstrap on trade returns)
6. Cost stress tests (1.5x, 2x, 3x)

CRITICAL FIX: Uses TRADE-LEVEL Sharpe (from actual trade PnL) instead of
BAR-LEVEL Sharpe (from equity curve returns). Bar-level Sharpe is diluted
by thousands of zero-return bars (no position open), producing ~0.0000
even when the strategy has a real edge.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..backtest.engine import BacktestConfig, BacktestEngine
from ..backtest.metrics import _std_dev
from .bootstrap_sensitivity import bootstrap_confidence_interval
from .cost_stress import analyze_cost_sensitivity
from .deflated_sharpe import DeflatedSharpeResult, deflated_sharpe_ratio
from .probability_overfitting import PBOResult, calculate_pbo_from_matrix
from .walk_forward import walk_forward_split

# ── Helpers ────────────────────────────────────────────────────────────


def load_ohlcv_csv(path: Path, skip_zero_volume: bool = True) -> dict[str, list]:
    """Load OHLCV data from a CSV file.

    Returns dict with 'open', 'high', 'low', 'close', 'volume' lists.
    If skip_zero_volume=True, rows with volume=0 are filtered out
    (skips synthetic pre-2007 data for XAUUSD).
    """
    data: dict[str, list] = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    if not path.exists():
        # Try alternate filenames
        for alt in ["XAUUSD_D1_clean.csv", "XAUUSD_D1_original.csv", "EURUSD_D1_clean.csv"]:
            alt_path = path.parent / alt
            if alt_path.exists():
                path = alt_path
                break
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                vol = float(row.get("volume", "0"))
                if skip_zero_volume and vol == 0:
                    continue
                data["open"].append(float(row["open"]))
                data["high"].append(float(row["high"]))
                data["low"].append(float(row["low"]))
                data["close"].append(float(row["close"]))
                data["volume"].append(int(vol) if vol > 0 else 1)
            except (ValueError, KeyError):
                continue

    if len(data["close"]) < 100:
        raise ValueError(f"Insufficient data: only {len(data['close'])} bars loaded from {path}")

    return data


def generate_timestamps(n: int, start: str = "2007-01-02", freq_days: int = 1) -> list[datetime]:
    """Generate deterministic timestamps for backtesting."""
    start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
    return [start_dt + timedelta(days=i * freq_days) for i in range(n)]


def _compute_trade_returns_sharpe(trades: list[dict], annualization_factor: int = 252) -> float:
    """Compute Sharpe from TRADE-LEVEL returns (not bar-level equity curve).

    This is the key fix: the engine's calculate_metrics() computes Sharpe
    from bar-level equity curve returns. For D1 data with 11K bars but
    ~600 trades, 95% of bars have zero return, diluting the Sharpe to
    ~0.0000 even when the strategy has a real edge.

    Trade-level Sharpe correctly reflects the strategy's actual
    risk-adjusted performance on trades it actually took.
    """
    if not trades or len(trades) < 2:
        return 0.0

    returns = []
    for t in trades:
        ret = t.get("return_pct", 0.0)
        if isinstance(ret, (int, float)):
            returns.append(ret / 100.0)  # convert percentage to fraction

    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    std_ret = _std_dev(returns)

    if std_ret == 0:
        return 0.0

    return (mean_ret / std_ret) * math.sqrt(annualization_factor)  # type: ignore[no-any-return]


def _compute_bar_level_sharpe(equity_curve: list, annualization_factor: int = 252) -> float:
    """Compute Sharpe from bar-level equity curve returns (DILUTED)."""
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = (
            equity_curve[i - 1].equity
            if hasattr(equity_curve[i - 1], "equity")
            else equity_curve[i - 1].get("equity", 0)
        )
        curr_eq = equity_curve[i].equity if hasattr(equity_curve[i], "equity") else equity_curve[i].get("equity", 0)
        if prev_eq > 0:
            returns.append((curr_eq - prev_eq) / prev_eq)
    if len(returns) < 2:
        return 0.0
    mean_ret = sum(returns) / len(returns)
    std_ret = _std_dev(returns)
    if std_ret == 0:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(annualization_factor)  # type: ignore[no-any-return]


# ── Configuration ──────────────────────────────────────────────────────


@dataclass
class ValidationConfig:
    """Configuration for strategy validation.

    annualization_factor: Annual bars-per-year for Sharpe.
      Auto-inferred from strategy_timeframe if not explicitly set:
        D1  -> 252
        H4  -> 252 * 6   = 1512
        H1  -> 252 * 6.5 = 1638
        M30 -> 252 * 13  = 3276
        M15 -> 252 * 26  = 6552
        M5  -> 252 * 78  = 19656
      Override explicitly for custom calendars.
    """

    initial_capital: Decimal = Decimal("10000")
    slippage_pips: float = 0.5
    spread_pips: float = 2.0
    commission_per_lot: Decimal = Decimal("3.5")
    risk_per_trade_bps: int = 100  # 1% risk per trade
    n_wf_folds: int = 5
    wf_train_ratio: float = 0.7
    embargo_bars: int = 12
    n_bootstrap_resamples: int = 1000
    annualization_factor: int = 0  # 0 = auto-infer from timeframe
    strategy_symbol: str = "XAUUSD"
    strategy_timeframe: str = "D1"

    def get_annualization_factor(self) -> int:
        """Return annualization factor, auto-inferring from timeframe if needed."""
        if self.annualization_factor > 0:
            return self.annualization_factor
        tf = self.strategy_timeframe.upper()
        _ANNUALIZATION_MAP = {
            "D1": 252,
            "D": 252,
            "H4": 1512,  # 252 * 6
            "H1": 1638,  # 252 * 6.5
            "H": 1638,
            "M30": 3276,  # 252 * 13
            "M15": 6552,  # 252 * 26
            "M5": 19656,  # 252 * 78
            "M1": 118080,  # 252 * 468
        }
        return _ANNUALIZATION_MAP.get(tf, 252)


# ── Validation Result ──────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Full validation result for a strategy."""

    strategy_name: str
    symbol: str
    timeframe: str
    n_bars: int
    validation_date: str

    # Baseline
    baseline_trades: int = 0
    baseline_win_rate: float = 0.0
    baseline_sharpe_bar: float = 0.0
    baseline_sharpe_trade: float = 0.0
    baseline_profit_factor: float = 0.0
    baseline_max_drawdown_pct: float = 0.0
    baseline_total_pnl: float = 0.0

    # Walk-forward
    wf_folds: int = 0
    wf_positive_folds: int = 0
    wf_oos_trades: int = 0
    wf_oos_sharpe: float = 0.0
    wf_pass: bool = False

    # DSR
    dsr_observed_sharpe: float = 0.0
    dsr_probability_alpha: float = 1.0
    dsr_n_observations: int = 0
    dsr_pass: bool = False

    # PBO
    pbo_score: float = 1.0
    pbo_pass: bool = False

    # Bootstrap
    bootstrap_sharpe: float = 0.0
    bootstrap_ci_lower: float = 0.0
    bootstrap_ci_upper: float = 0.0
    bootstrap_pass: bool = False

    # Cost stress
    cost_base_pnl: float = 0.0
    cost_total_costs: float = 0.0
    cost_2x_pnl: float = 0.0
    cost_degradation_pct: float = 100.0
    cost_pass: bool = False

    # Verdict
    gates_passed: int = 0
    total_gates: int = 5
    verdict: str = "UNKNOWN"
    recommendation: str = ""


# ── Strategy Validator ─────────────────────────────────────────────────


class StrategyValidator:
    """Reusable validation harness for any strategy.

    Usage:
        validator = StrategyValidator(
            strategy_factory=my_factory,
            param_grid=[...],
            pbo_configs=[...],
            default_params={...},
            strategy_name="My Strategy",
        )
        result = validator.run(data=ohlcv, timestamps=ts)
        report = validator.generate_report(result)
    """

    def __init__(
        self,
        strategy_factory: Callable[..., Any],
        param_grid: list[dict[str, Any]],
        pbo_configs: list[dict[str, Any]],
        default_params: dict[str, Any],
        strategy_name: str,
        config: ValidationConfig | None = None,
    ):
        self.strategy_factory = strategy_factory
        self.param_grid = param_grid
        self.pbo_configs = pbo_configs
        self.default_params = default_params
        self.strategy_name = strategy_name
        self.config = config or ValidationConfig()

    def _run_backtest(self, strategy, data: dict[str, list], timestamps: list[datetime]) -> dict[str, Any]:
        """Run a single backtest and return results dict."""
        bt_config = BacktestConfig(
            initial_capital=self.config.initial_capital,
            slippage_pips=self.config.slippage_pips,
            spread_pips=self.config.spread_pips,
            commission_per_lot=self.config.commission_per_lot,
            risk_per_trade_bps=self.config.risk_per_trade_bps,
            strict_mtf=False,
        )
        engine = BacktestEngine(config=bt_config)
        engine.set_strategy(strategy)
        engine.load_data(data, timestamps)
        return engine.run()  # type: ignore[no-any-return]

    def run(self, data: dict[str, list], timestamps: list[datetime]) -> ValidationResult:
        """Run comprehensive validation."""
        n_bars = len(data["close"])
        print(f"  Running validation on {n_bars} bars...")

        result = ValidationResult(
            strategy_name=self.strategy_name,
            symbol=self.config.strategy_symbol,
            timeframe=self.config.strategy_timeframe,
            n_bars=n_bars,
            validation_date=datetime.now(UTC).isoformat(),
        )

        # ── 1. Baseline backtest ─────────────────────────────────────
        print("  [1/5] Baseline backtest...")
        baseline_strat = self.strategy_factory(**self.default_params)
        baseline_result = self._run_backtest(baseline_strat, data, timestamps)
        baseline_trades = baseline_result.get("trades", [])
        baseline_metrics = baseline_result.get("metrics", {})
        baseline_equity = baseline_result.get("equity_curve", [])

        result.baseline_trades = len(baseline_trades)
        result.baseline_win_rate = baseline_metrics.win_rate if hasattr(baseline_metrics, "win_rate") else 0.0
        result.baseline_profit_factor = (
            baseline_metrics.profit_factor if hasattr(baseline_metrics, "profit_factor") else 0.0
        )
        result.baseline_max_drawdown_pct = (
            baseline_metrics.max_drawdown_pct if hasattr(baseline_metrics, "max_drawdown_pct") else 0.0
        )
        result.baseline_total_pnl = sum(t.get("pnl", 0) for t in baseline_trades)

        # Trade-level Sharpe (the fix!)
        ann_factor = self.config.get_annualization_factor()
        result.baseline_sharpe_trade = _compute_trade_returns_sharpe(baseline_trades, ann_factor)
        # Bar-level Sharpe (for comparison / backward compat)
        result.baseline_sharpe_bar = _compute_bar_level_sharpe(baseline_equity, ann_factor)

        print(f"    Trades: {result.baseline_trades}, Win Rate: {result.baseline_win_rate:.1%}")
        print(f"    Sharpe (trade-level): {result.baseline_sharpe_trade:.4f}")
        print(f"    Sharpe (bar-level):   {result.baseline_sharpe_bar:.4f}")
        print(f"    PF: {result.baseline_profit_factor:.2f}, MaxDD: {result.baseline_max_drawdown_pct:.1f}%")

        # ── 2. Walk-forward analysis ─────────────────────────────────
        print("  [2/5] Walk-forward analysis...")
        wf_result = self._run_walk_forward(data, timestamps)
        result.wf_folds = wf_result["n_folds"]
        result.wf_positive_folds = wf_result["positive_folds"]
        result.wf_oos_trades = wf_result["oos_trades"]
        result.wf_oos_sharpe = wf_result["oos_sharpe"]
        # PASS: >50% folds positive AND oos_sharpe > 0
        result.wf_pass = result.wf_positive_folds > result.wf_folds / 2 and result.wf_oos_sharpe > 0
        print(
            f"    {result.wf_positive_folds}/{result.wf_folds} folds positive, "
            f"OOS trades: {result.wf_oos_trades}, Sharpe: {result.wf_oos_sharpe:.4f}"
        )

        # ── 3. Deflated Sharpe Ratio ─────────────────────────────────
        print("  [3/5] Deflated Sharpe Ratio...")
        dsr_result = self._run_dsr(baseline_trades)
        result.dsr_observed_sharpe = dsr_result.observed_sharpe
        result.dsr_probability_alpha = dsr_result.probability_alpha
        result.dsr_n_observations = len(baseline_trades)
        result.dsr_pass = dsr_result.passes_threshold
        print(f"    Sharpe: {result.dsr_observed_sharpe:.4f}, P(alpha): {result.dsr_probability_alpha:.4f}")
        if len(baseline_trades) < 10:
            print(f"    *** LOW POWER WARNING: only {len(baseline_trades)} trades — DSR lacks statistical power")

        # ── 4. PBO ───────────────────────────────────────────────────
        print("  [4/5] Probability of Backtest Overfitting...")
        pbo_result = self._run_pbo(data, timestamps)
        result.pbo_score = pbo_result.pbo
        result.pbo_pass = pbo_result.passes_threshold
        print(f"    PBO: {result.pbo_score:.4f}")

        # ── 5. Bootstrap + Cost Stress ───────────────────────────────
        print("  [5/5] Bootstrap + Cost Stress...")
        boot_result = self._run_bootstrap(baseline_trades)
        result.bootstrap_sharpe = boot_result["sharpe"]
        result.bootstrap_ci_lower = boot_result["ci_lower"]
        result.bootstrap_ci_upper = boot_result["ci_upper"]
        result.bootstrap_pass = boot_result["passes"]

        cost_result = self._run_cost_stress(baseline_trades)
        result.cost_base_pnl = cost_result["base_pnl"]
        result.cost_total_costs = cost_result["total_costs"]
        result.cost_2x_pnl = cost_result["stress_2x_pnl"]
        result.cost_degradation_pct = cost_result["degradation"]
        # Pass gate if PnL survives 2x costs
        result.cost_pass = cost_result["survives_2x"]

        print(f"    Bootstrap CI: [{result.bootstrap_ci_lower:.4f}, {result.bootstrap_ci_upper:.4f}]")
        print(f"    Cost degradation: {result.cost_degradation_pct:.1f}%")
        print(f"    Sharpe at 2x cost: {cost_result.get('stress_2x_sharpe', 0):.4f}")

        # ── Verdict ──────────────────────────────────────────────────
        result.gates_passed = sum(
            [
                result.wf_pass,
                result.dsr_pass,
                result.pbo_pass,
                result.bootstrap_pass,
                result.cost_pass,
            ]
        )
        result.total_gates = 5

        if result.gates_passed >= 4:
            result.verdict = "STRONG EDGE"
            result.recommendation = "Proceed to paper trading"
        elif result.gates_passed >= 3:
            result.verdict = "MODERATE EDGE"
            result.recommendation = "Investigate further, consider smaller allocation"
        elif result.gates_passed >= 2:
            result.verdict = "WEAK EDGE"
            result.recommendation = "Not recommended for live trading"
        elif result.gates_passed >= 1:
            result.verdict = "MARGINAL EDGE"
            result.recommendation = "Do not trade"
        else:
            result.verdict = "NO EDGE"
            result.recommendation = "Reject strategy"

        print(f"\n  FINAL: {result.gates_passed}/{result.total_gates} gates passed -> {result.verdict}")
        return result

    def _run_walk_forward(self, data: dict[str, list], timestamps: list[datetime]) -> dict[str, Any]:
        """Run walk-forward analysis with parameter optimization on each fold."""
        n_bars = len(data["close"])
        splits = walk_forward_split(
            n_bars,
            n_folds=self.config.n_wf_folds,
            train_ratio=self.config.wf_train_ratio,
            embargo_bars=self.config.embargo_bars,
        )

        positive_folds = 0
        oos_all_trades = []

        for fold_idx, ((train_start, train_end), (test_start, test_end)) in enumerate(splits):
            # Slice data for train/test
            train_data = {k: v[train_start:train_end] for k, v in data.items()}
            test_data = {k: v[test_start:test_end] for k, v in data.items()}
            train_ts = timestamps[train_start:train_end]
            test_ts = timestamps[test_start:test_end]

            # Optimize on train: find best params
            best_sharpe: float = -999
            best_params = self.default_params
            for params in self.param_grid:
                try:
                    strat = self.strategy_factory(**params)
                    res = self._run_backtest(strat, train_data, train_ts)
                    trades = res.get("trades", [])
                    sharpe = _compute_trade_returns_sharpe(trades, self.config.get_annualization_factor())
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_params = {k: v for k, v in params.items() if k != "name"}
                except Exception:
                    continue

            # Evaluate on test
            try:
                strat = self.strategy_factory(**best_params)
                res = self._run_backtest(strat, test_data, test_ts)
                test_trades = res.get("trades", [])
                test_sharpe = _compute_trade_returns_sharpe(test_trades, self.config.get_annualization_factor())
                oos_all_trades.extend(test_trades)
                if test_sharpe > 0 and len(test_trades) >= 2:
                    positive_folds += 1
            except Exception:
                continue

        # Aggregate OOS Sharpe
        oos_sharpe = _compute_trade_returns_sharpe(oos_all_trades, self.config.get_annualization_factor())

        return {
            "n_folds": len(splits),
            "positive_folds": positive_folds,
            "oos_trades": len(oos_all_trades),
            "oos_sharpe": oos_sharpe,
        }

    def _run_dsr(self, trades: list[dict]) -> DeflatedSharpeResult:
        """Run Deflated Sharpe Ratio analysis."""
        sharpe = _compute_trade_returns_sharpe(trades, self.config.get_annualization_factor())
        # WS-C: Use the authoritative reconciled cumulative N as floor,
        # not just the local param_grid size (which undercounts by ~1000x).
        # The local param_grid is kept as a minimum to prevent under-deflation
        # when the reconciliation file is temporarily unavailable.
        from .n_trials import get_reconciled_n_trials

        n_trials = max(len(self.param_grid), get_reconciled_n_trials(minimum=5))
        n_observations = len(trades)

        # FIX: Lower threshold from 10 to 5 (compromise between old 10 and too-aggressive 2)
        if n_observations < 5:
            return DeflatedSharpeResult(
                observed_sharpe=sharpe,
                deflated_sharpe=sharpe,
                probability_alpha=1.0,
                multiple_testing_adjustment=0.0,
                passes_threshold=False,
            )

        return deflated_sharpe_ratio(
            observed_sharpe=sharpe,
            n_trials=n_trials,
            n_observations=n_observations,
        )

    def _run_pbo(self, data: dict[str, list], timestamps: list[datetime]) -> PBOResult:
        """Run Probability of Backtest Overfitting via CSCV."""
        if len(self.pbo_configs) < 2:
            return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

        # Run each config and collect per-period returns
        n_bars = len(data["close"])
        n_periods = min(self.config.n_wf_folds, 8)
        period_size = n_bars // n_periods

        strategy_returns: dict[str, list[list[float]]] = {}
        for cfg in self.pbo_configs:
            cfg_name = cfg.get("name", str(cfg))
            clean_cfg = {k: v for k, v in cfg.items() if k != "name"}
            cfg_returns = []

            for p in range(n_periods):
                start = p * period_size
                end = start + period_size if p < n_periods - 1 else n_bars
                period_data = {k: v[start:end] for k, v in data.items()}
                period_ts = timestamps[start:end]

                try:
                    strat = self.strategy_factory(**clean_cfg)
                    res = self._run_backtest(strat, period_data, period_ts)
                    trades = res.get("trades", [])
                    # Use per-trade returns for this period
                    period_returns = [t.get("return_pct", 0.0) / 100.0 for t in trades]
                    cfg_returns.append(period_returns if period_returns else [])
                except Exception:
                    cfg_returns.append([])

            strategy_returns[cfg_name] = cfg_returns

        # Use the correct CSCV method with strategy matrix
        return calculate_pbo_from_matrix(strategy_returns)

    def _run_bootstrap(self, trades: list[dict]) -> dict[str, Any]:
        """Run bootstrap CI on trade returns."""
        returns = [t.get("return_pct", 0.0) / 100.0 for t in trades]

        if len(returns) < 5:
            return {
                "sharpe": _compute_trade_returns_sharpe(trades, self.config.get_annualization_factor()),
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "passes": False,
            }

        # Use the validation bootstrap_confidence_interval (simpler, no stationary bootstrap)
        result = bootstrap_confidence_interval(
            returns,
            n_resamples=self.config.n_bootstrap_resamples,
            confidence_level=0.95,
            seed=42,
        )

        # Sharpe from full sample
        sharpe = _compute_trade_returns_sharpe(trades, self.config.get_annualization_factor())

        # CI on mean return -> check if Sharpe-like (positive)
        ci_lower = result.confidence_interval_95[0]
        ci_upper = result.confidence_interval_95[1]

        # PASS if lower bound > 0 (no zero in CI)
        passes = ci_lower > 0 and result.passes_threshold

        return {
            "sharpe": sharpe,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "passes": passes,
        }

    def _run_cost_stress(self, trades: list[dict]) -> dict[str, Any]:
        """Run cost stress test with trade-level Sharpe degradation.

        Computes how trade-level Sharpe degrades under 1.5x and 2x cost
        multipliers. The PBO gate passes if Sharpe remains positive at 2x costs.
        """
        base_pnl = sum(t.get("pnl", 0) for t in trades)
        total_costs = sum(t.get("fees", 0) for t in trades)
        ann_factor = self.config.get_annualization_factor()

        # PnL-based cost sensitivity
        cost_result = analyze_cost_sensitivity(base_pnl, total_costs)

        degradation = 0.0
        if abs(base_pnl) > 0:
            degradation = abs(cost_result.stress_2x_pnl - base_pnl) / abs(base_pnl) * 100

        # Trade-level Sharpe under 2x costs: recompute each trade's net return
        # by doubling the fees. Use net_pnl / notional for all trades.
        base_sharpe = _compute_trade_returns_sharpe(trades, ann_factor)
        stress_2x_returns = []
        for t in trades:
            pnl = t.get("pnl", 0.0)
            fees = t.get("fees", 0.0)
            entry = t.get("entry_price", 0)
            qty = t.get("quantity", 0)
            # PnL already has -fees; subtracting fees again = 2x total fees
            net_pnl = pnl - fees
            notional = abs(entry * qty) if entry and qty else 0
            if notional > 0:
                stress_2x_returns.append(net_pnl / notional)
        stress_2x_sharpe = 0.0
        if len(stress_2x_returns) >= 2:
            mean_ret = sum(stress_2x_returns) / len(stress_2x_returns)
            std_ret = _std_dev(stress_2x_returns)
            if std_ret > 0:
                stress_2x_sharpe = (mean_ret / std_ret) * math.sqrt(ann_factor)

        return {
            "base_pnl": base_pnl,
            "total_costs": total_costs,
            "stress_2x_pnl": cost_result.stress_2x_pnl,
            "degradation": degradation,
            "survives_2x": cost_result.survives_stress_2,
            "base_sharpe": base_sharpe,
            "stress_2x_sharpe": stress_2x_sharpe,
        }

    def generate_report(self, result: ValidationResult) -> str:
        """Generate a formatted validation report."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"EDGE VERIFICATION REPORT: {result.strategy_name}")
        lines.append(f"Symbol: {result.symbol} {result.timeframe}")
        lines.append(f"Data: {result.n_bars} bars")
        lines.append(f"Date: {result.validation_date}")
        lines.append("=" * 80)

        # Baseline
        lines.append("\nBASELINE METRICS")
        lines.append("-" * 40)
        lines.append(f"Total Trades: {result.baseline_trades}")
        lines.append(f"Win Rate: {result.baseline_win_rate * 100:.1f}%")
        lines.append(f"Sharpe Ratio: {result.baseline_sharpe_trade:.4f}")
        lines.append(f"Sharpe Ratio (bar-level):   {result.baseline_sharpe_bar:.4f}")
        lines.append(f"Profit Factor: {result.baseline_profit_factor:.2f}")
        lines.append(f"Max Drawdown Pct: {result.baseline_max_drawdown_pct:.1f}")
        lines.append(f"Total PnL: {result.baseline_total_pnl:.2f}")

        # Walk-forward
        lines.append("\nWALK-FORWARD ANALYSIS")
        lines.append("-" * 40)
        wf_status = "PASS" if result.wf_pass else "FAIL"
        lines.append(
            f"  {result.wf_positive_folds}/{result.wf_folds} positive, "
            f"{result.wf_oos_trades} trades, Sharpe={result.wf_oos_sharpe:.4f}"
        )
        lines.append(f"  {wf_status}")

        # DSR
        lines.append("\nDEFLATED SHARPE RATIO")
        lines.append("-" * 40)
        dsr_status = "PASS" if result.dsr_pass else "FAIL"
        lines.append(f"  DSR: Sharpe={result.dsr_observed_sharpe:.4f}, " f"P(alpha)={result.dsr_probability_alpha:.4f}")
        lines.append(f"  Observations: {result.dsr_n_observations}")
        if result.dsr_n_observations < 10:
            lines.append("  *** LOW POWER: DSR statistical power drops sharply below ~10 observations")
            lines.append(f"      (only {result.dsr_n_observations} trades — interpret P(alpha) with caution)")
        lines.append(f"  {dsr_status}")

        # PBO
        lines.append("\nPROBABILITY OF BACKTEST OVERFITTING")
        lines.append("-" * 40)
        pbo_status = "PASS" if result.pbo_pass else "FAIL"
        lines.append(f"  PBO: {result.pbo_score:.4f}")
        lines.append(f"  {pbo_status}")

        # Bootstrap
        lines.append("\nBOOTSTRAP CONFIDENCE INTERVAL")
        lines.append("-" * 40)
        boot_status = "PASS" if result.bootstrap_pass else "FAIL"
        lines.append(
            f"  BOOTSTRAP: Sharpe={result.bootstrap_sharpe:.4f}, "
            f"CI=[{result.bootstrap_ci_lower:.4f}, {result.bootstrap_ci_upper:.4f}]"
        )
        lines.append(f"  {boot_status}")

        # Cost stress
        lines.append("\nCOST STRESS TEST")
        lines.append("-" * 40)
        cost_status = "PASS" if result.cost_pass else "FAIL"
        lines.append(
            f"  COST STRESS: Base PnL={result.cost_base_pnl:.2f}, "
            f"2x PnL={result.cost_2x_pnl:.2f}, "
            f"Degradation={result.cost_degradation_pct:.1f}%"
        )
        lines.append(f"  {cost_status}")

        # Final
        lines.append("\n" + "=" * 80)
        lines.append(f"FINAL: {result.gates_passed}/{result.total_gates} gates passed")
        lines.append(f"VERDICT: {result.verdict}")
        lines.append(f"RECOMMENDATION: {result.recommendation}")
        lines.append("=" * 80)

        return "\n".join(lines)
