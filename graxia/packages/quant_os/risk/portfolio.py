"""
Portfolio Risk Management

Tracks overall portfolio exposure and correlations.
"""

from typing import Dict, List, Optional
from decimal import Decimal
from dataclasses import dataclass

from ..core.enums import RegimeType


@dataclass
class PositionExposure:
    """Exposure for a single position"""
    symbol: str
    direction: str  # LONG or SHORT
    quantity: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    risk_pct: float


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
        
        return PortfolioMetrics(
            total_exposure=total,
            net_exposure=net,
            gross_exposure=gross,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            concentration_pct=concentration,
            correlation_risk=0.0,  # Would calculate from correlation matrix
            beta_adjusted_exposure=0.0,  # Would calculate from betas
        )
    
    def check_exposure_limit(self) -> bool:
        """Check if exposure is within limits"""
        metrics = self.calculate_metrics()
        if self.account_balance == 0:
            return True
        
        exposure_pct = float(metrics.total_exposure / self.account_balance * 100)
        return exposure_pct <= self.max_exposure_pct
    
    def get_correlation_matrix(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """Get correlation matrix for symbols (placeholder)"""
        # Would calculate from historical returns
        return {s: {s2: 0.5 for s2 in symbols} for s in symbols}
    
    def estimate_var(self, confidence: float = 0.95) -> Optional[Decimal]:
        """Estimate Value at Risk (placeholder)"""
        # Would use historical simulation or parametric VaR
        return None
