"""
Gate-based scaling with Monte Carlo integration.

Each gate defines statistical and risk-of-ruin criteria that must be met
before a lot increase is permitted.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass

from .monte_carlo import bootstrap_equity_paths


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    required_criteria: dict[str, float]
    actual_values: dict[str, float]
    prob_ruin: float
    decision: str


@dataclass
class GateConfig:
    name: str
    min_trades: int
    min_t_stat: float
    min_win_rate: float
    min_sharpe: float
    min_months: int
    min_balance: float
    max_prob_ruin_current: float
    max_prob_ruin_next: float


def check_gate_5(
    trade_pnls: np.ndarray,
    current_balance: float,
    config: GateConfig,
) -> GateResult:
    """
    Paper validation gate (Gate 5) -- validates edge exists on paper before going live.

    Checks: trade count, win rate, t-statistic, Sharpe ratio, Monte Carlo ruin probability.
    """
    if len(trade_pnls) == 0:
        raise ValueError("trade_pnls must be non-empty")

    n_trades = len(trade_pnls)
    win_rate = float(np.mean(trade_pnls > 0))
    mean_pnl = float(np.mean(trade_pnls))
    std_pnl = float(np.std(trade_pnls, ddof=1))
    t_stat = 0.0 if std_pnl == 0 else mean_pnl / (std_pnl / np.sqrt(n_trades))
    sharpe = 0.0 if std_pnl == 0 else mean_pnl / std_pnl

    mc = bootstrap_equity_paths(
        trade_pnls,
        n_sims=10_000,
        n_trades_forward=540,
        starting_balance=current_balance,
        kill_switch_balance=4500.0,
        lot_multiplier=1.0,
    )
    prob_ruin = mc["prob_ruin"]

    required = {
        "min_trades": float(config.min_trades),
        "min_t_stat": config.min_t_stat,
        "min_win_rate": config.min_win_rate,
        "min_sharpe": config.min_sharpe,
        "max_prob_ruin_current": config.max_prob_ruin_current,
    }
    actual = {
        "n_trades": float(n_trades),
        "t_stat": t_stat,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "prob_ruin": prob_ruin,
    }

    passed = (
        n_trades >= config.min_trades
        and t_stat >= config.min_t_stat
        and win_rate >= config.min_win_rate
        and sharpe >= config.min_sharpe
        and prob_ruin <= config.max_prob_ruin_current
    )

    decision = "PASS" if passed else "BLOCKED"
    if not passed:
        reasons = []
        if n_trades < config.min_trades:
            reasons.append(f"trades {n_trades} < {config.min_trades}")
        if t_stat < config.min_t_stat:
            reasons.append(f"t-stat {t_stat:.3f} < {config.min_t_stat}")
        if win_rate < config.min_win_rate:
            reasons.append(f"win_rate {win_rate:.3f} < {config.min_win_rate}")
        if sharpe < config.min_sharpe:
            reasons.append(f"sharpe {sharpe:.3f} < {config.min_sharpe}")
        if prob_ruin > config.max_prob_ruin_current:
            reasons.append(f"prob_ruin {prob_ruin:.4f} > {config.max_prob_ruin_current}")
        decision = f"BLOCKED: {'; '.join(reasons)}"

    return GateResult(
        gate_name=config.name,
        passed=passed,
        required_criteria=required,
        actual_values=actual,
        prob_ruin=prob_ruin,
        decision=decision,
    )


def check_gate_6(
    trade_pnls: np.ndarray,
    current_balance: float,
    config: GateConfig,
    next_lot_mult: float,
) -> GateResult:
    """
    LIVE scaling gate (Gate 6) -- validates edge is stable enough to increase lot size.

    Requires: t-stat >= 2.0, >= 1k trades, win_rate >= 0.55.
    Monte Carlo check: prob_ruin < max_prob_ruin_current at current lot,
    < max_prob_ruin_next at next tier.
    """
    if len(trade_pnls) == 0:
        raise ValueError("trade_pnls must be non-empty")

    n_trades = len(trade_pnls)
    win_rate = float(np.mean(trade_pnls > 0))
    mean_pnl = float(np.mean(trade_pnls))
    std_pnl = float(np.std(trade_pnls, ddof=1))
    t_stat = 0.0 if std_pnl == 0 else mean_pnl / (std_pnl / np.sqrt(n_trades))
    sharpe = 0.0 if std_pnl == 0 else mean_pnl / std_pnl

    mc_current = bootstrap_equity_paths(
        trade_pnls,
        n_sims=10_000,
        n_trades_forward=540,
        starting_balance=current_balance,
        kill_switch_balance=4500.0,
        lot_multiplier=1.0,
    )
    prob_ruin_current = mc_current["prob_ruin"]

    mc_next = bootstrap_equity_paths(
        trade_pnls,
        n_sims=10_000,
        n_trades_forward=540,
        starting_balance=current_balance,
        kill_switch_balance=4500.0,
        lot_multiplier=next_lot_mult,
    )
    prob_ruin_next = mc_next["prob_ruin"]

    required = {
        "min_trades": float(config.min_trades),
        "min_t_stat": config.min_t_stat,
        "min_win_rate": config.min_win_rate,
        "min_sharpe": config.min_sharpe,
        "max_prob_ruin_current": config.max_prob_ruin_current,
        "max_prob_ruin_next": config.max_prob_ruin_next,
    }
    actual = {
        "n_trades": float(n_trades),
        "t_stat": t_stat,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "prob_ruin_current": prob_ruin_current,
        "prob_ruin_next": prob_ruin_next,
    }

    passed = (
        n_trades >= config.min_trades
        and t_stat >= config.min_t_stat
        and win_rate >= config.min_win_rate
        and sharpe >= config.min_sharpe
        and prob_ruin_current <= config.max_prob_ruin_current
        and prob_ruin_next <= config.max_prob_ruin_next
    )

    decision = "PASS" if passed else "BLOCKED"
    if not passed:
        reasons = []
        if n_trades < config.min_trades:
            reasons.append(f"trades {n_trades} < {config.min_trades}")
        if t_stat < config.min_t_stat:
            reasons.append(f"t-stat {t_stat:.3f} < {config.min_t_stat}")
        if win_rate < config.min_win_rate:
            reasons.append(f"win_rate {win_rate:.3f} < {config.min_win_rate}")
        if sharpe < config.min_sharpe:
            reasons.append(f"sharpe {sharpe:.3f} < {config.min_sharpe}")
        if prob_ruin_current > config.max_prob_ruin_current:
            reasons.append(f"prob_ruin_current {prob_ruin_current:.4f} > {config.max_prob_ruin_current}")
        if prob_ruin_next > config.max_prob_ruin_next:
            reasons.append(f"prob_ruin_next {prob_ruin_next:.4f} > {config.max_prob_ruin_next}")
        decision = f"BLOCKED: {'; '.join(reasons)}"

    return GateResult(
        gate_name=config.name,
        passed=passed,
        required_criteria=required,
        actual_values=actual,
        prob_ruin=prob_ruin_current,
        decision=decision,
    )


def evaluate_ladder(
    trade_pnls_by_period: list[np.ndarray],
    gates: list[GateConfig],
    starting_capital: float,
) -> list[GateResult]:
    """
    Evaluate entire scaling ladder against period-separated trade PnLs.

    trade_pnls_by_period[i] corresponds to gate[i] (cumulative up to that period).
    Returns list of GateResult showing when each gate would pass or fail.
    """
    results = []
    cumulative_pnls: list[float] = []

    for i, (period_pnls, gate) in enumerate(zip(trade_pnls_by_period, gates)):
        cumulative_pnls.extend(period_pnls.tolist())
        cumulative = np.array(cumulative_pnls)

        try:
            if gate.name.startswith("Gate 5"):
                result = check_gate_5(cumulative, starting_capital, gate)
            else:
                lot_mult = (i + 2) if i < len(gates) else 1.0
                result = check_gate_6(cumulative, starting_capital, gate, lot_mult)
        except ValueError:
            result = GateResult(
                gate_name=gate.name,
                passed=False,
                required_criteria={},
                actual_values={"error": "empty_trades"},
                prob_ruin=1.0,
                decision="BLOCKED: no trades available",
            )
        results.append(result)

    return results
