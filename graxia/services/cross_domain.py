"""
Graxia OS — Cross-Domain Service Layer
Revenue events trigger trading actions
Trading P&L affects revenue tracking
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RevenueEvent:
    event_type: str  # "order_completed", "refund", "chargeback"
    amount: Decimal
    customer_id: str
    product_id: str
    timestamp: datetime
    metadata: Dict[str, Any]


@dataclass
class TradingSignal:
    symbol: str
    action: str  # "buy", "sell"
    confidence: float
    strategy: str
    trigger_source: str


class CrossDomainOrchestrator:
    """
    Orchestrates actions between Revenue OS and Quant OS
    """
    
    def __init__(self):
        self.revenue_threshold_high = Decimal("1000.00")
        self.revenue_threshold_low = Decimal("100.00")
        self.pnl_threshold_for_alert = Decimal("-500.00")
    
    # ── Revenue → Trading ──
    
    def on_revenue_event(self, event: RevenueEvent) -> Optional[TradingSignal]:
        """
        Process revenue event and potentially generate trading signal
        
        Examples:
        - High revenue → Increase trading position size
        - Low revenue → Reduce risk
        - Chargeback → Alert trading team
        """
        if event.amount >= self.revenue_threshold_high:
            return TradingSignal(
                symbol="EURUSD",
                action="notify",
                confidence=0.8,
                strategy="revenue_correlation",
                trigger_source=f"high_revenue:{event.amount}"
            )
        
        if event.amount <= -self.revenue_threshold_low:
            return TradingSignal(
                symbol="EURUSD",
                action="risk_reduction",
                confidence=0.6,
                strategy="revenue_protection",
                trigger_source=f"revenue_loss:{event.amount}"
            )
        
        return None
    
    # ── Trading → Revenue ──
    
    def on_trading_pnl(self, pnl: Decimal, date: datetime) -> Dict[str, Any]:
        """
        Process trading P&L and update revenue tracking
        
        Trading profits/losses are recorded as revenue entries
        """
        entry_type = "trading_profit" if pnl > 0 else "trading_loss"
        
        return {
            "entry_type": entry_type,
            "amount": abs(pnl),
            "date": date.isoformat(),
            "category": "trading",
            "description": f"Trading {entry_type}: ${pnl}",
        }
    
    # ── Health Correlation ──
    
    def check_cross_domain_health(self, 
                                   revenue_healthy: bool, 
                                   trading_healthy: bool) -> Dict[str, Any]:
        """
        Check health across both domains
        """
        if not revenue_healthy and not trading_healthy:
            return {
                "status": "critical",
                "action": "notify_admin",
                "reason": "Both domains degraded"
            }
        
        if not revenue_healthy:
            return {
                "status": "degraded",
                "action": "continue_trading",
                "reason": "Revenue issues but trading OK"
            }
        
        if not trading_healthy:
            return {
                "status": "degraded",
                "action": "monitor_only",
                "reason": "Trading issues, revenue continues"
            }
        
        return {
            "status": "healthy",
            "action": "none",
        }
    
    # ── Unified Dashboard Data ──
    
    def get_unified_dashboard(self) -> Dict[str, Any]:
        """
        Get combined data for unified dashboard
        """
        today = datetime.utcnow().date()
        
        return {
            "date": today.isoformat(),
            "revenue": {
                "today": 0,
                "mtd": 0,
                "active_orders": 0,
            },
            "trading": {
                "mode": "PAPER",
                "open_positions": 0,
                "today_pnl": 0,
                "kill_switch": "ARMED",
            },
            "system": {
                "status": "operational",
                "last_update": datetime.utcnow().isoformat(),
            }
        }


class UnifiedNotifier:
    """
    Unified notification system for both domains
    """
    
    def __init__(self):
        self.telegram = None
        self.enabled = True
    
    async def notify_revenue_and_trading(self, 
                                          revenue_msg: str, 
                                          trading_msg: str):
        """Send combined notification"""
        from graxia.packages.quant_os.monitoring.telegram import TelegramNotifier
        
        notifier = TelegramNotifier()
        if notifier.bot_token:
            message = f"""
📊 <b>Graxia OS Update</b>

<b>Revenue:</b>
{revenue_msg}

<b>Trading:</b>
{trading_msg}
"""
            await notifier.send_custom_message("Unified Update", message)
    
    async def alert_critical(self, message: str):
        """Critical alert to both systems"""
        # Would send to all channels: Telegram, Email, PagerDuty
        pass
