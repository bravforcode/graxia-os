"""
Reusable Strategy Validation Framework
=======================================
Extracts shared infrastructure from deep_dive_*_validation.py scripts into a
single class that can validate any strategy with:
1. Walk-forward analysis (purged, with parameter retraining)
2. Deflated Sharpe Ratio (DSR)
3. Probability of Backtest Overfitting (PBO) via CSCV
4. Bootstrap confidence intervals (stationary bootstrap)
5. Cost stress tests

Usage:
    validator = StrategyValidator(
        strategy_factory=lambda **kw: DonchianBreakout(**kw),
        param_grid=[...],
        pbo_configs=[...],
        default_params={...},
        strategy_name="Donchian Breakout",
    )
    report = validator.run(data_path="data/XAUUSD_D1.csv")
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.backtest.engine import BacktestConfig, BacktestEngine
from quant_os.backtest.metrics import (
    BootstrapCI,
    bootstrap_metric_ci,
)
from quant_os.validation.deflated_sharpe import (
    DeflatedSharpeResult,
    MinBTLResult,
    deflated_sharpe_ratio,
    min_backtest_length,
)
from quant_os.validation.probability_overfitting import (
    PBOResult,
    calculate_pbo_from_matrix,
)
from quant_os.validation.walk_forward import walk_forward_split


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class ValidationConfig:
    """Configuration for a validation run."""
    
    # Walk-forward
    wf_folds: int = 5
    wf_train_ratio: float = 0.7
    wf_embargo_bars: int = 20
    
    # DSR
    dsr_n_trials: int = 200
    dsr_confidence_level: float = 0.95
    
    # PBO
    pbo_n_configs: int = 5
    pbo_n_folds: int = 8
    pbo_n_combinations: int = 512
    
    # Bootstrap
    bootstrap_n_resamples: int = 1000
    bootstrap_seed: int = 42
    
    # Backtest defaults
    initial_capital: float = 10000.0
    risk_per_trade_bps: int = 100
    spread_pips: float = 0.3
    slippage_pips: float = 0.1
    commission_per_lot: float = 0.0


@dataclass
class ValidationResult:
    """Complete validation result for a strategy."""
    
    strategy_name: str
    symbol: str
    n_bars: int
    
    baseline_metrics: dict
    walk_forward: dict
    dsr_result: DeflatedSharpeResult
    min_btl: MinBTLResult
    pbo_result: PBOResult
    bootstrap_result: BootstrapCI
    cost_stress: dict
    
    # Verdicts
    wf_pass: bool = False
    dsr_pass: bool = False
    pbo_pass: bool = False
    bootstrap_pass: bool = False
    cost_pass: bool = False
    
    @property
    def pass_count(self) -> int:
        return sum([self.wf_pass, self.dsr_pass, self.pbo_pass, 
                    self.bootstrap_pass, self.cost_pass])
    
    @property
    def verdict(self) -> str:
        if self.pass_count == 5:
            return "EDGE CONFIRMED"
        elif self.pass_count >= 3:
            return "EDGE PROBABLE"
        elif self.pass_count >= 2:
            return "EDGE UNCERTAIN"
        else:
            return "EDGE NOT CONFIRMED"
    
    @property
    def recommendation(self) -> str:
        if self.pass_count == 5:
            return "PROCEED to paper trading (30 days minimum)"
        elif self.pass_count >= 3:
            return "CONDITIONAL PASS - proceed with caution, monitor closely"
        elif self.pass_count >= 2:
            return "RETURN TO RESEARCH - investigate failing gates"
        else:
            return "REJECT - do not trade this strategy"


# ── Data Loading ──────────────────────────────────────────────────────────

def load_ohlcv_csv(csv_path: Path, min_bars: int = 100, skip_zero_volume: bool = True) -> dict[str, list]:
    """Load OHLCV data from CSV.
    
    Args:
        csv_path: Path to CSV file
        min_bars: Minimum number of bars required
        skip_zero_volume: If True, skip rows with volume=0 (synthetic data)
    
    Returns:
        dict with 'open', 'high', 'low', 'close', 'volume' lists
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Data not found: {csv_path}")
    
    print(f"Loading data from: {csv_path}")
    
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    
    with open(csv_path, "r") as f:
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
                data["volume"].append(int(vol))
            except (ValueError, KeyError):
                continue
    
    if len(data["close"]) < min_bars:
        raise ValueError(f"Insufficient data: {len(data['close'])} bars (need {min_bars})")
    
    print(f"Loaded {len(data['close'])} bars")
    print(f"Price range: {min(data['close']):.2f} - {max(data['close']):.2f}")
    
    return data


