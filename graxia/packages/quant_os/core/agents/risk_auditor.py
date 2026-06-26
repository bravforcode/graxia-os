"""
RiskAuditorAgent (C1)

Checks incoming SignalEvents against risk rules.
Emits a RiskEvent (pass/fail) and a SignalEvent with adjusted confidence.
"""

from dataclasses import dataclass, field

from ..events import Event, RiskEvent, SignalEvent
from .base import Agent


@dataclass
class RiskCheck:
    """Result of a single risk check."""

    name: str
    passed: bool
    reason: str = ""


@dataclass
class RiskAudit:
    """Aggregated risk audit result."""

    signal: SignalEvent | None
    checks: list[RiskCheck] = field(default_factory=list)
    approved: bool = False
    rejection_reason: str = ""


class RiskAuditorAgent(Agent):
    """
    Rule-based risk auditor.

    Checks:
        1. Confidence >= min_confidence (0.3)
        2. Risk/reward ratio >= 1.5
        3. No duplicate signal in last N observations
        4. Symbol whitelist (optional)
    """

    MIN_CONFIDENCE = 0.3
    MIN_RR_RATIO = 1.5
    MAX_DUPLICATE_SIGNALS = 3

    def __init__(
        self,
        name: str = "risk_auditor",
        allowed_symbols: list[str] | None = None,
    ) -> None:
        super().__init__(name)
        self.allowed_symbols = allowed_symbols
        self._recent_signals: dict[str, int] = {}
        self._last_audit: RiskAudit | None = None

    def observe(self, event: Event) -> None:
        if isinstance(event, SignalEvent):
            self._observations.append(event)

    def _audit_signal(self, event: SignalEvent) -> RiskEvent:
        checks: list[RiskCheck] = []

        # Check 1: confidence
        conf_ok = event.confidence >= self.MIN_CONFIDENCE
        checks.append(
            RiskCheck(
                name="min_confidence",
                passed=conf_ok,
                reason="" if conf_ok else f"confidence {event.confidence:.2f} < {self.MIN_CONFIDENCE}",
            )
        )

        # Check 2: risk/reward
        rr_ok = True
        if event.stop_loss and event.take_profit and event.entry_price:
            risk = abs(event.entry_price - event.stop_loss)
            reward = abs(event.take_profit - event.entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
            rr_ok = rr_ratio >= self.MIN_RR_RATIO
            checks.append(
                RiskCheck(
                    name="risk_reward_ratio",
                    passed=rr_ok,
                    reason="" if rr_ok else f"R:R {rr_ratio:.2f} < {self.MIN_RR_RATIO}",
                )
            )

        # Check 3: duplicate signal flood
        key = f"{event.symbol}:{event.signal_type.value}"
        count = self._recent_signals.get(key, 0)
        dup_ok = count < self.MAX_DUPLICATE_SIGNALS
        self._recent_signals[key] = count + 1
        checks.append(
            RiskCheck(
                name="duplicate_signal_limit",
                passed=dup_ok,
                reason="" if dup_ok else f"duplicate count {count+1} >= {self.MAX_DUPLICATE_SIGNALS}",
            )
        )

        # Check 4: symbol whitelist
        if self.allowed_symbols is not None:
            sym_ok = event.symbol in self.allowed_symbols
            checks.append(
                RiskCheck(
                    name="symbol_whitelist",
                    passed=sym_ok,
                    reason="" if sym_ok else f"{event.symbol} not in whitelist",
                )
            )

        approved = all(c.passed for c in checks)
        rejection = "; ".join(c.reason for c in checks if not c.passed)

        risk_event = RiskEvent(
            check_name="agent_risk_audit",
            passed=approved,
            reason=rejection,
            source=self.name,
            details={"checks": [c.name for c in checks]},
        )

        self._last_audit = RiskAudit(
            signal=event,
            checks=checks,
            approved=approved,
            rejection_reason=rejection,
        )

        return risk_event

    def act(self) -> Event | None:
        if not self._observations:
            return None

        signals = [
            obs for obs in self._observations if isinstance(obs, SignalEvent)
        ]
        self._observations.clear()

        if not signals:
            return None

        result: Event | None = None
        for event in signals:
            result = self._audit_signal(event)

        return result

    def get_last_audit(self) -> RiskAudit | None:
        return self._last_audit

    def reset(self) -> None:
        super().reset()
        self._recent_signals.clear()
        self._last_audit = None
