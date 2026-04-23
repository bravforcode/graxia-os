"""
Advanced Health Checker with Predictive Alerting
Enterprise-grade monitoring: trend analysis, predictive alerts, SLA tracking
แก้ปัญหา: รู้ตัวช้าเกินไปหลังระบบล่มแล้ว
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import deque
import statistics


logger = logging.getLogger(__name__)


class HealthTrend(Enum):
    """Health trend directions."""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    FLAPPING = "flapping"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @classmethod
    def from_prediction_time(cls, seconds_to_failure: float) -> "AlertSeverity":
        """Determine severity based on predicted time to failure."""
        if seconds_to_failure < 60:  # < 1 minute
            return cls.CRITICAL
        elif seconds_to_failure < 300:  # < 5 minutes
            return cls.WARNING
        else:
            return cls.INFO


class MetricHistory:
    """Rolling window metric history for trend analysis."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.values: deque = deque(maxlen=window_size)
        self.timestamps: deque = deque(maxlen=window_size)

    def add_metric(self, value: float, timestamp: datetime):
        """Add a metric reading."""
        self.values.append(value)
        self.timestamps.append(timestamp)

    def get_recent_values(self, n: int) -> List[float]:
        """Get last n values."""
        return list(self.values)[-n:]

    def average(self) -> float:
        """Calculate average of all values."""
        if not self.values:
            return 0.0
        return statistics.mean(self.values)

    def std_dev(self) -> float:
        """Calculate standard deviation."""
        if len(self.values) < 2:
            return 0.0
        return statistics.stdev(self.values)


@dataclass
class HealthAlert:
    """Health alert with metadata."""
    service: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    predicted_failure_at: Optional[datetime] = None
    trend: HealthTrend = HealthTrend.UNKNOWN
    metrics: Dict[str, Any] = field(default_factory=dict)


