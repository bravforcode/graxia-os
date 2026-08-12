"""
RiskAuditorAgent (C1)

Checks incoming SignalEvents against risk rules.
Emits a RiskEvent (pass/fail) with RiskVerdictPayload in details.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from ..canonical.payloads import RiskVerdictPayload, VetoReason
from ..events import Event, RiskEvent, SignalEvent
from .base import Agent

try:
    from ..canonical.macro_regime import RegimeBias, get_macro_regime
except ImportError:
    get_macro_regime = None
    RegimeBias = None


@dataclass
class RiskCheck:
    name: str
    passed: bool
    reason: str = ""


@dataclass
class RiskAudit:
    signal: SignalEvent | None
    checks: list[RiskCheck] = field(default_factory=list)
    approved: bool = False
    rejection_reason: str = ""


class RiskAuditorAgent(Agent):
    MIN_CONFIDENCE = 0.3
    MIN_RR_RATIO = 1.5
    MAX_DUPLICATE_SIGNALS = 3

    def __init__(self, name: str = "risk_auditor", allowed_symbols: list[str] | None = None) -> None:
        super().__init__(name)
        self.allowed_symbols = allowed_symbols
        self._recent_signals: dict[str, int] = {}
        self._last_audit: RiskAudit | None = None

    def observe(self, event: Event) -> None:
        if isinstance(event, SignalEvent):
            self._observations.append(event)

    def _check_macro_lockdown(self) -> RiskCheck:
        if get_macro_regime is None:
            return RiskCheck(name="macro_lockdown", passed=True, reason="cache not available")
        regime = get_macro_regime()
        is_lockdown = regime.bias == RegimeBias.PANIC or regime.regime_label == "CRISIS"
        return RiskCheck(
            name="macro_lockdown",
            passed=not is_lockdown,
            reason="" if not is_lockdown else f"MACRO LOCKDOWN: {regime.regime_label}",
        )

    def _audit_signal(self, event: SignalEvent) -> RiskEvent:
        checks: list[RiskCheck] = []

        conf_ok = event.confidence >= self.MIN_CONFIDENCE
        checks.append(
            RiskCheck(
                name="min_confidence",
                passed=conf_ok,
                reason="" if conf_ok else f"confidence {event.confidence:.2f} < {self.MIN_CONFIDENCE}",
            )
        )

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

        key = f"{event.symbol}:{event.signal_type.value}"
        count = self._recent_signals.get(key, 0)
        dup_ok = count < self.MAX_DUPLICATE_SIGNALS
        checks.append(
            RiskCheck(
                name="duplicate_signal_limit",
                passed=dup_ok,
                reason="" if dup_ok else f"duplicate count {count+1} >= {self.MAX_DUPLICATE_SIGNALS}",
            )
        )

        if self.allowed_symbols is not None:
            sym_ok = event.symbol in self.allowed_symbols
            checks.append(
                RiskCheck(
                    name="symbol_whitelist", passed=sym_ok, reason="" if sym_ok else f"{event.symbol} not in whitelist"
                )
            )

        macro_check = self._check_macro_lockdown()
        checks.append(macro_check)

        approved = all(c.passed for c in checks)
        rejection = "; ".join(c.reason for c in checks if not c.passed)

        # Only count approved signals toward duplicate limit
        if approved:
            self._recent_signals[key] = count + 1

        veto_reason = VetoReason.NONE
        if not approved:
            if any(c.name == "macro_lockdown" and not c.passed for c in checks):
                veto_reason = VetoReason.MACRO_LOCKDOWN
            elif any(c.name == "min_confidence" and not c.passed for c in checks):
                veto_reason = VetoReason.LOW_CONFIDENCE
            elif any(c.name == "risk_reward_ratio" and not c.passed for c in checks):
                veto_reason = VetoReason.POOR_RR_RATIO
            elif any(c.name == "duplicate_signal_limit" and not c.passed for c in checks):
                veto_reason = VetoReason.DUPLICATE_FLOOD
            elif any(c.name == "symbol_whitelist" and not c.passed for c in checks):
                veto_reason = VetoReason.SYMBOL_NOT_WHITELISTED

        verdict = RiskVerdictPayload(
            trace_id=str(uuid4()),
            timestamp=datetime.now(UTC),
            is_approved=approved,
            veto_reason=veto_reason,
            veto_detail=rejection,
            checks_passed=[c.name for c in checks if c.passed],
            checks_failed=[c.name for c in checks if not c.passed],
        )

        risk_event = RiskEvent(
            check_name="agent_risk_audit",
            passed=approved,
            reason=rejection,
            source=self.name,
            details={"checks": [c.name for c in checks], "risk_verdict": verdict},
        )

        self._last_audit = RiskAudit(signal=event, checks=checks, approved=approved, rejection_reason=rejection)
        return risk_event

    def act(self) -> Event | None:
        if not self._observations:
            return None
        signals = [obs for obs in self._observations if isinstance(obs, SignalEvent)]
        self._observations.clear()
        if not signals:
            return None
        # Process all signals, return last result.
        # This is by design: the event bus delivers each signal individually,
        # so PortfolioManager sees each RiskEvent as it's published.
        # The return value is for synchronous callers only.
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
