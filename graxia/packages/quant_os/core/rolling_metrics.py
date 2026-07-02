"""Rolling metrics from vectorbt pattern for regime detection"""
from typing import List, Dict, Optional
import math

class RollingMetrics:
    """Compute rolling risk metrics for time series analysis"""

    def __init__(self, returns: List[float]):
        self.returns = returns

    def rolling_sharpe(self, window: int = 20, risk_free: float = 0.0) -> List[Optional[float]]:
        """Rolling Sharpe ratio"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            avg = sum(window_returns) / len(window_returns)
            std = self._std(window_returns)
            if std == 0:
                result.append(0.0)
            else:
                result.append((avg - risk_free / 252) / std * math.sqrt(252))
        return result

    def rolling_sortino(self, window: int = 20, risk_free: float = 0.0) -> List[Optional[float]]:
        """Rolling Sortino ratio (downside deviation only)"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            avg = sum(window_returns) / len(window_returns)
            downside = [r for r in window_returns if r < 0]
            if not downside:
                result.append(float('inf') if avg > 0 else 0.0)
                continue
            downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
            if downside_std == 0:
                result.append(0.0)
            else:
                result.append((avg - risk_free / 252) / downside_std * math.sqrt(252))
        return result

    def rolling_max_drawdown(self, window: int = 20) -> List[Optional[float]]:
        """Rolling maximum drawdown"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            equity = [1.0]
            for r in window_returns:
                equity.append(equity[-1] * (1 + r))
            peak = equity[0]
            max_dd = 0.0
            for e in equity:
                if e > peak:
                    peak = e
                dd = (peak - e) / peak
                if dd > max_dd:
                    max_dd = dd
            result.append(max_dd)
        return result

    def rolling_volatility(self, window: int = 20) -> List[Optional[float]]:
        """Rolling annualized volatility"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            result.append(self._std(window_returns) * math.sqrt(252))
        return result

    def rolling_win_rate(self, window: int = 20) -> List[Optional[float]]:
        """Rolling win rate"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            wins = sum(1 for r in window_returns if r > 0)
            result.append(wins / len(window_returns))
        return result

    def rolling_profit_factor(self, window: int = 20) -> List[Optional[float]]:
        """Rolling profit factor"""
        result = []
        for i in range(len(self.returns)):
            if i < window - 1:
                result.append(None)
                continue
            window_returns = self.returns[i - window + 1:i + 1]
            gross_profit = sum(r for r in window_returns if r > 0)
            gross_loss = abs(sum(r for r in window_returns if r < 0))
            if gross_loss == 0:
                result.append(float('inf') if gross_profit > 0 else 0.0)
            else:
                result.append(gross_profit / gross_loss)
        return result

    @staticmethod
    def _std(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    def to_dict(self, window: int = 20) -> Dict[str, List]:
        """Compute all rolling metrics and return as dict"""
        return {
            "sharpe": self.rolling_sharpe(window),
            "sortino": self.rolling_sortino(window),
            "max_drawdown": self.rolling_max_drawdown(window),
            "volatility": self.rolling_volatility(window),
            "win_rate": self.rolling_win_rate(window),
            "profit_factor": self.rolling_profit_factor(window),
        }
