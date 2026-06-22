"""Phase 3B — Metrics calculation and cost attribution."""
from dataclasses import dataclass
from typing import Any


@dataclass
class Phase3BMetrics:
    scenario: str
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_spread_cost: float
    total_slippage_cost: float
    total_commission: float
    total_swap: float
    cost_share_of_pnl: float
    ambiguous_bar_count: int
    rejected_signal_count: int
    execution_quality: str


def calculate_phase_3b_metrics(result: dict, scenario: str) -> Phase3BMetrics:
    """Calculate metrics from engine result."""
    trades = result.get("trades", [])
    metrics = result.get("metrics", {})

    trade_count = len(trades)
    winning = [t for t in trades if t.get("pnl", 0) > 0]
    losing = [t for t in trades if t.get("pnl", 0) <= 0]

    win_rate = len(winning) / trade_count if trade_count > 0 else 0
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    avg_win = sum(t.get("pnl", 0) for t in winning) / len(winning) if winning else 0
    avg_loss = sum(t.get("pnl", 0) for t in losing) / len(losing) if losing else 0

    gross_profit = sum(t.get("pnl", 0) for t in winning)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_spread = sum(t.get("entry_spread_cost", 0) for t in trades)
    total_slippage = sum(t.get("entry_slippage_cost", 0) + t.get("exit_slippage_cost", 0) for t in trades)
    total_commission = sum(t.get("fees", 0) for t in trades)
    total_swap = sum(t.get("swap", 0) for t in trades) if trades and "swap" in trades[0] else 0

    total_cost = total_spread + total_slippage + total_commission + total_swap
    cost_share = total_cost / abs(total_pnl) if total_pnl != 0 else 0

    ambiguous = sum(1 for t in trades if t.get("ambiguous_bar", False))

    return Phase3BMetrics(
        scenario=scenario,
        trade_count=trade_count,
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        max_drawdown=0,  # TODO: calculate from equity curve
        sharpe_ratio=0,  # TODO: calculate
        total_spread_cost=total_spread,
        total_slippage_cost=total_slippage,
        total_commission=total_commission,
        total_swap=total_swap,
        cost_share_of_pnl=cost_share,
        ambiguous_bar_count=ambiguous,
        rejected_signal_count=0,
        execution_quality="CONSERVATIVE_BAR",
    )


def format_metrics_table(metrics_list: list[Phase3BMetrics]) -> str:
    """Format metrics as markdown table."""
    lines = ["| Metric | " + " | ".join(m.scenario for m in metrics_list) + " |"]
    lines.append("|---|" + "|".join(["---"] * len(metrics_list)) + "|")

    fields = [
        ("Trades", "trade_count"),
        ("Win Rate", lambda m: f"{m.win_rate:.1%}"),
        ("Total PnL", lambda m: f"${m.total_pnl:,.2f}"),
        ("Profit Factor", lambda m: f"{m.profit_factor:.2f}"),
        ("Spread Cost", lambda m: f"${m.total_spread_cost:,.2f}"),
        ("Slippage Cost", lambda m: f"${m.total_slippage_cost:,.2f}"),
        ("Commission", lambda m: f"${m.total_commission:,.2f}"),
        ("Swap", lambda m: f"${m.total_swap:,.2f}"),
        ("Cost Share", lambda m: f"{m.cost_share_of_pnl:.1%}"),
        ("Ambiguous Bars", "ambiguous_bar_count"),
    ]

    for label, field in fields:
        row = f"| {label} |"
        for m in metrics_list:
            if callable(field):
                val = field(m)
            else:
                val = getattr(m, field)
            row += f" {val} |"
        lines.append(row)

    return "\n".join(lines)
