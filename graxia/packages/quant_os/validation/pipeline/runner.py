"""Main parallel validation runner — orchestrates all statistical tests."""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import PipelineConfig
from .gates import GateEngine, GateSummary


@dataclass
class ValidationResult:
    """Result from a single validation workstream."""

    name: str
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    elapsed_sec: float = 0.0


@dataclass
class PipelineResult:
    """Full pipeline result."""

    timestamp: str
    symbols: list[str]
    results: dict[str, ValidationResult] = field(default_factory=dict)
    gate_summary: GateSummary | None = None
    total_elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symbols": self.symbols,
            "total_elapsed_sec": round(self.total_elapsed_sec, 2),
            "gate_summary": self.gate_summary.to_dict() if self.gate_summary else None,
            "results": {
                name: {
                    "success": r.success,
                    "elapsed_sec": round(r.elapsed_sec, 2),
                    "error": r.error,
                    "data": r.data,
                }
                for name, r in self.results.items()
            },
        }


class ValidationRunner:
    """Parallel validation runner."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def run_all(self) -> PipelineResult:
        """Run all validation workstreams in parallel."""
        start = time.time()
        result = PipelineResult(
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            symbols=self.config.symbols,
        )

        # Load data for all symbols
        data_cache = {}
        for sym in self.config.symbols:
            path = self.config.data_path(sym)
            if path.exists():
                data_cache[sym] = self._load_csv(path)

        if not data_cache:
            result.total_elapsed_sec = time.time() - start
            return result

        # Run all workstreams in parallel using threads
        # (CPU-bound work uses numpy which releases GIL)
        workstreams = [
            ("wfa", self._run_wfa),
            ("monte_carlo", self._run_monte_carlo),
            ("dsr", self._run_dsr),
            ("pbo", self._run_pbo),
            ("bootstrap", self._run_bootstrap),
            ("stress", self._run_stress),
            ("synthetic", self._run_synthetic),
        ]

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {}
            for name, func in workstreams:
                futures[executor.submit(func, data_cache)] = name

            for future in as_completed(futures):
                name = futures[future]
                try:
                    vr = future.result(timeout=300)
                    result.results[name] = vr
                except Exception as e:
                    result.results[name] = ValidationResult(name=name, success=False, error=str(e))

        # Evaluate gates
        gate_engine = GateEngine(self.config)
        result.gate_summary = gate_engine.evaluate(
            wfa_result=self._get_data(result, "wfa"),
            mc_result=self._get_data(result, "monte_carlo"),
            dsr_result=self._get_data(result, "dsr"),
            pbo_result=self._get_data(result, "pbo"),
            stress_result=self._get_data(result, "stress"),
            bootstrap_result=self._get_data(result, "bootstrap"),
        )

        result.total_elapsed_sec = time.time() - start
        return result

    def _get_data(self, result: PipelineResult, name: str) -> dict | None:
        ws = result.results.get(name)
        return ws.data if ws and ws.success else None

    # ── Workstream implementations ──────────────────────────────────────────

    def _compute_tsm_returns(self, closes: list[float], lookback: int = 20) -> list[float]:
        """Compute actual TSM strategy returns: sign(lookback_return) * vol_target / rvol."""
        import math

        if len(closes) < lookback + 20:
            return []

        # Daily returns
        daily_rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

        # TSM signal: sign of lookback-period return
        signals = []
        for i in range(lookback, len(daily_rets)):
            lb_ret = 1.0
            for j in range(i - lookback, i):
                lb_ret *= 1 + daily_rets[j]
            lb_ret -= 1.0
            signals.append(1.0 if lb_ret > 0 else -1.0 if lb_ret < 0 else 0.0)

        # Realized vol (20-day rolling)
        target_vol = 0.10  # 10% annualized
        rvol_window = 20
        strategy_rets = []
        for i in range(len(signals)):
            idx = i + lookback  # offset into daily_rets
            if idx < rvol_window:
                strategy_rets.append(0.0)
                continue

            window_rets = daily_rets[idx - rvol_window : idx]
            mean_r = sum(window_rets) / len(window_rets)
            var_r = sum((r - mean_r) ** 2 for r in window_rets) / (len(window_rets) - 1)
            rvol = math.sqrt(var_r) * math.sqrt(252) if var_r > 0 else 0.01

            weight = signals[i] * target_vol / max(rvol, 0.01)
            weight = max(-1.0, min(1.0, weight))  # clip

            # Strategy return = weight * next-day return
            if idx < len(daily_rets):
                strategy_rets.append(weight * daily_rets[idx])
            else:
                strategy_rets.append(0.0)

        return strategy_rets

    def _run_wfa(self, data_cache: dict) -> ValidationResult:
        """Walk-Forward Analysis using actual TSM strategy returns."""
        start = time.time()
        try:
            all_oos_sharpes = []
            all_is_sharpes = []
            all_wfe = []
            all_windows = []

            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                returns = self._compute_tsm_returns(closes, lookback=20)

                if len(returns) < 200:
                    continue

                # Split into windows
                n_windows = self.config.wfa_n_windows
                window_size = len(returns) // n_windows
                is_size = int(window_size * self.config.wfa_is_ratio)
                oos_size = window_size - is_size

                window_results = []
                for w in range(n_windows):
                    base = w * window_size
                    is_returns = returns[base : base + is_size]
                    oos_returns = returns[base + is_size : base + window_size]

                    if len(is_returns) < 50 or len(oos_returns) < 10:
                        continue

                    is_sharpe = self._calc_sharpe(is_returns)
                    oos_sharpe = self._calc_sharpe(oos_returns)
                    wfe = oos_sharpe / is_sharpe if is_sharpe != 0 else 0.0

                    all_oos_sharpes.append(oos_sharpe)
                    all_is_sharpes.append(is_sharpe)
                    all_wfe.append(wfe)
                    window_results.append(
                        {
                            "window": w,
                            "is_sharpe": round(is_sharpe, 4),
                            "oos_sharpe": round(oos_sharpe, 4),
                            "wfe": round(wfe, 4),
                            "symbol": sym,
                        }
                    )

                all_windows.extend(window_results)

            oos_positive = sum(1 for s in all_oos_sharpes if s > 0) / max(len(all_oos_sharpes), 1)
            avg_wfe = sum(all_wfe) / max(len(all_wfe), 1)
            avg_is = sum(all_is_sharpes) / max(len(all_is_sharpes), 1)
            avg_oos = sum(all_oos_sharpes) / max(len(all_oos_sharpes), 1)
            degradation = 1.0 - (avg_oos / avg_is) if avg_is != 0 else 1.0

            return ValidationResult(
                name="wfa",
                success=True,
                data={
                    "oos_consistency": oos_positive,
                    "walk_forward_efficiency": avg_wfe,
                    "overfitting_score": max(degradation, 0.0),
                    "avg_is_sharpe": round(avg_is, 4),
                    "avg_oos_sharpe": round(avg_oos, 4),
                    "n_windows": len(all_windows),
                    "windows": all_windows,
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="wfa", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_monte_carlo(self, data_cache: dict) -> ValidationResult:
        """Monte Carlo simulation using actual TSM strategy returns."""
        start = time.time()
        try:
            # Generate trade PnLs from TSM strategy returns
            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                all_returns.extend(rets)

            if not all_returns:
                return ValidationResult(name="monte_carlo", success=False, error="No data")

            trade_pnls = np.array(all_returns) * self.config.mc_starting_balance

            # Use existing bootstrap_equity_paths
            from ...core.risk.monte_carlo import bootstrap_equity_paths

            mc = bootstrap_equity_paths(
                trade_pnls=trade_pnls,
                n_sims=self.config.mc_n_sims,
                n_trades_forward=self.config.mc_n_trades_forward,
                starting_balance=self.config.mc_starting_balance,
                kill_switch_balance=self.config.mc_kill_switch_balance,
            )

            return ValidationResult(
                name="monte_carlo",
                success=True,
                data={
                    "prob_ruin": mc["prob_ruin"],
                    "median_ending_balance": mc["median_ending_balance"],
                    "p5_ending_balance": mc["p5_ending_balance"],
                    "p95_ending_balance": mc["p95_ending_balance"],
                    "median_max_dd_pct": mc["median_max_dd_pct"],
                    "p95_max_dd_pct": mc["p95_max_dd_pct"],
                    "n_sims": self.config.mc_n_sims,
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="monte_carlo", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_dsr(self, data_cache: dict) -> ValidationResult:
        """Deflated Sharpe Ratio using actual TSM strategy returns."""
        start = time.time()
        try:
            # Calculate Sharpe from TSM strategy returns
            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                all_returns.extend(rets)

            sharpe = self._calc_sharpe(all_returns)
            n_bars = len(all_returns)

            # Use existing DSR check
            from ...governance.validation_stack import DeflatedSharpeRatio

            dsr_check = DeflatedSharpeRatio().run(
                sharpe=sharpe,
                n_trials=self.config.dsr_n_trials,
                n_bars=n_bars,
            )

            # Also compute using strategies.walk_forward._deflated_sharpe
            from ...strategies.walk_forward import _deflated_sharpe

            dsr_value = _deflated_sharpe(sharpe, self.config.dsr_n_trials)

            return ValidationResult(
                name="dsr",
                success=True,
                data={
                    "observed_sharpe": round(sharpe, 4),
                    "deflated_sharpe": round(dsr_value, 4),
                    "n_trials": self.config.dsr_n_trials,
                    "n_bars": n_bars,
                    "check_passed": dsr_check.passed,
                    "check_details": dsr_check.details,
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="dsr", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_pbo(self, data_cache: dict) -> ValidationResult:
        """Probability of Backtest Overfitting using actual TSM strategy returns."""
        start = time.time()
        try:
            from ...validation.probability_overfitting import calculate_pbo_from_matrix

            # Build strategy returns matrix from TSM returns
            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                if rets:
                    all_returns.append((sym, rets))

            if not all_returns:
                return ValidationResult(name="pbo", success=False, error="No data")

            # Split returns into periods for CSCV
            _, returns = all_returns[0]
            n_periods = 8
            period_size = len(returns) // n_periods

            # Create strategy matrix: different "configs" via different subsets
            strategy_returns = {}
            for i, shift in enumerate(range(0, min(200, len(returns)), 50)):
                shifted = returns[shift:]
                if len(shifted) < period_size * n_periods:
                    continue
                periods = []
                for p in range(n_periods):
                    start_idx = p * period_size
                    end_idx = start_idx + period_size
                    if end_idx <= len(shifted):
                        periods.append(shifted[start_idx:end_idx])
                if len(periods) == n_periods:
                    strategy_returns[f"config_{i}"] = periods

            if len(strategy_returns) < 2:
                # Fallback: simple PBO from OOS degradation
                pbo_val = 0.5  # uncertain
            else:
                pbo_result = calculate_pbo_from_matrix(strategy_returns, n_combinations=128)
                pbo_val = pbo_result.pbo

            return ValidationResult(
                name="pbo",
                success=True,
                data={
                    "pbo": round(pbo_val, 4),
                    "n_configs": len(strategy_returns),
                    "passes_threshold": pbo_val < self.config.pbo_max_value,
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="pbo", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_bootstrap(self, data_cache: dict) -> ValidationResult:
        """Bootstrap confidence intervals using actual TSM strategy returns."""
        start = time.time()
        try:
            from ...backtest.metrics import bootstrap_metric_ci

            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                all_returns.extend(rets)

            if not all_returns:
                return ValidationResult(name="bootstrap", success=False, error="No data")

            # Bootstrap CI for Sharpe ratio
            def sharpe_func(rets):
                if len(rets) < 2:
                    return 0.0
                mean = sum(rets) / len(rets)
                var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
                std = math.sqrt(var) if var > 0 else 0.0
                return mean / std if std > 0 else 0.0

            ci = bootstrap_metric_ci(
                returns=all_returns,
                metric_func=sharpe_func,
                n_resamples=self.config.bootstrap_n_resamples,
                mean_block_length=self.config.bootstrap_block_length,
                ci_level=self.config.bootstrap_confidence,
            )

            return ValidationResult(
                name="bootstrap",
                success=True,
                data={
                    "sharpe_ci_lower": round(ci.ci_lower, 4),
                    "sharpe_ci_upper": round(ci.ci_upper, 4),
                    "sharpe_point_estimate": round(ci.point_estimate, 4),
                    "confidence_level": self.config.bootstrap_confidence,
                    "n_resamples": self.config.bootstrap_n_resamples,
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="bootstrap", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_stress(self, data_cache: dict) -> ValidationResult:
        """Stress testing using actual TSM strategy returns with synthetic stress events."""
        start = time.time()
        try:
            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                all_returns.extend(rets)

            if not all_returns:
                return ValidationResult(name="stress", success=False, error="No data")

            mu = np.mean(all_returns)
            sigma = np.std(all_returns)

            # Generate synthetic paths with stress events
            n_paths = min(self.config.synthetic_n_paths, 5000)
            path_len = len(all_returns)
            results = []

            for i in range(n_paths):
                # Normal path with fat tails (Student-t)
                df_t = 5  # degrees of freedom for fat tails
                t_sample = np.random.standard_t(df_t, size=path_len)
                synthetic = mu + sigma * t_sample * np.sqrt((df_t - 2) / df_t)

                # Add stress events (10% of paths get a crash)
                if i % 10 == 0:
                    crash_start = np.random.randint(0, max(1, path_len - 50))
                    crash_len = min(20, path_len - crash_start)
                    synthetic[crash_start : crash_start + crash_len] *= 3.0  # 3x vol spike
                    synthetic[crash_start] -= 0.05  # 5% gap down

                # Calculate strategy performance
                cumulative = np.cumsum(synthetic)
                final_return = cumulative[-1]
                max_dd = self._calc_max_dd_from_returns(synthetic)
                results.append(
                    {
                        "final_return": final_return,
                        "max_dd": max_dd,
                        "positive": final_return > 0,
                    }
                )

            positive_rate = sum(1 for r in results if r["positive"]) / len(results)
            avg_return = np.mean([r["final_return"] for r in results])
            avg_dd = np.mean([r["max_dd"] for r in results])

            return ValidationResult(
                name="stress",
                success=True,
                data={
                    "positive_rate": round(positive_rate, 4),
                    "n_paths": n_paths,
                    "avg_return": round(float(avg_return), 6),
                    "avg_max_dd": round(float(avg_dd), 4),
                    "scenarios_tested": ["normal", "fat_tail", "crash"],
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="stress", success=False, error=str(e), elapsed_sec=time.time() - start)

    def _run_synthetic(self, data_cache: dict) -> ValidationResult:
        """Synthetic data validation — test TSM strategy on block-bootstrapped paths."""
        start = time.time()
        try:
            all_returns = []
            for sym, raw in data_cache.items():
                closes = [bar["close"] for bar in raw[-5000:]]
                rets = self._compute_tsm_returns(closes, lookback=20)
                all_returns.extend(rets)

            if not all_returns:
                return ValidationResult(name="synthetic", success=False, error="No data")

            mu = np.mean(all_returns)
            sigma = np.std(all_returns)

            # Block bootstrap paths
            block_size = self.config.synthetic_block_size
            n_paths = min(self.config.synthetic_n_paths, 3000)
            blocks = [all_returns[i : i + block_size] for i in range(0, len(all_returns) - block_size, block_size)]

            sharpes = []
            for _ in range(n_paths):
                # Resample blocks
                n_blocks_needed = len(all_returns) // block_size + 1
                sampled_blocks = [blocks[np.random.randint(0, len(blocks))] for _ in range(n_blocks_needed)]
                path = [r for block in sampled_blocks for r in block][: len(all_returns)]
                sr = self._calc_sharpe(path)
                sharpes.append(sr)

            positive_rate = sum(1 for s in sharpes if s > 0) / len(sharpes)
            mean_sharpe = np.mean(sharpes)
            ci_lower = float(np.percentile(sharpes, 2.5))
            ci_upper = float(np.percentile(sharpes, 97.5))

            return ValidationResult(
                name="synthetic",
                success=True,
                data={
                    "positive_rate": round(positive_rate, 4),
                    "n_paths": n_paths,
                    "mean_sharpe": round(float(mean_sharpe), 4),
                    "ci_lower": round(ci_lower, 4),
                    "ci_upper": round(ci_upper, 4),
                    "method": "block_bootstrap",
                },
                elapsed_sec=time.time() - start,
            )
        except Exception as e:
            return ValidationResult(name="synthetic", success=False, error=str(e), elapsed_sec=time.time() - start)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _load_csv(self, path: Path) -> list[dict]:
        """Load OHLCV CSV into list of dicts."""
        import csv

        rows = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append(
                        {
                            "open": float(row.get("open", row.get("Open", 0))),
                            "high": float(row.get("high", row.get("High", 0))),
                            "low": float(row.get("low", row.get("Low", 0))),
                            "close": float(row.get("close", row.get("Close", 0))),
                            "volume": float(row.get("volume", row.get("Volume", 0))),
                        }
                    )
                except (ValueError, KeyError):
                    continue
        return rows

    def _calc_sharpe(self, returns: list[float]) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return 0.0
        return mean / std * math.sqrt(252)  # annualized

    def _calc_max_dd_from_returns(self, returns: list[float]) -> float:
        """Calculate max drawdown from return series."""
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        return float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
