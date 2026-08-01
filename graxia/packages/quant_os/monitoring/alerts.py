"""
Alert manager for Quant OS
Centralized alert routing and management
"""

from dataclasses import dataclass
from datetime import UTC, datetime
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

    def __init__(self, telegram_notifier: Any | None = None):
        self.telegram = telegram_notifier
        if self.telegram is None:
            try:
                from .telegram import TelegramNotifier

                self.telegram = TelegramNotifier()
            except Exception:
                self.telegram = None
        self.alert_history: list = []

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert through all configured channels"""
        self.alert_history.append(alert)

        formatted_text = f"<b>{alert.title}</b>\n{alert.message}"
        if alert.context:
            formatted_text += f"\n<i>Context: {alert.context}</i>"

        # Dispatch via Telegram if configured
        if self.telegram:
            try:
                await self.telegram.send_message(formatted_text, severity=alert.severity)
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Failed to dispatch alert via Telegram: {e}")

        return True

    async def notify_trade(self, symbol: str, action: str, price: float, sl: float, tp: float, lots: float) -> bool:
        """Send trade notification"""
        alert = Alert(
            severity=IncidentSeverity.P2,
            title=f"Trade Executed: {symbol}",
            message=f"{action} {lots} lots @ {price}",
            timestamp=datetime.now(UTC),
            context={"sl": sl, "tp": tp},
        )
        return await self.send_alert(alert)

    async def notify_kill_switch(self, trigger_type: str, reason: str) -> bool:
        """Send kill switch alert"""
        alert = Alert(
            severity=IncidentSeverity.P0,
            title="KILL SWITCH TRIGGERED",
            message=f"{trigger_type}: {reason}",
            timestamp=datetime.now(UTC),
        )
        return await self.send_alert(alert)
