"""
Portfolio Risk Management

Tracks overall portfolio exposure and correlations.
"""

from typing import Dict, List, Optional
from decimal import Decimal
from dataclasses import dataclass, field
import math

from .engine import PortfolioState


@dataclass
class PositionExposure:
    """Exposure for a single position"""
    symbol: str
    direction: str  # LONG or SHORT
    quantity: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    risk_pct: float
    returns: List[float] = field(default_factory=list)


@dataclass
class PortfolioMetrics:
    """Portfolio-level risk metrics"""
    total_exposure: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    concentration_pct: float
    correlation_risk: float
    beta_adjusted_exposure: float
    var_95: Optional[Decimal] = None
    cvar_95: Optional[Decimal] = None


class PortfolioRisk:
    """
    Portfolio Risk Manager
    
    Monitors:
    - Total exposure
    - Correlation risk
    - Concentration limits
    - Beta-adjusted exposure
    """
    
    def __init__(self, max_exposure_pct: float = 50.0):
        self.max_exposure_pct = max_exposure_pct
        self.positions: Dict[str, PositionExposure] = {}
        self.account_balance: Decimal = Decimal("10000")
        
    def update_position(self, exposure: PositionExposure) -> None:
        """Update or add a position"""
        self.positions[exposure.symbol] = exposure
    
    def remove_position(self, symbol: str) -> None:
        """Remove a position"""
        if symbol in self.positions:
            del self.positions[symbol]
    
    def calculate_metrics(self) -> PortfolioMetrics:
        """Calculate portfolio risk metrics"""
        long_exposure = sum(
            p.market_value for p in self.positions.values()
            if p.direction == "LONG"
        )
        
        short_exposure = sum(
            p.market_value for p in self.positions.values()
            if p.direction == "SHORT"
        )
        
        gross = long_exposure + short_exposure
        net = long_exposure - short_exposure
        
        total = abs(net)
        concentration = 0.0
        if total > 0 and self.positions:
            max_position = max(abs(p.market_value) for p in self.positions.values())
            concentration = float(max_position / total * 100)
        
        corr_risk = self._compute_correlation_risk()
        var_95, cvar_95 = self._compute_var()
        
        return PortfolioMetrics(
            total_exposure=total,
            net_exposure=net,
            gross_exposure=gross,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            concentration_pct=concentration,
            correlation_risk=corr_risk,
            beta_adjusted_exposure=0.0,
            var_95=var_95,
            cvar_95=cvar_95,
        )
    
    def check_exposure_limit(self) -> bool:
        """Check if exposure is within limits"""
        metrics = self.calculate_metrics()
        if self.account_balance == 0:
            return True
        
        exposure_pct = float(metrics.total_exposure / self.account_balance * 100)
        return exposure_pct <= self.max_exposure_pct

    def to_portfolio_state(self) -> PortfolioState:
        """Convert PortfolioRisk metrics to engine PortfolioState format."""
        metrics = self.calculate_metrics()
        balance = float(self.account_balance) if self.account_balance else 1.0

        total_exposure_pct = float(metrics.total_exposure) / balance if balance else 0.0

        class_exposure_pct: Dict[str, float] = {}
        venue_exposure_pct: Dict[str, float] = {}
        for pos in self.positions.values():
            pos_pct = float(pos.market_value) / balance if balance else 0.0
            class_exposure_pct[pos.symbol] = class_exposure_pct.get(pos.symbol, 0.0) + pos_pct
            venue_exposure_pct[pos.symbol] = venue_exposure_pct.get(pos.symbol, 0.0) + pos_pct

        position_symbols = list(self.positions.keys())

        correlation_matrix = self.get_correlation_matrix(position_symbols) if len(position_symbols) > 1 else None

        return PortfolioState(
            total_exposure_pct=total_exposure_pct,
            class_exposure_pct=class_exposure_pct,
            venue_exposure_pct=venue_exposure_pct,
            position_symbols=position_symbols,
            correlation_matrix=correlation_matrix,
        )
    
    def get_correlation_matrix(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """Compute correlation matrix from position returns."""
        n = len(symbols)
        if n == 0:
            return {}
        if n == 1:
            return {symbols[0]: {symbols[0]: 1.0}}

        matrix: Dict[str, Dict[str, float]] = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                elif s2 in matrix and s1 in matrix[s2]:
                    matrix[s1][s2] = matrix[s2][s1]
                else:
                    r1 = self.positions.get(s1)
                    r2 = self.positions.get(s2)
                    rets1 = r1.returns if r1 and r1.returns else []
                    rets2 = r2.returns if r2 and r2.returns else []
                    matrix[s1][s2] = self._pearson_correlation(rets1, rets2)
        return matrix
    
    def estimate_var(self, confidence: float = 0.95) -> Optional[Decimal]:
        """Estimate Value at Risk using historical simulation."""
        all_returns = []
        for pos in self.positions.values():
            if pos.returns:
                weight = float(pos.market_value) / float(self.account_balance) if self.account_balance else 0
                all_returns.extend([r * weight for r in pos.returns])
        if not all_returns:
            return None
        all_returns.sort()
        idx = int((1 - confidence) * len(all_returns))
        idx = max(0, min(idx, len(all_returns) - 1))
        return Decimal(str(-all_returns[idx]))
    
    def _compute_var(self):
        """Compute VaR and CVaR from position returns."""
        all_returns = []
        for pos in self.positions.values():
            if pos.returns:
                weight = float(pos.market_value) / float(self.account_balance) if self.account_balance else 0
                all_returns.extend([r * weight for r in pos.returns])
        if not all_returns:
            return None, None
        all_returns.sort()
        n = len(all_returns)
        idx_95 = max(0, int(0.05 * n))
        var_95 = Decimal(str(-all_returns[idx_95]))
        tail = all_returns[:idx_95 + 1]
        cvar_95 = Decimal(str(-sum(tail) / len(tail))) if tail else var_95
        return var_95, cvar_95
    
    def _compute_correlation_risk(self) -> float:
        """Compute average pairwise correlation as a risk metric."""
        symbols = [s for s, p in self.positions.items() if p.returns]
        if len(symbols) < 2:
            return 0.0
        matrix = self.get_correlation_matrix(symbols)
        total_corr = 0.0
        count = 0
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                total_corr += abs(matrix.get(s1, {}).get(s2, 0.0))
                count += 1
        return total_corr / count if count > 0 else 0.0
    
    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> float:
        """Compute Pearson correlation coefficient."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        x, y = x[:n], y[:n]
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (std_x * std_y)
