"""Phase 3B — Metrics calculation and cost attribution."""
import math
from dataclasses import dataclass
from datetime import datetime
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


def _max_drawdown(equity_curve: list[dict], initial_capital: float | None = None) -> float:
    """Maximum peak-to-trough equity decline (absolute)."""
    if not equity_curve:
        return 0.0

    peak = initial_capital
    if peak is None:
        peak = float(equity_curve[0].get("equity", 0))

    max_dd = 0.0
    for point in equity_curve:
        equity = float(point.get("equity", 0))
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _extract_returns(equity_curve: list[dict]) -> list[float]:
    """Period returns from adjacent equity-curve points."""
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = float(equity_curve[i - 1].get("equity", 0))
        curr = float(equity_curve[i].get("equity", 0))
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _std_dev(values: list[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """Maximum peak-to-trough equity decline as a positive percentage.

    Example: a 15% decline returns ``0.15``.

    Edge cases: empty series, non-positive starting equity, or any NaN value
    returns ``0.0``.
    """
    if not equity_curve:
        return 0.0

    peak = float(equity_curve[0])
    if peak <= 0 or math.isnan(peak):
        return 0.0

    max_dd = 0.0
    for point in equity_curve[1:]:
        equity = float(point)
        if math.isnan(equity) or equity <= 0:
            return 0.0
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Annualized Sharpe ratio from a series of period returns.

    ``risk_free_rate`` is treated as an annual rate and is de-annualized using
    ``periods_per_year`` before the excess return is computed.

    Edge cases: fewer than two returns, zero standard deviation, or any NaN
    value returns ``0.0``.
    """
    if not returns or len(returns) < 2:
        return 0.0

    clean_returns: list[float] = []
    for r in returns:
        rv = float(r)
        if math.isnan(rv):
            return 0.0
        clean_returns.append(rv)

    if len(clean_returns) < 2:
        return 0.0

    mean_return = sum(clean_returns) / len(clean_returns)
    per_period_rf = (
        risk_free_rate / periods_per_year if periods_per_year > 0 else 0.0
    )
    std = _std_dev(clean_returns)
    if std < 1e-12:
        return 0.0

    ratio = ((mean_return - per_period_rf) / std) * math.sqrt(periods_per_year)
    if math.isnan(ratio):
        return 0.0
    return ratio


def _periods_per_year(equity_curve: list[dict]) -> int:
    """Infer the number of equity-curve periods per year from timestamps."""
    if len(equity_curve) < 2:
        return 252

    seconds_per_year = 365.25 * 24 * 60 * 60
    intervals: list[float] = []
    for i in range(1, len(equity_curve)):
        t1 = equity_curve[i - 1].get("timestamp")
        t2 = equity_curve[i].get("timestamp")
        if not t1 or not t2:
            continue
        try:
            dt1 = datetime.fromisoformat(t1) if isinstance(t1, str) else t1
            dt2 = datetime.fromisoformat(t2) if isinstance(t2, str) else t2
            intervals.append((dt2 - dt1).total_seconds())
        except Exception:
            continue

    if not intervals:
        return 252

    median_interval = sorted(intervals)[len(intervals) // 2]
    if median_interval <= 0:
        return 252

    return max(1, int(round(seconds_per_year / median_interval)))


def _sharpe_ratio(equity_curve: list[dict]) -> float:
    """Annualized Sharpe ratio from equity-curve returns."""
    returns = _extract_returns(equity_curve)
    periods = _periods_per_year(equity_curve)
    return calculate_sharpe_ratio(
        returns, risk_free_rate=0.0, periods_per_year=periods
    )


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

    equity_curve = result.get("equity_curve", [])
    initial_capital = result.get("config", {}).get("initial_capital")
    max_dd = _max_drawdown(equity_curve, initial_capital)
    sharpe = _sharpe_ratio(equity_curve)

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
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
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
