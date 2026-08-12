"""
Tests for AI Signal Validator Agent (core/agents/signal_validator.py).

Covers:
- observe() signal filtering
- act() async validation with LLM
- Timeout and error fallbacks
- Prompt building and response parsing
- R:R computation
- Confidence clamping
- Reset behavior
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.core.agents.signal_validator import (
    SignalValidatorAgent,
)
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.events import (
    BarEvent,
    SignalEvent,
    SignalValidationEvent,
)

# Resolve the module object for patch.object (avoids dotted-path resolution issues)
_sv_mod = sys.modules["graxia.packages.quant_os.core.agents.signal_validator"]


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def validator() -> SignalValidatorAgent:
    """Create a fresh SignalValidatorAgent."""
    return SignalValidatorAgent(timeout=2.0)


@pytest.fixture
def buy_signal() -> SignalEvent:
    """Create a BUY signal event."""
    return SignalEvent(
        symbol="XAUUSD",
        signal_type=SignalType.BUY,
        confidence=0.75,
        entry_price=2345.50,
        stop_loss=2340.00,
        take_profit=2355.00,
        regime="TREND_UP",
        source="technical_analyst",
        metadata={"strategy_source": "mtm"},
    )


@pytest.fixture
def sell_signal() -> SignalEvent:
    """Create a SELL signal event."""
    return SignalEvent(
        symbol="EURUSD",
        signal_type=SignalType.SELL,
        confidence=0.60,
        entry_price=1.0850,
        stop_loss=1.0900,
        take_profit=1.0750,
        regime="RANGE_BOUND",
        source="analyst",
    )


def _make_validation_response(
    valid: bool = True,
    adjusted_confidence: float = 0.70,
    reasoning: str = "Looks good",
    red_flags: list[str] | None = None,
) -> str:
    """Build a JSON validation response string."""
    return json.dumps(
        {
            "valid": valid,
            "adjusted_confidence": adjusted_confidence,
            "reasoning": reasoning,
            "red_flags": red_flags or [],
        }
    )


# ── observe() Tests ───────────────────────────────────────────────


class TestObserve:
    def test_observe_stores_signal(self, validator: SignalValidatorAgent, buy_signal: SignalEvent):
        """observe() should store valid SignalEvent in pending list."""
        validator.observe(buy_signal)
        assert len(validator._pending) == 1
        assert validator._pending[0] is buy_signal

    def test_observe_ignores_no_trade(self, validator: SignalValidatorAgent):
        """observe() should ignore NO_TRADE signals."""
        sig = SignalEvent(symbol="XAUUSD", signal_type=SignalType.NO_TRADE)
        validator.observe(sig)
        assert len(validator._pending) == 0

    def test_observe_ignores_non_signal(self, validator: SignalValidatorAgent):
        """observe() should ignore non-SignalEvent events."""
        bar = BarEvent(symbol="XAUUSD", close=2000.0)
        validator.observe(bar)
        assert len(validator._pending) == 0

    def test_observe_stores_multiple(self, validator: SignalValidatorAgent, buy_signal, sell_signal):
        """observe() should accumulate multiple signals."""
        validator.observe(buy_signal)
        validator.observe(sell_signal)
        assert len(validator._pending) == 2


# ── act() Tests ───────────────────────────────────────────────────


class TestAct:
    @pytest.mark.asyncio
    async def test_act_validates_signal(self, validator: SignalValidatorAgent, buy_signal):
        """act() should validate signal and yield SignalValidationEvent."""
        validator.observe(buy_signal)

        mock_response = _make_validation_response(valid=True, adjusted_confidence=0.72)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(mock_response, 150.0, MagicMock(tier=1)))

        with patch.object(_sv_mod, "get_router", return_value=mock_router):
            results = []
            async for event in validator.act():
                results.append(event)

        assert len(results) == 1
        assert isinstance(results[0], SignalValidationEvent)
        assert results[0].valid is True
        assert results[0].adjusted_confidence == 0.72
        assert results[0].signal_id == buy_signal.event_id

    @pytest.mark.asyncio
    async def test_act_timeout_fallback(self, validator: SignalValidatorAgent, buy_signal):
        """act() should yield fallback event on LLM timeout."""
        validator.observe(buy_signal)

        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=TimeoutError())

        with patch.object(_sv_mod, "get_router", return_value=mock_router):
            results = []
            async for event in validator.act():
                results.append(event)

        assert len(results) == 1
        assert isinstance(results[0], SignalValidationEvent)
        assert results[0].valid is True  # fallback passes through
        assert results[0].adjusted_confidence == buy_signal.confidence
        assert "timeout" in results[0].reasoning.lower()
        assert "deterministic_fallback" in results[0].red_flags

    @pytest.mark.asyncio
    async def test_act_invalid_json_fallback(self, validator: SignalValidatorAgent, buy_signal):
        """act() should handle unparseable LLM response gracefully."""
        validator.observe(buy_signal)

        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=("This is not JSON at all", 100.0, MagicMock(tier=1)))

        with patch.object(_sv_mod, "get_router", return_value=mock_router):
            results = []
            async for event in validator.act():
                results.append(event)

        assert len(results) == 1
        assert isinstance(results[0], SignalValidationEvent)
        assert results[0].valid is True  # default parse: valid=True
        assert "unparseable" in results[0].reasoning.lower()

    @pytest.mark.asyncio
    async def test_act_empty_pending_yields_nothing(self, validator: SignalValidatorAgent):
        """act() with no pending signals should yield nothing."""
        results = []
        async for event in validator.act():
            results.append(event)
        assert len(results) == 0


# ── Prompt Building ───────────────────────────────────────────────


class TestBuildPrompt:
    def test_build_prompt_format(self, validator: SignalValidatorAgent, buy_signal):
        """_build_prompt should produce a well-formed prompt with signal data."""
        prompt = validator._build_prompt(buy_signal)

        assert "XAUUSD" in prompt
        assert "BUY" in prompt
        assert "0.75" in prompt
        assert "2345.5" in prompt
        assert "2340.0" in prompt
        assert "2355.0" in prompt
        assert "TREND_UP" in prompt
        assert "mtm" in prompt

    def test_build_prompt_includes_rr(self, validator: SignalValidatorAgent, buy_signal):
        """_build_prompt should include computed R:R ratio."""
        prompt = validator._build_prompt(buy_signal)
        # R:R = |2355 - 2345.5| / |2345.5 - 2340| = 9.5 / 5.5 ≈ 1.73
        assert "1.73" in prompt


# ── Response Parsing ──────────────────────────────────────────────


class TestParseResponse:
    def test_parse_response_valid_json(self, validator: SignalValidatorAgent, buy_signal):
        """_parse_response should parse valid JSON correctly."""
        raw = _make_validation_response(valid=True, adjusted_confidence=0.80, red_flags=["high_vol"])
        result = validator._parse_response(raw, buy_signal)

        assert result["valid"] is True
        assert result["adjusted_confidence"] == 0.80
        assert result["red_flags"] == ["high_vol"]

    def test_parse_response_markdown_codeblock(self, validator: SignalValidatorAgent, buy_signal):
        """_parse_response should strip markdown code fences."""
        raw_json = _make_validation_response(valid=False, adjusted_confidence=0.50)
        raw = f"```json\n{raw_json}\n```"
        result = validator._parse_response(raw, buy_signal)

        assert result["valid"] is False
        assert result["adjusted_confidence"] == 0.50

    def test_parse_response_invalid_fallback(self, validator: SignalValidatorAgent, buy_signal):
        """_parse_response should return defaults for unparseable input."""
        result = validator._parse_response("not json at all", buy_signal)

        assert result["valid"] is True
        assert result["adjusted_confidence"] == buy_signal.confidence
        assert "unparseable" in result["reasoning"].lower()
        assert "unparseable_llm_response" in result["red_flags"]

    def test_parse_response_embedded_json(self, validator: SignalValidatorAgent, buy_signal):
        """_parse_response should extract JSON embedded in surrounding text."""
        raw = f"Here is my analysis:\n{_make_validation_response(valid=True, adjusted_confidence=0.65)}\nEnd."
        result = validator._parse_response(raw, buy_signal)

        assert result["valid"] is True
        assert result["adjusted_confidence"] == 0.65


# ── R:R Computation ───────────────────────────────────────────────


class TestComputeRR:
    def test_compute_rr_correct(self):
        """_compute_rr should calculate reward/risk correctly."""
        # entry=100, sl=95, tp=110 → risk=5, reward=10 → RR=2.0
        assert SignalValidatorAgent._compute_rr(100.0, 95.0, 110.0) == 2.0

    def test_compute_rr_short_trade(self):
        """_compute_rr should work for short trades."""
        # entry=100, sl=105, tp=90 → risk=5, reward=10 → RR=2.0
        assert SignalValidatorAgent._compute_rr(100.0, 105.0, 90.0) == 2.0

    def test_compute_rr_zero_risk(self):
        """_compute_rr should return 0 when entry == sl."""
        assert SignalValidatorAgent._compute_rr(100.0, 100.0, 110.0) == 0.0

    def test_compute_rr_zero_inputs(self):
        """_compute_rr should return 0 for zero/missing inputs."""
        assert SignalValidatorAgent._compute_rr(0.0, 95.0, 110.0) == 0.0
        assert SignalValidatorAgent._compute_rr(100.0, 0.0, 110.0) == 0.0
        assert SignalValidatorAgent._compute_rr(100.0, 95.0, 0.0) == 0.0


# ── Confidence Clamping ───────────────────────────────────────────


class TestConfidenceClamped:
    @pytest.mark.asyncio
    async def test_confidence_clamped_max(self, validator: SignalValidatorAgent, buy_signal):
        """Adjusted confidence should be clamped to MAX_CONFIDENCE (0.95)."""
        validator.observe(buy_signal)

        mock_response = _make_validation_response(adjusted_confidence=0.99)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(mock_response, 100.0, MagicMock(tier=1)))

        with patch.object(_sv_mod, "get_router", return_value=mock_router):
            results = []
            async for event in validator.act():
                results.append(event)

        assert results[0].adjusted_confidence == 0.95

    @pytest.mark.asyncio
    async def test_confidence_clamped_min(self, validator: SignalValidatorAgent, buy_signal):
        """Adjusted confidence should be clamped to MIN_CONFIDENCE (0.1)."""
        validator.observe(buy_signal)

        mock_response = _make_validation_response(adjusted_confidence=0.01)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(mock_response, 100.0, MagicMock(tier=1)))

        with patch.object(_sv_mod, "get_router", return_value=mock_router):
            results = []
            async for event in validator.act():
                results.append(event)

        assert results[0].adjusted_confidence == 0.1


# ── Reset ─────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_pending(self, validator: SignalValidatorAgent, buy_signal, sell_signal):
        """reset() should clear all pending signals."""
        validator.observe(buy_signal)
        validator.observe(sell_signal)
        assert len(validator._pending) == 2

        validator.reset()
        assert len(validator._pending) == 0


# ── Fallback Event ────────────────────────────────────────────────


class TestFallbackEvent:
    def test_fallback_preserves_confidence(self, validator: SignalValidatorAgent, buy_signal):
        """_fallback_event should preserve original confidence."""
        event = validator._fallback_event(buy_signal, "test reason")

        assert event.original_confidence == buy_signal.confidence
        assert event.adjusted_confidence == buy_signal.confidence
        assert event.valid is True
        assert "test reason" in event.reasoning
        assert "deterministic_fallback" in event.red_flags
        assert event.tier_used == 0
