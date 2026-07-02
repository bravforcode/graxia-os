"""Alerting rules for live monitoring."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    rule_name: str
    severity: Severity
    message: str
    timestamp: float = field(default_factory=time.time)

    def __str__(self):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))
        return f"[{self.severity.value.upper()}] {self.rule_name} @ {ts}: {self.message}"


class HighDrawdownAlert:
    """Triggers when drawdown exceeds threshold."""

    def __init__(self, threshold_pct: float = 5.0):
        self.threshold = threshold_pct
        self.name = "high_drawdown"
        self.severity = Severity.CRITICAL

    def check(self, current_drawdown_pct: float) -> Optional[Alert]:
        if current_drawdown_pct > self.threshold:
            return Alert(
                rule_name=self.name,
                severity=self.severity,
                message=f"Drawdown {current_drawdown_pct:.2f}% exceeds threshold {self.threshold}%",
            )
        return None


class ConsecutiveLossAlert:
    """Triggers after N consecutive losses."""

    def __init__(self, max_losses: int = 5):
        self.max_losses = max_losses
        self.name = "consecutive_losses"
        self.severity = Severity.WARNING
        self._streak = 0

    def update(self, pnl: float):
        if pnl < 0:
            self._streak += 1
        else:
            self._streak = 0

    def check(self, current_drawdown_pct: float = 0.0) -> Optional[Alert]:
        if self._streak >= self.max_losses:
            return Alert(
                rule_name=self.name,
                severity=self.severity,
                message=f"{self._streak} consecutive losses (threshold: {self.max_losses})",
            )
        return None

    @property
    def streak(self) -> int:
        return self._streak


class SpreadWideningAlert:
    """Triggers when spread exceeds normal * multiplier."""

    def __init__(self, normal_spread_pips: float = 1.0, multiplier: float = 3.0):
        self.normal_spread = normal_spread_pips
        self.multiplier = multiplier
        self.name = "spread_widening"
        self.severity = Severity.WARNING
        self.threshold = normal_spread_pips * multiplier

    def check(self, current_spread_pips: float) -> Optional[Alert]:
        if current_spread_pips > self.threshold:
            return Alert(
                rule_name=self.name,
                severity=self.severity,
                message=f"Spread {current_spread_pips:.2f} pips exceeds {self.threshold:.2f} pips ({self.multiplier}x normal)",
            )
        return None


class DataStalenessAlert:
    """Triggers when data is older than threshold seconds."""

    def __init__(self, max_age_seconds: float = 60.0):
        self.max_age = max_age_seconds
        self.name = "data_staleness"
        self.severity = Severity.CRITICAL

    def check(self, data_age_seconds: float) -> Optional[Alert]:
        if data_age_seconds > self.max_age:
            return Alert(
                rule_name=self.name,
                severity=self.severity,
                message=f"Data is {data_age_seconds:.1f}s old (threshold: {self.max_age}s)",
            )
        return None


class AlertEngine:
    """Runs all rules against current state and collects alerts."""

    def __init__(self):
        self._rules: List = []
        self._history: List[Alert] = []

    def add_rule(self, rule):
        self._rules.append(rule)
        return self

    def evaluate(self, **kwargs) -> List[Alert]:
        fired = []
        for rule in self._rules:
            result = None
            name = getattr(rule, "name", "")
            if name == "high_drawdown":
                result = rule.check(kwargs.get("drawdown_pct", 0.0))
            elif name == "consecutive_losses":
                if "pnl" in kwargs:
                    rule.update(kwargs["pnl"])
                result = rule.check()
            elif name == "spread_widening":
                result = rule.check(kwargs.get("spread_pips", 0.0))
            elif name == "data_staleness":
                result = rule.check(kwargs.get("data_age_seconds", 0.0))
            if result is not None:
                fired.append(result)
        self._history.extend(fired)
        return fired

    @property
    def history(self) -> List[Alert]:
        return list(self._history)
