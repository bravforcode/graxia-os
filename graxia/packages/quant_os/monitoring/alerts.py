"""
Alert manager for Quant OS
Centralized alert routing and management
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..core.enums import IncidentSeverity
from .alerting import AlertEngine, AlertSeverity, AlertType

logger = logging.getLogger(__name__)

# IncidentSeverity (P0-P3) has no direct equivalent in AlertEngine's 3-level
# scale. P0/P1 are both "needs a human soon" -> CRITICAL; P2/P3 map to the
# remaining two levels in order of urgency.
_SEVERITY_MAP: dict[IncidentSeverity, AlertSeverity] = {
    IncidentSeverity.P0: AlertSeverity.CRITICAL,
    IncidentSeverity.P1: AlertSeverity.CRITICAL,
    IncidentSeverity.P2: AlertSeverity.WARNING,
    IncidentSeverity.P3: AlertSeverity.INFO,
}

# Alert.title is free text (no structured alert_type field), so the engine's
# category is inferred by keyword. Anything that doesn't match one of the
# engine's 5 risk-rule categories falls back to AlertType.SYSTEM rather than
# being mislabeled as e.g. a drawdown alert.
_TYPE_KEYWORDS: list[tuple[str, AlertType]] = [
    ("KILL SWITCH", AlertType.KILL_SWITCH),
    ("DRAWDOWN", AlertType.DRAWDOWN),
    ("DRIFT", AlertType.MODEL_DRIFT),
    ("POSITION", AlertType.POSITION_LIMIT),
    ("DAILY LOSS", AlertType.DAILY_LOSS),
]


def _infer_alert_type(title: str) -> AlertType:
    upper = title.upper()
    for keyword, alert_type in _TYPE_KEYWORDS:
        if keyword in upper:
            return alert_type
    return AlertType.SYSTEM


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
    Routes alerts to appropriate channels (Telegram, AlertEngine, etc.)
    """

    def __init__(self, telegram_notifier: Any | None = None, engine: AlertEngine | None = None):
        # No default network client: constructing an AlertManager must never
        # open an outbound connection on its own. Callers that want real
        # Telegram dispatch pass telegram_notifier=TelegramNotifier()
        # explicitly (e.g. the live bot/orchestrator bootstrap). Same for
        # engine — pass an existing AlertEngine to get history/callback
        # routing; without one, alerts are still recorded locally and logged.
        self.telegram = telegram_notifier
        self._engine = engine
        self.alert_history: list = []

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert through all configured channels.

        Returns False only when a configured AlertEngine raises on dispatch
        (so the caller knows the alert may not have reached its history/
        callback/telegram routing). Never returns False just because no
        engine or Telegram is configured — a bare AlertManager still records
        history and logs, so alerts are never silently dropped.
        """
        self.alert_history.append(alert)

        formatted_text = f"<b>{alert.title}</b>\n{alert.message}"
        if alert.context:
            formatted_text += f"\n<i>Context: {alert.context}</i>"

        ok = True

        if self._engine is not None:
            try:
                self._engine.send_alert(
                    alert_type=_infer_alert_type(alert.title),
                    severity=_SEVERITY_MAP[alert.severity],
                    message=formatted_text,
                    metadata=alert.context,
                )
            except Exception as e:
                logger.error(f"Failed to dispatch alert via AlertEngine: {e}")
                ok = False
        elif alert.severity in (IncidentSeverity.P0, IncidentSeverity.P1):
            # No engine configured — make sure high-severity alerts still
            # leave a trace beyond alert_history.
            logger.warning(f"{alert.title}: {alert.message}")

        # Dispatch via Telegram if configured
        if self.telegram:
            try:
                await self.telegram.send_message(formatted_text, severity=alert.severity)
            except Exception as e:
                logger.error(f"Failed to dispatch alert via Telegram: {e}")

        return ok

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
