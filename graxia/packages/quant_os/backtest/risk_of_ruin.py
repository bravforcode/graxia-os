"""Risk of ruin calculation for trading strategies."""
from typing import List, Dict


def risk_of_ruin(win_rate: float, risk_reward: float, max_risk_pct: float, max_drawdown_pct: float) -> float:
    """
    Calculate risk of ruin probability.
    
    Args:
        win_rate: Win rate as decimal (e.g., 0.55 for 55%)
        risk_reward: Risk/Reward ratio (e.g., 2.0 means reward is 2x risk)
        max_risk_pct: Maximum risk per trade as decimal
        max_drawdown_pct: Maximum drawdown before ruin as decimal
    
    Returns:
        Probability of ruin (0.0 to 1.0)
    """
    if win_rate <= 0 or win_rate >= 1:
        return 1.0
    if risk_reward <= 0:
        return 1.0
    
    # Kelly-inspired ruin calculation
    # Edge = win_rate * reward - (1 - win_rate) * risk
    edge = win_rate * risk_reward - (1 - win_rate)
    
    if edge <= 0:
        # Negative edge = guaranteed ruin eventually
        return 1.0
    
    # Number of units to ruin
    units_to_ruin = max_drawdown_pct / max_risk_pct
    
    # Approximate risk of ruin using binomial distribution
    # P(ruin) ≈ ((1 - edge) / (1 + edge))^units_to_ruin
    q = (1 - edge) / (1 + edge)
    if q >= 1:
        return 1.0
    
    prob = q ** units_to_ruin
    return min(max(prob, 0.0), 1.0)


def kelly_criterion(win_rate: float, risk_reward: float) -> float:
    """
    Calculate optimal Kelly fraction.
    
    Returns:
        Optimal fraction of capital to risk per trade (0.0 to 1.0)
    """
    if win_rate <= 0 or win_rate >= 1 or risk_reward <= 0:
        return 0.0
    
    # Kelly formula: f* = (bp - q) / b
    # where b = reward/risk, p = win_rate, q = 1 - win_rate
    b = risk_reward
    p = win_rate
    q = 1 - p
    
    kelly = (b * p - q) / b
    return max(kelly, 0.0)


def expectancy(win_rate: float, risk_reward: float, risk_pct: float) -> float:
    """
    Calculate expected value per trade.
    
    Returns:
        Expected P&L per trade as percentage of capital
    """
    return win_rate * risk_reward * risk_pct - (1 - win_rate) * risk_pct


def compute_risk_analysis(trades: List[Dict], initial_capital: float, max_risk_pct: float = 0.005) -> Dict:
    """
    Compute full risk analysis from trade history.
    
    Args:
        trades: List of trade dicts with 'pnl' field
        initial_capital: Starting capital
        max_risk_pct: Maximum risk per trade as decimal
    """
    if not trades:
        return {"error": "no trades"}
    
    # Calculate win rate
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    win_rate = wins / len(trades)
    
    # Calculate average win/loss
    win_pnls = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
    loss_pnls = [t["pnl"] for t in trades if t.get("pnl", 0) < 0]
    
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss = abs(sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0
    
    # Risk/Reward ratio
    risk_reward = avg_win / avg_loss if avg_loss > 0 else 0
    
    # Calculate max drawdown
    equity = [initial_capital]
    for t in trades:
        equity.append(equity[-1] + t.get("pnl", 0))
    peak = equity[0]
    max_dd = 0
    for eq in equity:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # Risk of ruin
    ror = risk_of_ruin(win_rate, risk_reward, max_risk_pct, max_dd)
    
    # Kelly criterion
    kelly = kelly_criterion(win_rate, risk_reward)
    
    # Expected value
    exp = expectancy(win_rate, risk_reward, max_risk_pct)
    
    return {
        "win_rate": round(win_rate * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "risk_reward": round(risk_reward, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "risk_of_ruin": round(ror * 100, 2),
        "kelly_fraction": round(kelly * 100, 1),
        "expected_value": round(exp * 100, 3),
        "total_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": len(trades) - wins,
    }
