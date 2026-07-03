"""
AI Signal Validator — LLM-powered second opinion for trading signals.

Uses CascadeRouter (Tier 1-2) to validate signal logic against market context.
Does NOT make trading decisions — only adjusts confidence or flags concerns.

Safety:
    - LLM validation is advisory only (reduce confidence, never hard block)
    - Timeout: configurable (default 5s), deterministic fallback on timeout
    - All validations logged for audit trail
    - Follows Golden Rules: AI_CANNOT_SUBMIT_ORDER = True

Architecture:
    EventBus (SignalEvent) → observe() → _pending list
    act() → async LLM validation → SignalValidationEvent on EventBus

Usage:
    validator = SignalValidatorAgent(bus=bus)
    bus.subscribe(SignalEvent, validator.observe)
    # act() is called by orchestrator after observe
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

import structlog

from ..enums import SignalType
from ..events import Event, SignalEvent, SignalValidationEvent
from .base import Agent
from .llm_router import TIER1_PROVIDERS, get_router

logger = structlog.get_logger(__name__)

# ── Prompt Template ────────────────────────────────────────────────

VALIDATION_PROMPT = """You are a trading signal validator for {symbol}.

Signal Details:
- Direction: {direction}
- Confidence: {confidence:.2f}
- Entry: {entry} | SL: {sl} | TP: {tp}
- R:R Ratio: {rr_ratio:.2f}
- Regime: {regime}
- Strategy: {strategy_source}

Validate this signal. Return ONLY JSON:
{{"valid": true/false, "adjusted_confidence": 0.0-1.0, "reasoning": "brief", "red_flags": ["concern1"]}}

Rules:
- If R:R < 1.0, flag as low reward/risk
- If confidence > 0.85 without strong confluence, suggest reduction
- If regime is CRISIS, reduce confidence significantly
- Never suggest confidence > 0.95 (uncertainty always exists)

