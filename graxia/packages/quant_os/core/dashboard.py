"""
Monitoring Dashboard — Real-time metrics

Displays:
- Live P&L
- Strategy performance
- Risk metrics
- Regime status
- League standings
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class DashboardMetrics:
    """Dashboard metrics snapshot"""

    timestamp: datetime

    # Account
    balance: float
    equity: float
    unrealized_pnl: float
    daily_pnl: float
    total_pnl: float

    # Risk
    drawdown_pct: float
    max_drawdown_pct: float
    daily_loss_pct: float

    # Trading
    open_positions: int
    total_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float

    # Strategy
    active_strategies: int
    total_strategies: int
    top_strategy: str
    strategy_scores: dict[str, int]

    # Regime
    current_regime: str
    regime_confidence: float


class Dashboard:
    """
    Real-time monitoring dashboard.

    Usage:
        dashboard = Dashboard()
        dashboard.update(metrics)
        dashboard.render()
    """

    def __init__(self):
        self.history: list[DashboardMetrics] = []
        self.alerts: list[str] = []

    def update(self, metrics: DashboardMetrics):
        """Update dashboard with new metrics"""
        self.history.append(metrics)

        # Keep last 1000 snapshots
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

        # Check for alerts
        self._check_alerts(metrics)

    def render(self, metrics: DashboardMetrics) -> str:
        """Render dashboard as text"""
        lines = []
        lines.append("=" * 70)
        lines.append("  GOLD BOT — Live Dashboard")
        lines.append(f"  {metrics.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("=" * 70)

        # Account
        lines.append("\n  📊 ACCOUNT")
        lines.append(f"  Balance:    ${metrics.balance:,.2f}")
        lines.append(f"  Equity:     ${metrics.equity:,.2f}")
        lines.append(f"  Unrealized: ${metrics.unrealized_pnl:+,.2f}")
        lines.append(f"  Daily P&L:  ${metrics.daily_pnl:+,.2f}")
        lines.append(f"  Total P&L:  ${metrics.total_pnl:+,.2f}")

        # Risk
        lines.append("\n  🛡️ RISK")
        dd_emoji = "🟢" if metrics.drawdown_pct < 5 else "🟡" if metrics.drawdown_pct < 10 else "🔴"
        lines.append(f"  Drawdown:   {dd_emoji} {metrics.drawdown_pct:.2f}%")
        lines.append(f"  Max DD:     {metrics.max_drawdown_pct:.2f}%")
        lines.append(f"  Daily Loss: {metrics.daily_loss_pct:.2f}%")

        # Trading
        lines.append("\n  📈 TRADING")
        lines.append(f"  Positions:  {metrics.open_positions}")
        lines.append(f"  Trades:     {metrics.total_trades}")
        lines.append(f"  Win Rate:   {metrics.win_rate:.1%}")
        lines.append(f"  Profit Factor: {metrics.profit_factor:.2f}")
        lines.append(f"  Sharpe:     {metrics.sharpe_ratio:.2f}")

        # Strategies
        lines.append("\n  🎯 STRATEGIES")
        lines.append(f"  Active:     {metrics.active_strategies}/{metrics.total_strategies}")
        lines.append(f"  Top:        {metrics.top_strategy}")

        # Top 5 strategy scores
        sorted_scores = sorted(metrics.strategy_scores.items(), key=lambda x: x[1], reverse=True)[:5]

        for name, score in sorted_scores:
            bar = "█" * (score // 10)
            lines.append(f"    {name:<18} {score:>3} {bar}")

        # Regime
        lines.append("\n  🌊 REGIME")
        regime_emoji = {
            "TRENDING_UP": "🟢↑",
            "TRENDING_DOWN": "🔴↓",
            "RANGING": "🟡↔",
            "HIGH_VOLATILITY": "🔴⚡",
            "LOW_VOLATILITY": "🟢😴",
            "CRISIS": "🚨",
        }.get(metrics.current_regime, "❓")

        lines.append(f"  Current:    {regime_emoji} {metrics.current_regime}")
        lines.append(f"  Confidence: {metrics.regime_confidence:.1%}")

        # Alerts
        if self.alerts:
            lines.append("\n  ⚠️ ALERTS")
            for alert in self.alerts[-5:]:
                lines.append(f"    {alert}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)

    def _check_alerts(self, metrics: DashboardMetrics):
        """Check for alert conditions"""
        # High drawdown
        if metrics.drawdown_pct > 10:
            self.alerts.append(f"🔴 High drawdown: {metrics.drawdown_pct:.2f}%")

        # Daily loss
        if metrics.daily_loss_pct > 2:
            self.alerts.append(f"🔴 Daily loss limit: {metrics.daily_loss_pct:.2f}%")

        # Low win rate
        if metrics.total_trades > 10 and metrics.win_rate < 0.4:
            self.alerts.append(f"🟡 Low win rate: {metrics.win_rate:.1%}")

        # Keep last 20 alerts
        if len(self.alerts) > 20:
            self.alerts = self.alerts[-20:]

    def get_summary(self) -> dict:
        """Get summary statistics"""
        if not self.history:
            return {}

        latest = self.history[-1]

        return {
            "uptime_minutes": len(self.history),
            "final_balance": latest.balance,
            "total_pnl": latest.total_pnl,
            "max_drawdown": latest.max_drawdown_pct,
            "total_trades": latest.total_trades,
            "win_rate": latest.win_rate,
            "alerts_count": len(self.alerts),
        }
