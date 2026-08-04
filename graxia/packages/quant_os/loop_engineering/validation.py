"""
validation.py — 3-layer verification + injectable validation adapters.

Spec Part 2.5 (the most important): a candidate MUST pass ALL THREE layers
before it may be called "candidate"/"promising":
  1. DK-test (pooled, multi-asset): dk_t > threshold AND positive_sharpe_count >= 5
  2. Label-shuffle (>= 200 iterations): p < alpha
  3. Min-trades gate: total_trades >= min_trades (avoids COT 40-trade / BEVS 68-trade traps)

The agent MUST NOT report a hypothesis as promising from raw Sharpe alone.

Adapters are INJECTABLE (default = real scripts/ via importlib). This keeps the
loop testable with fast fakes and lets the is_stopped test prove the backtest is
never reached when stopped.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pre_register import (
    DEFAULT_DK_T_THRESHOLD,
    DEFAULT_LABEL_SHUFFLE_ALPHA,
    DEFAULT_MIN_POSITIVE_SHARPE,
    DEFAULT_MIN_TRADES,
)


@dataclass
class VerificationThresholds:
    dk_t_threshold: float = DEFAULT_DK_T_THRESHOLD
    min_positive_sharpe_count: int = DEFAULT_MIN_POSITIVE_SHARPE
    label_shuffle_alpha: float = DEFAULT_LABEL_SHUFFLE_ALPHA
    min_trades: int = DEFAULT_MIN_TRADES


@dataclass
class VerificationResult:
    dk_pass: bool
    label_shuffle_pass: bool
    min_trades_pass: bool
    is_candidate: bool  # True ONLY if all three pass
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateGates:
    """SP1b (2026-08-04): extended candidate gate result — adds cost stress.

    Holdout may only be opened when dk + label-shuffle + min-trades + cost
    stress ALL pass (Spec Part 2.5 + cost-stress requirement).
    """

    dk_pass: bool
    label_shuffle_pass: bool
    min_trades_pass: bool
    cost_stress_pass: bool
    is_candidate: bool  # True ONLY if all four pass

    def failed(self) -> list[str]:
        return [
            n
            for n, ok in [
                ("dk", self.dk_pass),
                ("label_shuffle", self.label_shuffle_pass),
                ("min_trades", self.min_trades_pass),
                ("cost_stress", self.cost_stress_pass),
            ]
            if not ok
        ]


def verify_candidate_gates(
    dk_result: dict[str, Any],
    label_shuffle_pvalue: float,
    total_trades: int,
    cost_stress: dict[str, Any] | None,
    thresholds: VerificationThresholds | None = None,
) -> CandidateGates:
    """Evaluate all four gates. is_candidate is True only if ALL pass.

    cost_stress: result of analyze_cost_sensitivity() — dict with
    cost_sensitivity and survives_stress_1/2/3. Pass = sensitivity in
    LOW/MEDIUM (survives at least 2x costs).
    """
    t = thresholds or VerificationThresholds()
    dk_t = float(dk_result.get("dk_t_stat", 0.0))
    pos_sharpe = dk_result.get("positive_sharpe_count", 0)
    dk_pass = (dk_t > t.dk_t_threshold) and (pos_sharpe >= t.min_positive_sharpe_count)
    ls_pass = label_shuffle_pvalue < t.label_shuffle_alpha
    mt_pass = total_trades >= t.min_trades
    if cost_stress is None:
        cost_pass = False
    else:
        sensitivity = cost_stress.get("cost_sensitivity", "HIGH")
        cost_pass = sensitivity in ("LOW", "MEDIUM")
    return CandidateGates(
        dk_pass=dk_pass,
        label_shuffle_pass=ls_pass,
        min_trades_pass=mt_pass,
        cost_stress_pass=cost_pass,
        is_candidate=dk_pass and ls_pass and mt_pass and cost_pass,
    )


def verify_three_layer(
    dk_result: dict[str, Any],
    label_shuffle_pvalue: float,
    total_trades: int,
    thresholds: VerificationThresholds | None = None,
) -> VerificationResult:
    """Evaluate all three gates. is_candidate is True only if ALL pass.

    Refuses to call anything a candidate on raw Sharpe alone (Spec Part 2.5).
    """
    t = thresholds or VerificationThresholds()
    dk_t = float(dk_result.get("dk_t_stat", 0.0))
    pos_sharpe = dk_result.get("positive_sharpe_count", 0)
    dk_pass = (dk_t > t.dk_t_threshold) and (pos_sharpe >= t.min_positive_sharpe_count)
    ls_pass = label_shuffle_pvalue < t.label_shuffle_alpha
    mt_pass = total_trades >= t.min_trades
    return VerificationResult(
        dk_pass=dk_pass,
        label_shuffle_pass=ls_pass,
        min_trades_pass=mt_pass,
        is_candidate=dk_pass and ls_pass and mt_pass,
        details={
            "dk_t_stat": dk_t,
            "positive_sharpe_count": pos_sharpe,
            "label_shuffle_pvalue": label_shuffle_pvalue,
            "total_trades": total_trades,
            "thresholds": t.__dict__,
        },
    )


# ---------------------------------------------------------------------------
# Injectable adapters
# ---------------------------------------------------------------------------
@dataclass
class ValidationAdapters:
    """Callable hooks the loop invokes. Inject fakes in tests; real ones in prod.

    Contract:
      run_backtest(pre_reg) -> {"returns": pd.DataFrame, "total_trades": int, "trade_log": str}
      run_dk_test(returns, total_trades) -> dict  (edge_search_all.run_dk_test shape)
      run_label_shuffle(pre_reg, returns) -> float  (p-value)
      run_holdout(pre_reg) -> bool  (True if sacred holdout confirms)
    """

    run_backtest: Callable | None = None
    run_dk_test: Callable | None = None
    run_label_shuffle: Callable | None = None
    run_cost_stress: Callable | None = None
    run_holdout: Callable | None = None

    def require(self, *names: str) -> None:
        for n in names:
            if getattr(self, n) is None:
                raise RuntimeError(
                    f"ValidationAdapters.{n} is not set. Inject a real adapter or "
                    f"build one via build_default_adapters()."
                )


def _load_script(module_name: str, filename: str):
    """Load a scripts/*.py module by path (repo convention: importlib, see env.py)."""
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    file_path = scripts_dir / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Script not found: {file_path}")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def build_default_adapters(signal_fn: Callable | None = None) -> ValidationAdapters:
    """Wire the REAL verification scripts. backtest/holdout remain injectable (data/strategy specific).

    - run_dk_test  -> scripts/edge_search_all.py:run_dk_test
    - run_label_shuffle -> scripts/label_shuffle_top.py:run_case (needs a signal_fn)
    - run_cost_stress -> validation/cost_stress.py:analyze_cost_sensitivity
    - run_backtest / run_holdout -> None (must be injected by caller)
    """
    esa = _load_script("edge_search_all", "edge_search_all.py")
    lst = _load_script("label_shuffle_top", "label_shuffle_top.py")
    from ..validation.cost_stress import analyze_cost_sensitivity

    def dk_adapter(returns, total_trades):
        return esa.run_dk_test(returns, total_trades)

    def ls_adapter(pre_reg, returns):  # pragma: no cover - requires real data + signal_fn
        if signal_fn is None:
            raise RuntimeError(
                "run_label_shuffle default requires a signal_fn (label_shuffle_top.run_case "
                "needs a signal function). Inject a custom adapter or pass signal_fn."
            )
        cost = lst.COST_RT_BPS.get(pre_reg.symbol, 3.5)
        res = lst.run_case(pre_reg.hypothesis, pre_reg.symbol, signal_fn, cost)
        return float(res.get("p_value", 1.0))

    def cost_stress_adapter(backtest_out: dict) -> dict:
        """SP1b: cost-stress from the backtest output (base PnL + costs)."""
        from dataclasses import asdict

        base_pnl = float(backtest_out.get("net_pnl", backtest_out.get("total_pnl", 0.0)))
        total_costs = float(backtest_out.get("total_costs", backtest_out.get("total_fees", 0.0)))
        return asdict(analyze_cost_sensitivity(base_pnl=base_pnl, total_costs=total_costs))

    return ValidationAdapters(
        run_backtest=None,
        run_dk_test=dk_adapter,
        run_label_shuffle=ls_adapter,
        run_cost_stress=cost_stress_adapter,
        run_holdout=None,
    )