Return ONLY valid JSON."""


class SignalValidatorAgent(Agent):
    """
    Async agent that validates trading signals via LLM second opinion.

    Subscribes to SignalEvent, validates each signal through CascadeRouter,
    and emits SignalValidationEvent with adjusted confidence.

    NOTE: This agent is fully implemented and tested, but is **not yet wired
    into the main orchestrator flow** (core/orchestrator.py). It is ready for
    integration when the team decides to enable LLM-based signal validation
    in production.

    Safety: AI_CANNOT_SUBMIT_ORDER = True — this agent only adjusts
    confidence scores, never blocks or submits orders.
    """

    DEFAULT_TIMEOUT: float = 5.0
    MIN_CONFIDENCE: float = 0.1
    MAX_CONFIDENCE: float = 0.95

    def __init__(
        self,
        name: str = "signal_validator",
        timeout: float | None = None,
        min_confidence: float | None = None,
        bus: Any | None = None,
    ) -> None:
        super().__init__(name)
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._min_confidence = min_confidence or self.MIN_CONFIDENCE
        self._bus = bus
        self._pending: list[SignalEvent] = []
        self._last_validations: list[SignalValidationEvent] = []

    # ── Agent interface ────────────────────────────────────────────

    def observe(self, event: Event) -> None:
        """Store incoming SignalEvent for later validation."""
        if not isinstance(event, SignalEvent):
            return
        if event.signal_type in (SignalType.NO_TRADE, None):
            return
        self._pending.append(event)

    async def act(self) -> AsyncGenerator[SignalValidationEvent, None]:
        """
        Validate each pending signal through LLM cascade.

        Each signal is validated independently with timeout protection.
        On timeout or error, the signal passes through unchanged
        (deterministic fallback — never blocks the pipeline).

        Yields SignalValidationEvent for each validated signal.
        Also publishes to EventBus if bus was provided.
        """
        if not self._pending:
            return

        signals = list(self._pending)
        self._pending.clear()
        self._last_validations.clear()

        for signal in signals:
            try:
                validation = await asyncio.wait_for(
                    self._validate_signal(signal),
                    timeout=self._timeout,
                )
                logger.info(
                    "signal_validator.result",
                    signal_id=validation.signal_id,
                    original=validation.original_confidence,
                    adjusted=validation.adjusted_confidence,
                    valid=validation.valid,
                    tier=validation.tier_used,
                    latency_ms=round(validation.latency_ms, 1),
                    red_flags=validation.red_flags,
                )
            except TimeoutError:
                logger.warning(
                    "signal_validator.timeout",
                    symbol=signal.symbol,
                    timeout_s=self._timeout,
                )
                validation = self._fallback_event(signal, "LLM timeout")
            except Exception as exc:
                logger.warning(
                    "signal_validator.error",
                    symbol=signal.symbol,
                    error=str(exc),
                )
                validation = self._fallback_event(signal, f"Error: {exc}")

            self._last_validations.append(validation)
            if self._bus is not None:
                self._bus.publish(validation)
            yield validation

    async def _validate_signal(self, signal: SignalEvent) -> SignalValidationEvent:
        """Validate a single signal through the LLM cascade."""
        start = time.monotonic()

        router = get_router()
        prompt = self._build_prompt(signal)

        raw_response, latency_ms, tier_used = await router._call_llm_chain(TIER1_PROVIDERS, prompt)

        if not raw_response:
            return self._fallback_event(signal, "All LLM providers failed")

        parsed = self._parse_response(raw_response, signal)
        total_ms = (time.monotonic() - start) * 1000

        # Clamp adjusted confidence to safe bounds
        adjusted = parsed["adjusted_confidence"]
        adjusted = max(self._min_confidence, min(self.MAX_CONFIDENCE, adjusted))

        return SignalValidationEvent(
            signal_id=signal.event_id,
            original_confidence=signal.confidence,
            adjusted_confidence=adjusted,
            valid=parsed["valid"],
            reasoning=parsed["reasoning"],
            red_flags=tuple(parsed["red_flags"]),
            tier_used=tier_used.tier if tier_used else 0,
            latency_ms=total_ms,
            source="signal_validator",
            trace_id=signal.trace_id,
        )

    def _build_prompt(self, signal: SignalEvent) -> str:
        """Build the LLM validation prompt from signal data."""
        direction = signal.signal_type.value if isinstance(signal.signal_type, SignalType) else str(signal.signal_type)
        strategy_source = signal.metadata.get("strategy_source", signal.source or "unknown")
        rr = self._compute_rr(signal.entry_price, signal.stop_loss, signal.take_profit)

        return VALIDATION_PROMPT.format(
            symbol=signal.symbol,
            direction=direction,
            confidence=signal.confidence,
            entry=signal.entry_price,
            sl=signal.stop_loss,
            tp=signal.take_profit,
            rr_ratio=rr,
            regime=signal.regime or "UNKNOWN",
            strategy_source=strategy_source,
        )

    def _parse_response(self, raw: str, signal: SignalEvent) -> dict[str, Any]:
        """Parse LLM JSON response with robust fallback."""
        # Strip markdown code blocks if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        # Try direct JSON parse
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try regex extraction
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return self._default_parse(signal)
            else:
                return self._default_parse(signal)

        return {
            "valid": bool(data.get("valid", True)),
            "adjusted_confidence": float(data.get("adjusted_confidence", signal.confidence)),
            "reasoning": str(data.get("reasoning", "")),
            "red_flags": list(data.get("red_flags", [])),
        }

    def _default_parse(self, signal: SignalEvent) -> dict[str, Any]:
        """Fallback when JSON parsing fails entirely."""
        return {
            "valid": True,
            "adjusted_confidence": signal.confidence,
            "reasoning": "LLM response unparseable — passing through",
            "red_flags": ["unparseable_llm_response"],
        }

    def _fallback_event(self, signal: SignalEvent, reason: str) -> SignalValidationEvent:
        """Create a deterministic fallback validation event."""
        return SignalValidationEvent(
            signal_id=signal.event_id,
            original_confidence=signal.confidence,
            adjusted_confidence=signal.confidence,
            valid=True,
            reasoning=reason,
            red_flags=("deterministic_fallback",),
            tier_used=0,
            latency_ms=0.0,
            source="signal_validator",
            trace_id=signal.trace_id,
        )

    @staticmethod
    def _compute_rr(entry: float, sl: float, tp: float) -> float:
        """Calculate risk:reward ratio. Returns 0.0 if invalid inputs."""
        if not entry or not sl or not tp:
            return 0.0
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return 0.0
        return reward / risk

    def reset(self) -> None:
        """Clear accumulated pending signals."""
        super().reset()
        self._pending.clear()
        self._last_validations.clear()
