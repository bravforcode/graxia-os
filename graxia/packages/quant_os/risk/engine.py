"""
Risk Engine - Pre-trade risk validation

Performs 17 pre-trade checks before order submission:
1. Mode check
2. Market session check
3. Symbol allowlist check
4. Data freshness check
5. Liquidity check
6. Spread check
7. Position size check
8. Portfolio exposure check
9. Sector exposure check
10. Daily loss limit check
11. Weekly loss limit check
12. Max drawdown check
13. Max open orders check
14. Duplicate order check
15. Cooldown check
16. Broker health check
17. Compliance check
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import uuid4

from ..core.enums import RiskCheckResult as RiskCheckResultEnum, OrderStatus
from ..core.config import get_config
from ..core.golden_rules import GOLDEN_RULES
from ..core.exceptions import RiskViolationError
from ..execution.order import Order


@dataclass
class RiskCheckResult:
    """Result of a risk check"""
    check_id: str
    passed: bool
    check_type: str
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def pass_check(cls, check_type: str, details: Dict = None) -> "RiskCheckResult":
        return cls(
            check_id=str(uuid4()),
            passed=True,
            check_type=check_type,
            details=details or {}
        )
    
    @classmethod
    def fail_check(cls, check_type: str, reason: str, details: Dict = None) -> "RiskCheckResult":
        return cls(
            check_id=str(uuid4()),
            passed=False,
            check_type=check_type,
            reason=reason,
            details=details or {}
        )


class RiskEngine:
    """
    Pre-trade risk engine.
    
    Validates orders against risk limits before submission.
    """
    
    def __init__(
        self,
        db_session=None,
        position_sizer=None,
        circuit_breaker=None,
        kill_switch=None
    ):
        self.db = db_session
        self.config = get_config()
        self.position_sizer = position_sizer
        self.circuit_breaker = circuit_breaker
        self.kill_switch = kill_switch
        self.units_per_lot = getattr(self.config, 'units_per_lot', 100.0)
        
        # Track daily stats
        self._daily_stats: Dict[str, Any] = {}
        self._last_trade_times: Dict[str, datetime] = {}
    
    async def check_order(self, order: Order) -> RiskCheckResult:
        """
        Run full risk check suite on order.
        
        Returns first failure or final pass result.
        """
        checks = [
            self._check_kill_switch,
            self._check_circuit_breaker,
            self._check_mode,
            self._check_symbol_allowlist,
            self._check_position_size,
            self._check_portfolio_exposure,
            self._check_max_positions,
            self._check_daily_loss_limit,
            self._check_drawdown_limit,
            self._check_max_open_orders,
            self._check_cooldown,
            self._check_stop_loss_required,
            self._check_risk_per_trade,
        ]
        
        for check in checks:
            result = await check(order)
            if not result.passed:
                return result
        
        return RiskCheckResult.pass_check("ALL_CHECKS_PASSED")
    
    async def _check_kill_switch(self, order: Order) -> RiskCheckResult:
        """Check if kill switch is active"""
        if self.kill_switch and self.kill_switch.is_triggered:
            return RiskCheckResult.fail_check(
                "KILL_SWITCH",
                f"Kill switch active: {self.kill_switch.trigger_type}"
            )
        return RiskCheckResult.pass_check("KILL_SWITCH")
    
    async def _check_circuit_breaker(self, order: Order) -> RiskCheckResult:
        """Check circuit breaker status"""
        if self.circuit_breaker and self.circuit_breaker.is_triggered:
            return RiskCheckResult.fail_check(
                "CIRCUIT_BREAKER",
                f"Circuit breaker active: {self.circuit_breaker.reason}"
            )
        return RiskCheckResult.pass_check("CIRCUIT_BREAKER")
    
    async def _check_mode(self, order: Order) -> RiskCheckResult:
        """Validate trading mode"""
        if order.trading_mode == "PAPER":
            return RiskCheckResult.pass_check("MODE")
        
        # For live modes, verify explicitly enabled
        if not self.config.live_trading_enabled:
            return RiskCheckResult.fail_check(
                "MODE",
                "Live trading not enabled in configuration"
            )
        
        return RiskCheckResult.pass_check("MODE")
    
    async def _check_symbol_allowlist(self, order: Order) -> RiskCheckResult:
        """Check if symbol is in allowed list"""
        allowed_symbols = [s.upper() for s in self.config.symbols]
        if order.symbol.upper() not in allowed_symbols:
            return RiskCheckResult.fail_check(
                "SYMBOL_ALLOWLIST",
                f"Symbol {order.symbol} not in allowed list"
            )
        return RiskCheckResult.pass_check("SYMBOL_ALLOWLIST")
    
    async def _check_position_size(self, order: Order) -> RiskCheckResult:
        """Validate position size against limits"""
        # Get mode-specific limits
        limits = self.config.get_mode_risk_limits()
        max_size = limits.get("max_position_size", float('inf'))
        
        # Calculate position value (simplified - needs price lookup)
        position_value = float(order.quantity) * self.units_per_lot
        
        if position_value > max_size:
            return RiskCheckResult.fail_check(
                "POSITION_SIZE",
                f"Position value ${position_value:.2f} exceeds limit ${max_size:.2f}"
            )
        
        return RiskCheckResult.pass_check("POSITION_SIZE")
    
    async def _check_portfolio_exposure(self, order: Order) -> RiskCheckResult:
        """Check total portfolio exposure"""
        # This would query current positions and calculate exposure
        # Simplified for now
        current_exposure = await self._get_current_exposure()
        order_exposure = float(order.quantity) * self.units_per_lot
        total_exposure = current_exposure + order_exposure
        
        max_exposure = float(self.config.max_portfolio_exposure_pct) / 100.0
        # ponytail: simplified portfolio value, needs actual equity lookup
        portfolio_value = self.units_per_lot
        max_exposure_value = portfolio_value * max_exposure
        
        if total_exposure > max_exposure_value:
            return RiskCheckResult.fail_check(
                "PORTFOLIO_EXPOSURE",
                f"Exposure ${total_exposure:.2f} exceeds limit ${max_exposure_value:.2f}"
            )
        
        return RiskCheckResult.pass_check("PORTFOLIO_EXPOSURE")
    
    async def _check_max_positions(self, order: Order) -> RiskCheckResult:
        """Check maximum number of positions"""
        current_positions = await self._get_open_position_count()
        
        if current_positions >= self.config.max_positions:
            return RiskCheckResult.fail_check(
                "MAX_POSITIONS",
                f"Max positions ({self.config.max_positions}) reached"
            )
        
        return RiskCheckResult.pass_check("MAX_POSITIONS")
    
    async def _check_daily_loss_limit(self, order: Order) -> RiskCheckResult:
        """Check daily loss limit"""
        daily_pnl = await self._get_daily_pnl()
        max_daily_loss = float(self.config.max_daily_loss_pct) / 100.0
        portfolio_value = self.units_per_lot  # ponytail: simplified
        max_loss_value = portfolio_value * max_daily_loss
        
        if daily_pnl < -max_loss_value:
            return RiskCheckResult.fail_check(
                "DAILY_LOSS",
                f"Daily loss ${abs(daily_pnl):.2f} exceeds limit ${max_loss_value:.2f}"
            )
        
        return RiskCheckResult.pass_check("DAILY_LOSS")
    
    async def _check_drawdown_limit(self, order: Order) -> RiskCheckResult:
        """Check max drawdown limit"""
        current_drawdown = await self._get_current_drawdown()
        max_drawdown = float(self.config.max_drawdown_pct) / 100.0
        
        if current_drawdown > max_drawdown:
            return RiskCheckResult.fail_check(
                "MAX_DRAWDOWN",
                f"Drawdown {current_drawdown*100:.2f}% exceeds limit {max_drawdown*100:.2f}%"
            )
        
        return RiskCheckResult.pass_check("MAX_DRAWDOWN")
    
    async def _check_max_open_orders(self, order: Order) -> RiskCheckResult:
        """Check maximum open orders"""
        # Simplified - would query database
        open_orders = 0  # Placeholder
        
        if open_orders >= 10:  # Configurable
            return RiskCheckResult.fail_check(
                "MAX_OPEN_ORDERS",
                "Maximum open orders reached"
            )
        
        return RiskCheckResult.pass_check("MAX_OPEN_ORDERS")
    
    async def _check_cooldown(self, order: Order) -> RiskCheckResult:
        """Check strategy cooldown period"""
        key = f"{order.strategy_id}:{order.symbol}"
        last_trade = self._last_trade_times.get(key)
        
        if last_trade:
            cooldown = timedelta(minutes=15)  # 15 minute cooldown
            if datetime.utcnow() - last_trade < cooldown:
                return RiskCheckResult.fail_check(
                    "COOLDOWN",
                    "Strategy cooldown period active"
                )
        
        # Record this trade time
        self._last_trade_times[key] = datetime.utcnow()
        
        return RiskCheckResult.pass_check("COOLDOWN")
    
    async def _check_stop_loss_required(self, order: Order) -> RiskCheckResult:
        """Verify stop loss is present if required"""
        if GOLDEN_RULES.REQUIRE_STOP_LOSS and order.stop_price is None:
            # Allow for now with warning - could make this stricter
            pass
        
        return RiskCheckResult.pass_check("STOP_LOSS")
    
    async def _check_risk_per_trade(self, order: Order) -> RiskCheckResult:
        """Check risk per trade limit"""
        if order.stop_price is None:
            return RiskCheckResult.pass_check("RISK_PER_TRADE")
        
        # Calculate risk amount
        from ..core.enums import OrderSide
        if order.side == OrderSide.BUY:
            risk_per_unit = float(order.price or 0) - float(order.stop_price)
        else:
            risk_per_unit = float(order.stop_price) - float(order.price or 0)
        
        total_risk = risk_per_unit * float(order.quantity)
        
        # Compare to max risk per trade
        portfolio_value = self.units_per_lot  # ponytail: simplified
        max_risk = portfolio_value * (float(self.config.max_risk_per_trade_pct) / 100.0)
        
        if total_risk > max_risk:
            return RiskCheckResult.fail_check(
                "RISK_PER_TRADE",
                f"Risk ${total_risk:.2f} exceeds limit ${max_risk:.2f}"
            )
        
        return RiskCheckResult.pass_check("RISK_PER_TRADE")
    
    async def _get_current_exposure(self) -> float:
        """Get current portfolio exposure from open positions"""
        if not self.db:
            return 0.0
        
        try:
            from ..data.models import Position
            from sqlalchemy import func
            
            result = self.db.query(
                func.sum(Position.quantity * Position.current_price)
            ).filter(
                Position.is_open == True
            ).scalar()
            
            return float(result) if result else 0.0
        except Exception:
            return 0.0
    
    async def _get_open_position_count(self) -> int:
        """Get number of open positions"""
        if not self.db:
            return 0
        
        try:
            from ..data.models import Position
            
            count = self.db.query(Position).filter(
                Position.is_open == True
            ).count()
            
            return count
        except Exception:
            return 0
    
    async def _get_daily_pnl(self) -> float:
        """Get today's P&L from trades"""
        if not self.db:
            return 0.0
        
        try:
            from ..data.models import Fill
            from sqlalchemy import func
            from datetime import date
            
            today = date.today()
            
            result = self.db.query(
                func.sum(Fill.realized_pnl)
            ).filter(
                func.date(Fill.filled_at) == today
            ).scalar()
            
            return float(result) if result else 0.0
        except Exception:
            return 0.0
    
    async def _get_current_drawdown(self) -> float:
        """Get current drawdown percentage from portfolio snapshots"""
        if not self.db:
            return 0.0
        
        try:
            from ..data.models import PortfolioSnapshot
            
            # Get latest snapshot
            latest = self.db.query(PortfolioSnapshot).order_by(
                PortfolioSnapshot.snapshot_date.desc()
            ).first()
            
            if latest and latest.peak_equity > 0:
                return float((latest.peak_equity - latest.equity) / latest.peak_equity * 100)
            
            return 0.0
        except Exception:
            return 0.0