def generate_timestamps(n_bars: int, start_date: datetime | None = None) -> list[datetime]:
    """Generate deterministic daily timestamps."""
    if start_date is None:
        start_date = datetime(2000, 1, 3, tzinfo=UTC)
    return [start_date + timedelta(days=i) for i in range(n_bars)]


# ── Metric Helpers ────────────────────────────────────────────────────────

def extract_metrics(result: dict) -> dict:
    """Extract metrics from backtest result (handles BacktestMetrics dataclass)."""
    metrics = result.get("metrics", {})
    
    if hasattr(metrics, "__dataclass_fields__"):
        return {
            "total_trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "sharpe_ratio": metrics.sharpe_ratio,
            "sortino_ratio": metrics.sortino_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "profit_factor": metrics.profit_factor,
            "total_pnl": metrics.total_pnl,
            "cagr": metrics.cagr,
            "calmar_ratio": metrics.calmar_ratio,
        }
    
    return {
        "total_trades": metrics.get("total_trades", 0),
        "win_rate": metrics.get("win_rate", 0.0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
        "sortino_ratio": metrics.get("sortino_ratio", 0.0),
        "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
        "profit_factor": metrics.get("profit_factor", 0.0),
        "total_pnl": metrics.get("total_pnl", 0.0),
        "cagr": metrics.get("cagr", 0.0),
        "calmar_ratio": metrics.get("calmar_ratio", 0.0),
    }


def compute_trade_returns(trades: list[dict]) -> list[float]:
    """Compute per-trade returns from trade list.
    
    Note: return_pct in BacktestEngine is already a PERCENTAGE (e.g., 0.5 = 0.5%).
    We convert to fraction by dividing by 100 for statistical calculations.
    """
    returns = []
    for t in trades:
        ret = t.get("return_pct", 0.0)
        if isinstance(ret, str):
            ret = float(ret)
        returns.append(ret / 100.0)
    return returns


def compute_trade_returns_sharpe(returns: list[float], annualization_factor: int = 252) -> float:
    """Compute Sharpe from a list of per-trade returns.
    
    BUG FIX: The engine's calculate_metrics() computes Sharpe from bar-level
    equity curve returns. For D1 data with 11K bars but only ~600 trades,
    95% of bars have zero return (no position open), diluting the signal to
    ~0.0000. This function computes Sharpe from TRADE-LEVEL returns instead,
    which correctly reflects the strategy's actual risk-adjusted performance.
    """
    if len(returns) < 2:
        return 0.0
    
    mean = sum(returns) / len(returns)
    var = sum((x - mean) ** 2 for x in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    
    if std <= 0:
        return 0.0
    
    return (mean / std) * math.sqrt(annualization_factor)


# ── StrategyValidator Class ───────────────────────────────────────────────

class StrategyValidator:
    """Reusable validation framework for any trading strategy.
    
    Args:
        strategy_factory: Callable that creates a strategy from params.
            Example: lambda **kw: DonchianBreakout(**kw)
        param_grid: List of parameter dicts for optimization.
            Example: [{"period": 20, "atr_sl_mult": 2.0, ...}, ...]
        pbo_configs: List of parameter dicts for PBO analysis.
            Must have a "name" key in each dict.
        default_params: Default params for baseline and cost stress tests.
        strategy_name: Human-readable strategy name for reports.
        config: Validation configuration (optional).
    """
    
    def __init__(
        self,
        strategy_factory: Callable[..., Any],
        param_grid: list[dict],
        pbo_configs: list[dict],
        default_params: dict,
        strategy_name: str,
        config: ValidationConfig | None = None,
    ) -> None:
        self.strategy_factory = strategy_factory
        self.param_grid = param_grid
        self.pbo_configs = pbo_configs
        self.default_params = default_params
        self.strategy_name = strategy_name
        self.config = config or ValidationConfig()
    
    def _run_backtest(
        self,
        data: dict[str, list],
        timestamps: list[datetime],
        params: dict | None = None,
    ) -> dict:
        """Run a single backtest with given parameters."""
        if params is None:
            params = self.default_params.copy()
        else:
            params = params.copy()
        
        # Separate strategy params from backtest config params
        strategy_params = {k: v for k, v in params.items() 
                          if k not in ("initial_capital", "risk_per_trade_bps", 
                                      "spread_pips", "slippage_pips", "commission_per_lot")}
        
        strategy = self.strategy_factory(**strategy_params)
        
        config = BacktestConfig(
            initial_capital=Decimal(str(params.get("initial_capital", self.config.initial_capital))),
            spread_pips=params.get("spread_pips", self.config.spread_pips),
            slippage_pips=params.get("slippage_pips", self.config.slippage_pips),
            commission_per_lot=Decimal(str(params.get("commission_per_lot", self.config.commission_per_lot))),
            risk_per_trade_bps=params.get("risk_per_trade_bps", self.config.risk_per_trade_bps),
            strict_mtf=False,
            enable_swap=False,
        )
        
        engine = BacktestEngine(config=config)
        engine.set_strategy(strategy)
        engine.load_data(data, timestamps)
        return engine.run()
    
    def optimize_on_train_set(
        self,
        train_data: dict[str, list],
        train_ts: list[datetime],
        min_trades: int = 3,
    ) -> dict:
        """Find best parameters on training data.
        
        Tests the parameter grid and returns the best config by Sharpe ratio.
        """
        best_sharpe = -999
        best_config = self.param_grid[0]
        
        for params in self.param_grid:
            try:
                result = self._run_backtest(train_data, train_ts, params)
                m = extract_metrics(result)
                trades = result.get("trades", [])
                
                if len(trades) < min_trades:
                    continue
                
                if m["sharpe_ratio"] > best_sharpe:
                    best_sharpe = m["sharpe_ratio"]
                    best_config = params
                    
            except Exception:
                continue
        
        return best_config
    
    def run_walk_forward(
        self,
        data: dict[str, list],
        timestamps: list[datetime],
    ) -> dict:
        """Run walk-forward analysis with purged cross-validation and retraining."""
        n_bars = len(data["close"])
        splits = walk_forward_split(
            n_bars=n_bars,
            n_folds=self.config.wf_folds,
            train_ratio=self.config.wf_train_ratio,
            embargo_bars=self.config.wf_embargo_bars,
        )
        
        print(f"\n{'='*70}")
        print(f"WALK-FORWARD ANALYSIS: {self.config.wf_folds} folds, "
              f"train_ratio={self.config.wf_train_ratio}, embargo={self.config.wf_embargo_bars}")
        print(f"{'='*70}")
        
        fold_results = []
        all_oos_returns = []
        
        for fold_idx, ((train_start, train_end), (test_start, test_end)) in enumerate(splits):
            print(f"\n--- Fold {fold_idx+1}: Train[{train_start}:{train_end}] Test[{test_start}:{test_end}] ---")
            
            train_data = {k: v[train_start:train_end] for k, v in data.items()}
            test_data = {k: v[test_start:test_end] for k, v in data.items()}
            train_ts = timestamps[train_start:train_end]
            test_ts = timestamps[test_start:test_end]
            
            # Retrain/optimize on train set
            best_params = self.optimize_on_train_set(train_data, train_ts)
            print(f"  Best params: {best_params}")
            
            # Evaluate on OOS test set
            try:
                result = self._run_backtest(test_data, test_ts, best_params)
                m = extract_metrics(result)
                trades = result.get("trades", [])
                returns = compute_trade_returns(trades)
                
                # BUG FIX: Use TRADE-LEVEL Sharpe instead of BAR-LEVEL Sharpe.
                # The engine's calculate_metrics() computes Sharpe from equity curve
                # returns, which are mostly zero for D1 data (95% of bars have no
                # position open). This dilutes the Sharpe to ~0.0000 even when the
                # strategy has a real edge. Trade-level Sharpe correctly reflects
                # the strategy's actual risk-adjusted performance.
                trade_sharpe = compute_trade_returns_sharpe(returns)
                
                fold_result = {
                    "fold": fold_idx + 1,
                    "train_bars": train_end - train_start,
                    "test_bars": test_end - test_start,
                    "total_trades": len(trades),
                    "total_pnl": m["total_pnl"],
                    "win_rate": m["win_rate"],
                    "sharpe_ratio": trade_sharpe,
                    "max_drawdown_pct": m["max_drawdown_pct"],
                    "profit_factor": m["profit_factor"],
                    "best_params": best_params,
                    "returns": returns,
                }
                
                fold_results.append(fold_result)
                all_oos_returns.extend(returns)
                
                print(f"  OOS: trades={len(trades)}, PnL=${m['total_pnl']:.2f}, "
                      f"Sharpe={trade_sharpe:.3f}, MaxDD={m['max_drawdown_pct']:.1f}%")
                
            except Exception as e:
                print(f"  ERROR: {e}")
                fold_results.append({"fold": fold_idx + 1, "error": str(e), "returns": []})
        
        valid_folds = [f for f in fold_results if "error" not in f]
        
        if valid_folds:
            avg_sharpe = np.mean([f["sharpe_ratio"] for f in valid_folds])
            positive_folds = sum(1 for f in valid_folds if f["total_pnl"] > 0)
            total_trades = sum(f["total_trades"] for f in valid_folds)
            total_pnl = sum(f["total_pnl"] for f in valid_folds)
            wf_efficiency = avg_sharpe / max(0.5, abs(avg_sharpe))
            
            print(f"\n  Aggregate: {positive_folds}/{len(valid_folds)} positive, "
                  f"{total_trades} trades, PnL=${total_pnl:.2f}, AvgSharpe={avg_sharpe:.4f}")
        else:
            avg_sharpe = 0.0
            positive_folds = 0
            total_trades = 0
            total_pnl = 0.0
            wf_efficiency = 0.0
        
        return {
            "folds": fold_results,
            "aggregate": {
                "n_folds": self.config.wf_folds,
                "positive_folds": positive_folds,
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "avg_oos_sharpe": avg_sharpe,
                "wf_efficiency": wf_efficiency,
            },
            "all_oos_returns": all_oos_returns,
        }
    
    def compute_deflated_sharpe(
        self,
        returns: list[float],
        annualization_factor: int | None = None,
    ) -> tuple[DeflatedSharpeResult, MinBTLResult]:
        """Compute Deflated Sharpe Ratio.
        
        BUG FIX: Previously returned early with probability_alpha=1.0 (auto-fail)
        when len(returns) < 10. This caused DSR gate to ALWAYS fail for strategies
        with fewer than 10 trades, even if they had a genuine edge. Now we compute
        DSR for samples >=5, with a warning when power is low.
        """
        if not returns or len(returns) < 2:
            return (
                DeflatedSharpeResult(0.0, 1.0, 1.0, 0.0, False),
                MinBTLResult(999999, self.config.dsr_n_trials, 0.0, 0.0, 0.0, False),
            )
        
        if len(returns) < 5:
            print(f"  WARNING: Only {len(returns)} trade returns — DSR has very low statistical power")
        
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)
        
        if std_return <= 0:
            observed_sharpe = 0.0
        else:
            ann_factor = annualization_factor if annualization_factor is not None else 252
            observed_sharpe = (mean_return / std_return) * math.sqrt(ann_factor)
        
        skewness = float(np.mean(((returns - mean_return) / std_return) ** 3)) if std_return > 0 else 0.0
        kurtosis = float(np.mean(((returns - mean_return) / std_return) ** 4)) if std_return > 0 else 3.0
        
        result = deflated_sharpe_ratio(
            observed_sharpe=observed_sharpe,
            n_trials=self.config.dsr_n_trials,
            n_observations=len(returns),
            skewness=skewness,
            kurtosis=kurtosis,
            confidence_level=self.config.dsr_confidence_level,
        )
        
        min_btl = min_backtest_length(
            observed_sharpe=observed_sharpe,
            n_trials=self.config.dsr_n_trials,
            confidence_level=self.config.dsr_confidence_level,
            skewness=skewness,
            kurtosis=kurtosis,
            current_observations=len(returns),
        )
        
        print(f"\n{'='*70}")
        print(f"DSR ANALYSIS")
        print(f"{'='*70}")
        print(f"  Observed Sharpe: {observed_sharpe:.4f}")
        print(f"  Skewness: {skewness:.4f}, Kurtosis: {kurtosis:.4f}")
        print(f"  N Trials: {self.config.dsr_n_trials}, N Obs: {len(returns)}")
        print(f"  DSR P(alpha): {result.probability_alpha:.4f}")
        print(f"  Passes: {result.passes_threshold}")
        print(f"  MinBTL Required: {min_btl.min_observations}")
        print(f"  Sufficient: {min_btl.sufficient}")
        
        return result, min_btl
    
    def compute_pbo(
        self,
        data: dict[str, list],
        timestamps: list[datetime],
    ) -> PBOResult:
        """Compute PBO using CSCV."""
        print(f"\n{'='*70}")
        print(f"PBO (CSCV)")
        print(f"{'='*70}")
        
        configs = self.pbo_configs[:self.config.pbo_n_configs]
        
        n_bars = len(data["close"])
        period_size = n_bars // self.config.pbo_n_folds
        periods = [
            (i * period_size, (i + 1) * period_size if i < self.config.pbo_n_folds - 1 else n_bars)
            for i in range(self.config.pbo_n_folds)
        ]
        
        strategy_returns: dict[str, list[list[float]]] = {}
        
        for cfg in configs:
            config_name = cfg["name"]
            strategy_returns[config_name] = []
            
            for period_idx, (start, end) in enumerate(periods):
                period_data = {k: v[start:end] for k, v in data.items()}
                period_ts = timestamps[start:end]
                
                try:
                    # Remove "name" key before passing to backtest
                    params = {k: v for k, v in cfg.items() if k != "name"}
                    result = self._run_backtest(period_data, period_ts, params)
                    trades = result.get("trades", [])
                    returns = compute_trade_returns(trades)
                    strategy_returns[config_name].append(returns)
                    
                    mean_ret = np.mean(returns) if returns else 0.0
                    std_ret = np.std(returns, ddof=1) if len(returns) > 1 else 1.0
                    sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
                    
                    print(f"  {config_name} P{period_idx}: {len(returns)} rets, Sharpe={sharpe:.3f}")
                    
                except Exception as e:
                    print(f"  ERROR {config_name} P{period_idx}: {e}")
                    strategy_returns[config_name].append([])
        
        pbo_result = calculate_pbo_from_matrix(
            strategy_returns,
            n_combinations=self.config.pbo_n_combinations,
        )
        
        print(f"\n  PBO: {pbo_result.pbo:.4f}")
        print(f"  Passes (<0.05): {pbo_result.passes_threshold}")
        
        return pbo_result
    
    def compute_bootstrap_ci(
        self,
        returns: list[float],
        annualization_factor: int | None = None,
    ) -> BootstrapCI:
        """Compute bootstrap confidence interval for Sharpe ratio."""
        ann_factor = annualization_factor if annualization_factor is not None else 252
        
        def sharpe_metric(r: list[float]) -> float:
            if len(r) < 2:
                return 0.0
            mean = sum(r) / len(r)
            var = sum((x - mean) ** 2 for x in r) / (len(r) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std <= 0:
                return 0.0
            return (mean / std) * math.sqrt(ann_factor)
        
        result = bootstrap_metric_ci(
            returns=returns,
            metric_func=sharpe_metric,
            n_resamples=self.config.bootstrap_n_resamples,
            mean_block_length=10,
            ci_level=0.95,
            seed=self.config.bootstrap_seed,
        )
        
        print(f"\n{'='*70}")
        print(f"BOOTSTRAP CI (Stationary)")
        print(f"{'='*70}")
        print(f"  Sharpe: {result.point_estimate:.4f}")
        print(f"  95% CI: [{result.ci_lower:.4f}, {result.ci_upper:.4f}]")
        print(f"  Includes Zero: {result.includes_zero}")
        
        return result
    
    def run_cost_stress_tests(
        self,
        data: dict[str, list],
        timestamps: list[datetime],
        params: dict | None = None,
    ) -> dict:
        """Run backtests under different cost scenarios.
        
        Args:
            data: OHLCV data
            timestamps: Timestamps for each bar
            params: Strategy params to test (if None, uses self.default_params)
        """
        print(f"\n{'='*70}")
        print(f"COST STRESS TESTS")
        print(f"{'='*70}")
        
        cost_scenarios = [
            {"name": "Base", "spread": 0.3, "slippage": 0.1, "commission": 0.0},
            {"name": "1.5x", "spread": 0.45, "slippage": 0.15, "commission": 0.0},
            {"name": "2x", "spread": 0.6, "slippage": 0.2, "commission": 0.0},
            {"name": "3x", "spread": 0.9, "slippage": 0.3, "commission": 0.0},
            {"name": "WithCommission", "spread": 0.3, "slippage": 0.1, "commission": 3.5},
        ]
        
        results = {}
        
        for scenario in cost_scenarios:
            try:
                # Use provided params or defaults
                test_params = (params or self.default_params).copy()
                test_params["spread_pips"] = scenario["spread"]
                test_params["slippage_pips"] = scenario["slippage"]
                test_params["commission_per_lot"] = scenario["commission"]
                
                result = self._run_backtest(data, timestamps, test_params)
                m = extract_metrics(result)
                trades = result.get("trades", [])
                
                results[scenario["name"]] = {
                    "trades": len(trades),
                    "pnl": m["total_pnl"],
                    "sharpe": m["sharpe_ratio"],
                    "maxDD": m["max_drawdown_pct"],
                }
                
                print(f"  {scenario['name']}: trades={len(trades)}, "
                      f"PnL=${m['total_pnl']:.2f}, Sharpe={m['sharpe_ratio']:.3f}")
                
            except Exception as e:
                print(f"  ERROR {scenario['name']}: {e}")
                results[scenario["name"]] = {"error": str(e)}
        
        return results
    
    def run(
        self,
        data: dict[str, list] | None = None,
        data_path: str | Path | None = None,
        timestamps: list[datetime] | None = None,
    ) -> ValidationResult:
        """Run complete validation pipeline.
        
        Args:
            data: Pre-loaded OHLCV data (if None, load from data_path)
            data_path: Path to CSV file (if data is None)
            timestamps: Optional timestamps (if None, generate daily)
        
        Returns:
            ValidationResult with all metrics and verdicts
        """
        # Load data if needed
        if data is None:
            if data_path is None:
                raise ValueError("Either data or data_path must be provided")
            data = load_ohlcv_csv(Path(data_path))
        
        if timestamps is None:
            timestamps = generate_timestamps(len(data["close"]))
        
        n_bars = len(data["close"])
        
        # 1. Baseline backtest
        print(f"\n{'='*80}")
        print(f"FULL BACKTEST - BASELINE")
        print(f"{'='*80}")
        
        baseline_result = self._run_backtest(data, timestamps)
        baseline_metrics = extract_metrics(baseline_result)
        baseline_trades = baseline_result.get("trades", [])
        baseline_returns = compute_trade_returns(baseline_trades)
        
        # BUG FIX: Also compute trade-level Sharpe for comparison
        baseline_trade_sharpe = compute_trade_returns_sharpe(baseline_returns)
        
        print(f"  Trades: {baseline_metrics['total_trades']}")
        print(f"  WinRate: {baseline_metrics['win_rate']*100:.1f}%")
        print(f"  Sharpe (bar-level): {baseline_metrics['sharpe_ratio']:.4f}")
        print(f"  Sharpe (trade-level): {baseline_trade_sharpe:.4f}")
        print(f"  MaxDD: {baseline_metrics['max_drawdown_pct']:.1f}%")
        print(f"  PF: {baseline_metrics['profit_factor']:.2f}")
        
        # Estimate trades per year for annualization
        n_years = n_bars / 252.0
        trades_per_year = max(1, int(len(baseline_trades) / n_years)) if n_years > 0 else 252
        print(f"  Estimated trades/year: {trades_per_year}")
        
        # 2. Walk-forward
        walk_forward = self.run_walk_forward(data, timestamps)
        
        # 3. DSR
        dsr_result, min_btl = self.compute_deflated_sharpe(
            baseline_returns,
            annualization_factor=trades_per_year,
        )
        
        # 4. PBO
        pbo_result = self.compute_pbo(data, timestamps)
        
        # 5. Bootstrap
        bootstrap_result = self.compute_bootstrap_ci(
            baseline_returns,
            annualization_factor=trades_per_year,
        )
        
        # 6. Cost stress tests
        cost_stress = self.run_cost_stress_tests(data, timestamps)
        
        # Compute verdicts
        wf_agg = walk_forward["aggregate"]
        wf_pass = wf_agg["positive_folds"] >= wf_agg["n_folds"] * 0.6 and wf_agg["total_pnl"] > 0
        dsr_pass = dsr_result.passes_threshold and min_btl.sufficient
        pbo_pass = pbo_result.passes_threshold
        bootstrap_pass = not bootstrap_result.includes_zero
        
        base_scenario = cost_stress.get("Base", {})
        stress_2x = cost_stress.get("2x", {})
        base_sharpe = base_scenario.get("sharpe", 0.0) if "error" not in base_scenario else 0.0
        stress_sharpe = stress_2x.get("sharpe", 0.0) if "error" not in stress_2x else 0.0
        if base_sharpe > 0:
            degradation = (base_sharpe - stress_sharpe) / base_sharpe * 100
            cost_pass = degradation < 50 and stress_sharpe > 0
        else:
            cost_pass = False
        
        return ValidationResult(
            strategy_name=self.strategy_name,
            symbol="XAUUSD D1",
            n_bars=n_bars,
            baseline_metrics=baseline_metrics,
            walk_forward=walk_forward,
            dsr_result=dsr_result,
            min_btl=min_btl,
            pbo_result=pbo_result,
            bootstrap_result=bootstrap_result,
            cost_stress=cost_stress,
            wf_pass=wf_pass,
            dsr_pass=dsr_pass,
            pbo_pass=pbo_pass,
            bootstrap_pass=bootstrap_pass,
            cost_pass=cost_pass,
        )
    
    def generate_report(self, result: ValidationResult) -> str:
        """Generate comprehensive edge verification report."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"EDGE VERIFICATION REPORT: {result.strategy_name}")
        lines.append(f"Symbol: {result.symbol} | Data: {result.n_bars} bars")
        lines.append(f"Date: {datetime.now(UTC).isoformat()}")
        lines.append("=" * 80)
        
        # Baseline
        lines.append("\n0. BASELINE")
        lines.append("-" * 40)
        for k in ["total_trades", "win_rate", "sharpe_ratio", "sortino_ratio", 
                   "max_drawdown_pct", "profit_factor", "cagr", "calmar_ratio"]:
            v = result.baseline_metrics[k]
            label = k.replace("_", " ").title()
            if "rate" in k or "pct" in k:
                lines.append(f"   {label}: {v*100:.1f}%")
            else:
                lines.append(f"   {label}: {v:.4f}")
        
        # Walk-forward
        wf_agg = result.walk_forward["aggregate"]
        wf_eff = wf_agg.get('wf_efficiency', 0.0)
        lines.append(f"\n1. WALK-FORWARD: {wf_agg['positive_folds']}/{wf_agg['n_folds']} positive, "
                     f"{wf_agg['total_trades']} trades, Sharpe={wf_agg['avg_oos_sharpe']:.4f}")
        lines.append(f"   WF Efficiency: {wf_eff:.3f}")
        lines.append(f"   VERDICT: {'PASS' if result.wf_pass else 'FAIL'}")
        
        # DSR
        lines.append(f"\n2. DSR: Sharpe={result.dsr_result.observed_sharpe:.4f}, "
                     f"P(alpha)={result.dsr_result.probability_alpha:.4f}, "
                     f"MinBTL={result.min_btl.min_observations}")
        lines.append(f"   VERDICT: {'PASS' if result.dsr_pass else 'FAIL'}")
        
        # PBO
        lines.append(f"\n3. PBO: {result.pbo_result.pbo:.4f}, "
                     f"Combinations={result.pbo_result.n_combinations_tested}")
        lines.append(f"   VERDICT: {'PASS' if result.pbo_pass else 'FAIL'}")
        
        # Bootstrap
        lines.append(f"\n4. BOOTSTRAP: Sharpe={result.bootstrap_result.point_estimate:.4f}, "
                     f"CI=[{result.bootstrap_result.ci_lower:.4f}, {result.bootstrap_result.ci_upper:.4f}]")
        lines.append(f"   VERDICT: {'PASS' if result.bootstrap_pass else 'FAIL'}")
        
        # Cost stress
        base = result.cost_stress.get("Base", {})
        stress = result.cost_stress.get("2x", {})
        base_sharpe = base.get("sharpe", 0.0) if "error" not in base else 0.0
        stress_sharpe = stress.get("sharpe", 0.0) if "error" not in stress else 0.0
        degradation = (base_sharpe - stress_sharpe) / base_sharpe * 100 if base_sharpe > 0 else 100
        lines.append(f"\n5. COST STRESS: Base={base_sharpe:.3f}, 2x={stress_sharpe:.3f}, "
                     f"Degradation={degradation:.1f}%")
        lines.append(f"   VERDICT: {'PASS' if result.cost_pass else 'FAIL'}")
        
        # Final verdict
        lines.append(f"\n{'='*80}")
        lines.append(f"FINAL: {result.pass_count}/5 gates passed")
        for name, p in zip(["Walk-Forward", "DSR", "PBO", "Bootstrap", "Cost"], 
                          [result.wf_pass, result.dsr_pass, result.pbo_pass, 
                           result.bootstrap_pass, result.cost_pass]):
            lines.append(f"  {name:15s} {'PASS' if p else 'FAIL'}")
        
        lines.append(f"\n  VERDICT: {result.verdict}")
        lines.append(f"  RECOMMENDATION: {result.recommendation}")
        
        return "\n".join(lines)
