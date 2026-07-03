"""
Predefined scaling ladder configurations for lot progression.

Ladder A -- "Fast": scale the moment each gate's minimum threshold is crossed.
Ladder B -- "Fast with margin of safety": tighter Monte Carlo thresholds.
"""
from .scaling_gate import GateConfig


LADDER_A_GATES = [
    GateConfig(
        name="Gate 6a: 0.01 -> 0.02",
        min_trades=540,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.05,
        max_prob_ruin_next=0.02,
    ),
    GateConfig(
        name="Gate 6b: 0.02 -> 0.03",
        min_trades=1080,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=2,
        min_balance=6000.0,
        max_prob_ruin_current=0.05,
        max_prob_ruin_next=0.02,
    ),
    GateConfig(
        name="Gate 6c: 0.03 -> 0.04",
        min_trades=1620,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=3,
        min_balance=8000.0,
        max_prob_ruin_current=0.05,
        max_prob_ruin_next=0.02,
    ),
]

LADDER_B_GATES = [
    GateConfig(
        name="Gate 6a: 0.01 -> 0.02",
        min_trades=540,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.03,
        max_prob_ruin_next=0.01,
    ),
    GateConfig(
        name="Gate 6b: 0.02 -> 0.03",
        min_trades=1080,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=2,
        min_balance=6000.0,
        max_prob_ruin_current=0.03,
        max_prob_ruin_next=0.01,
    ),
    GateConfig(
        name="Gate 6c: 0.03 -> 0.04",
        min_trades=1620,
        min_t_stat=2.0,
        min_win_rate=0.55,
        min_sharpe=0.5,
        min_months=3,
        min_balance=8000.0,
        max_prob_ruin_current=0.03,
        max_prob_ruin_next=0.01,
    ),
]


def get_current_lot(trades_completed: int, gates_passed: int) -> float:
    """
    Return recommended lot size based on trade count and gates cleared.

    Gate 0 (not started): 0.01 lot (paper)
    Gate 1 passed: 0.02 lot
    Gate 2 passed: 0.03 lot
    Gate 3 passed: 0.04 lot
    """
    base = 0.01
    return base * (gates_passed + 1)


def next_gate_info(current_lot: float, current_trades: int) -> GateConfig | None:
    """
    Return the GateConfig for the next lot increase, or None if at max lot.

    Derives which ladder tier you're on from current_lot and looks up the
    corresponding gate from Ladder A (default).
    """
    lot_to_gate_index = {0.01: 0, 0.02: 1, 0.03: 2}
    idx = lot_to_gate_index.get(current_lot)
    if idx is None or idx >= len(LADDER_A_GATES):
        return None
    return LADDER_A_GATES[idx]