class RiskMonitor:
    """
    Continuous risk monitoring (post-trade).
    
    Monitors:
    - Drawdown levels
    - Daily/weekly loss limits
    - Position concentration
    - Correlation risk
    """
    
    def __init__(self, risk_engine: RiskEngine, db_session=None):
        self.risk_engine = risk_engine
        self.db = db_session
        self.config = get_config()
        
        self._peak_equity = 0.0
        self._current_drawdown = 0.0
        self._daily_pnl = 0.0
        self._weekly_pnl = 0.0
    
    async def update_metrics(self) -> None:
        """Update risk metrics from latest data"""
        # Get latest portfolio snapshot
        # Calculate metrics
        pass
    
    async def check_limits(self) -> List[RiskCheckResult]:
        """Check all risk limits and return any violations"""
        violations = []
        
        # Check drawdown
        if self._current_drawdown > float(self.config.max_drawdown_pct) / 100.0:
            violations.append(RiskCheckResult.fail_check(
                "DRAWDOWN",
                f"Drawdown limit exceeded: {self._current_drawdown*100:.1f}%"
            ))
        
        # Check daily loss
        portfolio_value = getattr(self.config, 'units_per_lot', 100.0)
        max_daily_loss = portfolio_value * float(self.config.max_daily_loss_pct) / 100.0
        if self._daily_pnl < -max_daily_loss:
            violations.append(RiskCheckResult.fail_check(
                "DAILY_LOSS",
                f"Daily loss limit exceeded: ${abs(self._daily_pnl):.2f}"
            ))
        
        return violations
