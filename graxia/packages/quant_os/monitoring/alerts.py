"""
Alert manager for Quant OS
Centralized alert routing and management
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.enums import IncidentSeverity


@dataclass
class Alert:
    """Alert data structure"""

    severity: IncidentSeverity
    title: str
    message: str
    timestamp: datetime
    context: dict[str, Any] | None = None


class AlertManager:
    """
    Centralized alert manager
    Routes alerts to appropriate channels (Telegram, email, etc.)
    """

    def __init__(self):
        self.telegram = None  # Would be TelegramNotifier instance
        self.alert_history: list = []

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert through all configured channels"""
        self.alert_history.append(alert)

        # Route based on severity
        if alert.severity == IncidentSeverity.P0:
            # Critical - send to all channels immediately
            pass
        elif alert.severity == IncidentSeverity.P1:
            # High - send to primary channels
            pass

        return True

    async def notify_trade(self, symbol: str, action: str, price: float, sl: float, tp: float, lots: float) -> bool:
        """Send trade notification"""
        alert = Alert(
            severity=IncidentSeverity.P2,
            title=f"Trade Executed: {symbol}",
            message=f"{action} {lots} lots @ {price}",
            timestamp=datetime.utcnow(),
            context={"sl": sl, "tp": tp},
        )
        return await self.send_alert(alert)

    async def notify_kill_switch(self, trigger_type: str, reason: str) -> bool:
        """Send kill switch alert"""
        alert = Alert(
            severity=IncidentSeverity.P0,
            title="KILL SWITCH TRIGGERED",
            message=f"{trigger_type}: {reason}",
            timestamp=datetime.utcnow(),
        )
        return await self.send_alert(alert)