class AdvancedHealthChecker:
    """
    Enterprise-grade health checker with predictive capabilities.

    Features:
    - Trend analysis (improving/stable/degrading/flapping)
    - Predictive failure detection
    - Correlated failure detection
    - SLA monitoring
    - Alert deduplication
    """

    # Thresholds
    TREND_WINDOW_SIZE = 10
    DEGRADATION_THRESHOLD = 0.20  # 20% increase = degrading
    FLAPPING_THRESHOLD = 2.0      # Very high variance = flapping (only extreme cases)
    PREDICTION_THRESHOLD = 600    # Predict failure within 10 minutes

    # Alert cooldown (prevent spam)
    alert_cooldown_seconds: int = 300  # 5 minutes

    def __init__(self):
        self.metric_history: Dict[str, Dict[str, MetricHistory]] = {}
        self.last_alert_time: Dict[str, datetime] = {}
        self.last_alert_severity: Dict[str, AlertSeverity] = {}
        self._lock = asyncio.Lock()

    def _get_or_create_metric_history(self, service: str, metric_name: str) -> MetricHistory:
        """Get or create metric history for a service."""
        if service not in self.metric_history:
            self.metric_history[service] = {}

        if metric_name not in self.metric_history[service]:
            self.metric_history[service][metric_name] = MetricHistory(
                window_size=self.TREND_WINDOW_SIZE
            )

        return self.metric_history[service][metric_name]

    def _calculate_trend(self, values: List[float]) -> HealthTrend:
        """
        Calculate trend from value series.

        Returns:
            HealthTrend: IMPROVING, STABLE, DEGRADING, or FLAPPING
        """
        if len(values) < 3:
            return HealthTrend.UNKNOWN

        # Calculate variance to detect flapping
        try:
            variance = statistics.variance(values)
            mean_val = statistics.mean(values)
            cv = (variance ** 0.5) / mean_val if mean_val > 0 else 0  # Coefficient of variation

            if cv > self.FLAPPING_THRESHOLD:
                return HealthTrend.FLAPPING
        except statistics.StatisticsError:
            pass

        # Calculate slope using simple linear regression
        n = len(values)
        x = list(range(n))

        try:
            # Slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
            sum_x = sum(x)
            sum_y = sum(values)
            sum_xy = sum(x[i] * values[i] for i in range(n))
            sum_x2 = sum(xi * xi for xi in x)

            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

            # Normalize slope relative to average
            avg = sum_y / n if n > 0 else 1
            normalized_slope = slope / avg if avg > 0 else 0

            if normalized_slope > self.DEGRADATION_THRESHOLD:
                return HealthTrend.DEGRADING
            elif normalized_slope < -self.DEGRADATION_THRESHOLD:
                return HealthTrend.IMPROVING
            else:
                return HealthTrend.STABLE

        except ZeroDivisionError:
            return HealthTrend.UNKNOWN

    def _predict_failure_time(
        self,
        values: List[float],
        threshold: float,
        check_interval_seconds: float = 60.0
    ) -> Optional[float]:
        """
        Predict time until value exceeds threshold.

        Args:
            values: Historical values (most recent last)
            threshold: Failure threshold
            check_interval_seconds: Seconds between readings

        Returns:
            Seconds until predicted failure, or None if not predicted
        """
        if len(values) < 3:
            return None

        trend = self._calculate_trend(values)

        # Only predict for degrading trends
        if trend != HealthTrend.DEGRADING:
            return None

        # Calculate rate of increase
        recent = values[-5:]  # Last 5 readings
        if len(recent) < 2:
            return None

        rate_of_increase = (recent[-1] - recent[0]) / (len(recent) - 1)

        if rate_of_increase <= 0:
            return None

        current_value = values[-1]
        remaining = threshold - current_value

        if remaining <= 0:
            return 0  # Already at threshold

        # Predict readings until failure
        readings_until_failure = remaining / rate_of_increase
        seconds_until_failure = readings_until_failure * check_interval_seconds

        return seconds_until_failure

    async def check_service_health(
        self,
        service_name: str,
        metrics: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """
        Check service health and generate predictive alerts.

        Args:
            service_name: Name of service
            metrics: Dict of metric name -> list of values

        Returns:
            Health status dict with predictions
        """
        async with self._lock:
            results = {
                "service": service_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": {},
                "trends": {},
                "predictions": {},
                "alerts": []
            }

            for metric_name, values in metrics.items():
                # Update history
                history = self._get_or_create_metric_history(service_name, metric_name)
                for val in values:
                    history.add_metric(val, datetime.now(timezone.utc))

                # Calculate trend
                recent = history.get_recent_values(self.TREND_WINDOW_SIZE)
                trend = self._calculate_trend(recent)
                results["trends"][metric_name] = trend.value

                # Predict failure for key metrics
                if metric_name in ["latency_ms", "error_rate", "cpu_percent"]:
                    threshold = self._get_threshold_for_metric(metric_name)
                    prediction = self._predict_failure_time(recent, threshold)

                    if prediction is not None and prediction < self.PREDICTION_THRESHOLD:
                        severity = AlertSeverity.from_prediction_time(prediction)
                        predicted_time = datetime.now(timezone.utc) + timedelta(seconds=prediction)

                        alert_msg = (
                            f"🔮 Predictive Alert: {service_name} {metric_name} "
                            f"will breach threshold in {prediction:.0f}s "
                            f"(predicted at {predicted_time.strftime('%H:%M:%S')})"
                        )

                        await self._send_alert(service_name, severity, alert_msg)

                        results["predictions"][metric_name] = {
                            "seconds_until_failure": prediction,
                            "predicted_at": predicted_time.isoformat(),
                            "severity": severity.value
                        }
                        results["alerts"].append(alert_msg)

                results["metrics"][metric_name] = {
                    "current": values[-1] if values else None,
                    "average": history.average(),
                    "std_dev": history.std_dev()
                }

            return results

    def _get_threshold_for_metric(self, metric_name: str) -> float:
        """Get failure threshold for a metric."""
        thresholds = {
            "latency_ms": 1000.0,      # 1 second
            "error_rate": 0.1,         # 10%
            "cpu_percent": 90.0,       # 90% CPU
            "memory_percent": 85.0,    # 85% memory
        }
        return thresholds.get(metric_name, 100.0)

    async def _send_alert(self, service: str, severity: AlertSeverity, message: str):
        """
        Send alert with deduplication and escalation handling.
        """
        now = datetime.now(timezone.utc)
        alert_key = f"{service}:{message}"

        # Check cooldown
        if alert_key in self.last_alert_time:
            last_time = self.last_alert_time[alert_key]
            last_severity = self.last_alert_severity.get(alert_key)

            cooldown = timedelta(seconds=self.alert_cooldown_seconds)

            # Allow if: cooldown expired OR severity escalated
            if now - last_time < cooldown:
                if severity.value == last_severity.value:
                    logger.debug(f"Alert suppressed (cooldown): {message}")
                    return
                elif severity.value < last_severity.value:  # Lower severity
                    logger.debug(f"Alert suppressed (lower severity): {message}")
                    return

        # Send alert
        await self._send_telegram_alert(service, severity, message)

        # Update tracking
        self.last_alert_time[alert_key] = now
        self.last_alert_severity[alert_key] = severity

    async def _send_telegram_alert(self, service: str, severity: AlertSeverity, message: str):
        """Send alert via Telegram."""
        try:
            from app.telegram_bot.bot import send_message

            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity.value, "⚠️")
            formatted = f"{emoji} [{severity.value.upper()}] {message}"

            await send_message(formatted, parse_mode=None)
            logger.info(f"Alert sent: {formatted}")

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def detect_correlated_failures(
        self,
        service_histories: Dict[str, Dict[str, List[float]]]
    ) -> Optional[str]:
        """
        Detect when multiple services are failing simultaneously.

        Returns:
            Alert message if correlated failure detected, None otherwise
        """
        degrading_services = []

        for service_name, metrics in service_histories.items():
            for metric_name, values in metrics.items():
                if len(values) >= 3:
                    trend = self._calculate_trend(values)
                    if trend == HealthTrend.DEGRADING:
                        degrading_services.append(service_name)
                        break

        if len(degrading_services) >= 3:
            message = (
                f"🚨 Correlated Failure Detected: "
                f"{', '.join(degrading_services)} are degrading simultaneously. "
                f"Check infrastructure (network, database, external APIs)."
            )
            await self._send_alert(
                "system",
                AlertSeverity.CRITICAL,
                message
            )
            return message

        return None

    def _check_sla_breach(
        self,
        service: str,
        error_rates: List[float],
        max_error_rate: float = 0.001  # 99.9% SLA
    ) -> bool:
        """
        Check if service is breaching SLA.

        Returns:
            True if SLA breach detected
        """
        if not error_rates:
            return False

        # Check if recent error rate exceeds SLA
        recent_avg = statistics.mean(error_rates[-5:]) if len(error_rates) >= 5 else error_rates[-1]

        if recent_avg > max_error_rate:
            logger.warning(
                f"SLA breach detected for {service}: "
                f"error_rate={recent_avg:.4f} > {max_error_rate:.4f}"
            )
            return True

        return False

    async def run_full_health_check(self, services: List[str]) -> Dict[str, Any]:
        """
        Run comprehensive health check on all services.

        Returns:
            Full health report
        """
        results = {}

        for service in services:
            # Get current metrics (this would be implemented per service)
            metrics = await self._get_service_metrics(service)

            health = await self.check_service_health(service, metrics)
            results[service] = health

        # Check for correlated failures
        service_histories = {
            s: r["metrics"] for s, r in results.items()
            if "metrics" in r
        }
        await self.detect_correlated_failures(service_histories)

        return results

    async def _get_service_metrics(self, service: str) -> Dict[str, List[float]]:
        """
        Get metrics for a service. Override in subclass or implement per service.
        """
        # This is a placeholder - real implementation would query actual metrics
        return {
            "latency_ms": [100, 110, 105, 115, 108],
            "error_rate": [0.001, 0.002, 0.001, 0.003, 0.002]
        }

    async def generate_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive health report."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "services": {},
            "system_wide": {
                "total_services": len(self.metric_history),
                "degrading_services": [],
                "flapping_services": []
            }
        }

        for service_name, metrics in self.metric_history.items():
            service_report = {
                "metrics": {},
                "overall_trend": HealthTrend.STABLE.value
            }

            for metric_name, history in metrics.items():
                recent = history.get_recent_values(self.TREND_WINDOW_SIZE)
                trend = self._calculate_trend(recent)

                service_report["metrics"][metric_name] = {
                    "trend": trend.value,
                    "current": list(history.values)[-1] if history.values else None,
                    "average": history.average()
                }

                if trend == HealthTrend.DEGRADING:
                    report["system_wide"]["degrading_services"].append(service_name)
                elif trend == HealthTrend.FLAPPING:
                    report["system_wide"]["flapping_services"].append(service_name)

            report["services"][service_name] = service_report

        return report


# Convenience function for quick predictive alert
def predictive_alert(
    service: str,
    metric: str,
    values: List[float],
    threshold: float
) -> Optional[Dict[str, Any]]:
    """
    Quick predictive alert check.

    Returns:
        Alert dict if failure predicted, None otherwise
    """
    checker = AdvancedHealthChecker()
    prediction = checker._predict_failure_time(values, threshold)

    if prediction is not None and prediction < checker.PREDICTION_THRESHOLD:
        severity = AlertSeverity.from_prediction_time(prediction)
        return {
            "service": service,
            "metric": metric,
            "predicted_failure_in_seconds": prediction,
            "severity": severity.value,
            "current_value": values[-1] if values else None,
            "threshold": threshold
        }

    return None


# Global instance
health_checker = AdvancedHealthChecker()
