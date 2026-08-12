"""
QuantOS Alerting Rules Engine.

Monitors system state and triggers alerts for:
  - Drawdown exceeding threshold
  - Kill switch activation
  - Model prediction drift
  - Position count / notional limit breaches
  - Daily loss limit reached

Integrates with Telegram for real-time notifications.
Uses structlog for structured logging and dataclasses for alert state.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import httpx
import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Supported alert types."""
    DRAWDOWN = "drawdown"
    KILL_SWITCH = "kill_switch"
    MODEL_DRIFT = "model_drift"
    POSITION_LIMIT = "position_limit"
    DAILY_LOSS = "daily_loss"


@dataclass(frozen=True)
class AlertRule:
    """Configuration for a single alert rule."""
    alert_type: AlertType
    severity: AlertSeverity
    threshold: float
    message_template: str
    enabled: bool = True
    cooldown_seconds: float = 300.0

    def format_message(self, **kwargs: Any) -> str:
        """Render the message template with provided values."""
        return self.message_template.format(**kwargs)


@dataclass
class Alert:
    """A triggered alert instance."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize alert to a dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
        }


@dataclass
class TelegramConfig:
    """Telegram notification configuration."""
    bot_token: str
    chat_id: str
    enabled: bool = True
    parse_mode: str = "HTML"
    base_url: str = "https://api.telegram.org"


class AlertEngine:
    """
    Alert rules engine that monitors system state and triggers notifications.

    Usage:
        engine = AlertEngine(
            rules=[...],
            telegram_config=TelegramConfig(bot_token="...", chat_id="..."),
        )

        # Periodically
        engine.check_alerts(system_state={...})

        # Query history
        history = engine.get_alert_history(limit=50)
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        telegram_config: TelegramConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._rules = rules or self._default_rules()
        self._telegram = telegram_config
        self._http = http_client or httpx.Client(timeout=10.0)
        self._alert_history: list[Alert] = []
        self._last_fired: dict[AlertType, float] = {}
        self._callbacks: list[Callable[[Alert], None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_alerts(self, system_state: dict[str, Any]) -> list[Alert]:
        """
        Evaluate all enabled rules against the current system state.

        Args:
            system_state: Dictionary containing live metrics. Expected keys
                depend on the alert type:
                  drawdown:     {"drawdown_pct": float, "account": str}
                  kill_switch:  {"kill_switch_active": bool, "account": str}
                  model_drift:  {"drift_score": float, "threshold": float, "account": str}
                  position_limit: {"open_positions": int, "max_positions": int, "account": str}
                  daily_loss:   {"daily_pnl": float, "daily_loss_limit": float, "account": str}

        Returns:
            List of alerts that were triggered in this cycle.
        """
        triggered: list[Alert] = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            if self._in_cooldown(rule):
                continue

            alert = self._evaluate_rule(rule, system_state)
            if alert is not None:
                triggered.append(alert)
                self._alert_history.append(alert)
                self._last_fired[rule.alert_type] = time.time()
                self._notify(alert)
                logger.warning(
                    "alert_triggered",
                    alert_type=rule.alert_type.value,
                    severity=rule.severity.value,
                    message=alert.message,
                )

        return triggered

    def send_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """
        Manually send an alert (bypasses rule evaluation).

        Useful for one-off alerts like scheduled maintenance or manual kill.
        """
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._alert_history.append(alert)
        self._notify(alert)
        logger.info(
            "alert_sent_manual",
            alert_type=alert_type.value,
            severity=severity.value,
            message=message,
        )
        return alert

    def get_alert_history(
        self,
        limit: int = 50,
        alert_type: AlertType | None = None,
        severity: AlertSeverity | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent alert history.

        Args:
            limit: Maximum number of alerts to return.
            filter_by_type: Optional filter by alert type.
            filter_by_severity: Optional filter by severity.

        Returns:
            List of alert dictionaries, most recent first.
        """
        results = self._alert_history

        if alert_type is not None:
            results = [a for a in results if a.alert_type == alert_type]
        if severity is not None:
            results = [a for a in results if a.severity == severity]

        return [a.to_dict() for a in reversed(results[-limit:])]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert by ID. Returns True if found."""
        for alert in reversed(self._alert_history):
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                logger.info("alert_acknowledged", alert_id=alert_id)
                return True
        return False

    def register_callback(self, callback: Callable[[Alert], None]) -> None:
        """Register a callback to be invoked whenever an alert fires."""
        self._callbacks.append(callback)

    @property
    def active_alert_count(self) -> int:
        """Count of unacknowledged alerts."""
        return sum(1 for a in self._alert_history if not a.acknowledged)

    def clear_history(self) -> int:
        """Clear all alert history. Returns count of cleared alerts."""
        count = len(self._alert_history)
        self._alert_history.clear()
        self._last_fired.clear()
        logger.info("alert_history_cleared", count=count)
        return count

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self, rule: AlertRule, state: dict[str, Any]
    ) -> Alert | None:
        """Evaluate a single rule against system state."""
        evaluators: dict[AlertType, Callable[..., bool]] = {
            AlertType.DRAWDOWN: self._check_drawdown,
            AlertType.KILL_SWITCH: self._check_kill_switch,
            AlertType.MODEL_DRIFT: self._check_model_drift,
            AlertType.POSITION_LIMIT: self._check_position_limit,
            AlertType.DAILY_LOSS: self._check_daily_loss,
        }

        evaluator = evaluators.get(rule.alert_type)
        if evaluator is None:
            logger.error("unknown_alert_type", alert_type=rule.alert_type.value)
            return None

        try:
            fired, kwargs = evaluator(rule, state)
        except (KeyError, TypeError) as exc:
            logger.error(
                "alert_evaluation_error",
                alert_type=rule.alert_type.value,
                error=str(exc),
            )
            return None

        if not fired:
            return None

        return Alert(
            alert_id=str(uuid.uuid4()),
            alert_type=rule.alert_type,
            severity=rule.severity,
            message=rule.format_message(**kwargs),
            timestamp=time.time(),
            metadata=kwargs,
        )

    def _in_cooldown(self, rule: AlertRule) -> bool:
        """Check if a rule is still within its cooldown window."""
        last = self._last_fired.get(rule.alert_type, 0.0)
        return (time.time() - last) < rule.cooldown_seconds

    def _notify(self, alert: Alert) -> None:
        """Send notification via Telegram and invoke callbacks."""
        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception:
                logger.exception("alert_callback_error", alert_id=alert.alert_id)

        if self._telegram is not None and self._telegram.enabled:
            self._send_telegram(alert)

    def _send_telegram(self, alert: Alert) -> None:
        """Dispatch an alert message to Telegram."""
        severity_emoji = {
            AlertSeverity.INFO: "\U0001f4a1",
            AlertSeverity.WARNING: "\u26a0\ufe0f",
            AlertSeverity.CRITICAL: "\U0001f6a8",
        }
        emoji = severity_emoji.get(alert.severity, "")

        text = (
            f"{emoji} <b>QuantOS Alert</b>\n\n"
            f"<b>Type:</b> {alert.alert_type.value}\n"
            f"<b>Severity:</b> {alert.severity.value}\n"
            f"<b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(alert.timestamp))} UTC\n\n"
            f"{alert.message}"
        )

        url = f"{self._telegram.base_url}/bot{self._telegram.bot_token}/sendMessage"
        payload = {
            "chat_id": self._telegram.chat_id,
            "text": text,
            "parse_mode": self._telegram.parse_mode,
        }

        try:
            resp = self._http.post(url, json=payload)
            resp.raise_for_status()
            logger.info(
                "telegram_sent",
                alert_id=alert.alert_id,
                chat_id=self._telegram.chat_id,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "telegram_send_failed",
                alert_id=alert.alert_id,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Rule evaluators — each returns (fired: bool, context: dict)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_drawdown(
        rule: AlertRule, state: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        dd = float(state.get("drawdown_pct", 0.0))
        return dd >= rule.threshold, {
            "current_drawdown": dd,
            "threshold": rule.threshold,
            "account": state.get("account", "unknown"),
        }

    @staticmethod
    def _check_kill_switch(
        rule: AlertRule, state: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        active = bool(state.get("kill_switch_active", False))
        return active, {
            "kill_switch_active": active,
            "account": state.get("account", "unknown"),
        }

    @staticmethod
    def _check_model_drift(
        rule: AlertRule, state: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        drift = float(state.get("drift_score", 0.0))
        threshold = float(state.get("threshold", rule.threshold))
        return drift >= threshold, {
            "drift_score": drift,
            "threshold": threshold,
            "account": state.get("account", "unknown"),
        }

    @staticmethod
    def _check_position_limit(
        rule: AlertRule, state: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        positions = int(state.get("open_positions", 0))
        max_pos = int(state.get("max_positions", rule.threshold))
        return positions >= max_pos, {
            "open_positions": positions,
            "max_positions": max_pos,
            "account": state.get("account", "unknown"),
        }

    @staticmethod
    def _check_daily_loss(
        rule: AlertRule, state: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        daily_pnl = float(state.get("daily_pnl", 0.0))
        limit = float(state.get("daily_loss_limit", rule.threshold))
        return daily_pnl <= -limit, {
            "daily_pnl": daily_pnl,
            "daily_loss_limit": limit,
            "account": state.get("account", "unknown"),
        }

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def _default_rules(cls) -> list[AlertRule]:
        """Return the standard alert rule set."""
        return [
            AlertRule(
                alert_type=AlertType.DRAWDOWN,
                severity=AlertSeverity.CRITICAL,
                threshold=5.0,
                message_template=(
                    "Drawdown of {current_drawdown:.2f}% exceeds {threshold:.1f}% limit "
                    "on account {account}. Review positions immediately."
                ),
                cooldown_seconds=300,
            ),
            AlertRule(
                alert_type=AlertType.KILL_SWITCH,
                severity=AlertSeverity.CRITICAL,
                threshold=1.0,
                message_template=(
                    "Kill switch ACTIVATED on account {account}. "
                    "All trading has been halted."
                ),
                cooldown_seconds=60,
            ),
            AlertRule(
                alert_type=AlertType.MODEL_DRIFT,
                severity=AlertSeverity.WARNING,
                threshold=5.0,
                message_template=(
                    "Model drift score of {drift_score:.2f}% exceeds "
                    "threshold {threshold:.1f}% on account {account}. "
                    "Retrain recommended."
                ),
                cooldown_seconds=600,
            ),
            AlertRule(
                alert_type=AlertType.POSITION_LIMIT,
                severity=AlertSeverity.WARNING,
                threshold=6,
                message_template=(
                    "Position count {open_positions} has reached limit "
                    "{max_positions} on account {account}. "
                    "No new positions allowed."
                ),
                cooldown_seconds=300,
            ),
            AlertRule(
                alert_type=AlertType.DAILY_LOSS,
                severity=AlertSeverity.CRITICAL,
                threshold=500.0,
                message_template=(
                    "Daily loss of ${daily_pnl:.2f} has exceeded "
                    "limit ${daily_loss_limit:.2f} on account {account}. "
                    "Trading halted for the day."
                ),
                cooldown_seconds=600,
            ),
        ]
