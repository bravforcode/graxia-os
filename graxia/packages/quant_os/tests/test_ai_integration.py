"""
AI Integration Tests — end-to-end flows for Phase 5+6 components.

Covers:
- Signal flows through validator pipeline
- Validation adjusts confidence
- LLM timeout doesn't block flow
- Centaur agent sends to Telegram
- Callback approve executes trade
- Callback reject cancels trade

These tests verify cross-component wiring, not just unit behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.core.agents.centaur_telegram import (
    CentaurTelegramAgent,
)
from graxia.packages.quant_os.core.agents.signal_validator import SignalValidatorAgent
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.events import (
    SignalEvent,
    SignalValidationEvent,
)
from graxia.packages.quant_os.core.telegram_callback import (
    CallbackAction,
    PendingSignal,
    TelegramCallbackHandler,
)

# ── Helpers ───────────────────────────────────────────────────────


def _buy_signal(**overrides) -> SignalEvent:
    """Create a BUY SignalEvent with defaults."""
    defaults = {
        "symbol": "XAUUSD",
        "signal_type": SignalType.BUY,
        "confidence": 0.75,
        "entry_price": 2345.50,
        "stop_loss": 2340.00,
        "take_profit": 2355.00,
        "regime": "TREND_UP",
        "source": "technical_analyst",
        "metadata": {"strategy_source": "mtm"},
    }
    defaults.update(overrides)
    return SignalEvent(**defaults)


def _pending_signal(**overrides) -> PendingSignal:
    """Create a PendingSignal with defaults."""
    defaults = {
        "message_id": 42,
        "asset": "XAUUSD",
        "direction": "BUY",
        "confidence": 0.75,
        "entry": 2345.50,
        "stop_loss": 2340.00,
        "take_profit": 2355.00,
        "regime": "TREND_UP",
        "strategy_source": "mtm",
        "metadata": {},
    }
    defaults.update(overrides)
    return PendingSignal(**defaults)


# ── Signal → Validator Flow ───────────────────────────────────────


class TestSignalValidatorFlow:
    @pytest.mark.asyncio
    async def test_signal_flows_through_validator(self):
        """SignalEvent should flow through validator and produce SignalValidationEvent."""
        validator = SignalValidatorAgent(timeout=5.0)
        signal = _buy_signal()
        validator.observe(signal)

        assert len(validator._pending) == 1

        # Mock LLM to return valid response
        import json

        mock_response = json.dumps(
            {
                "valid": True,
                "adjusted_confidence": 0.70,
                "reasoning": "Valid signal",
                "red_flags": [],
            }
        )
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(mock_response, 120.0, MagicMock(tier=1)))

        with patch(
            "graxia.packages.quant_os.core.agents.signal_validator.get_router",
            return_value=mock_router,
        ):
            results = []
            async for event in validator.act():
                results.append(event)

        assert len(results) == 1
        assert isinstance(results[0], SignalValidationEvent)
        assert results[0].signal_id == signal.event_id
        assert results[0].valid is True

    @pytest.mark.asyncio
    async def test_validation_adjusts_confidence(self):
        """Validator should adjust confidence based on LLM response."""
        validator = SignalValidatorAgent(timeout=5.0)
        signal = _buy_signal(confidence=0.85)
        validator.observe(signal)

        import json

        # LLM suggests lower confidence
        mock_response = json.dumps(
            {
                "valid": True,
                "adjusted_confidence": 0.65,
                "reasoning": "High confidence without strong confluence",
                "red_flags": ["overconfident"],
            }
        )
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(mock_response, 100.0, MagicMock(tier=1)))

        with patch(
            "graxia.packages.quant_os.core.agents.signal_validator.get_router",
            return_value=mock_router,
        ):
            results = []
            async for event in validator.act():
                results.append(event)

        assert results[0].adjusted_confidence == 0.65
        assert results[0].adjusted_confidence < results[0].original_confidence
        assert "overconfident" in results[0].red_flags

    @pytest.mark.asyncio
    async def test_llm_timeout_doesnt_block_flow(self):
        """LLM timeout should produce fallback event, not block pipeline."""
        validator = SignalValidatorAgent(timeout=0.1)
        signal = _buy_signal()
        validator.observe(signal)

        # Simulate slow LLM
        async def slow_call(*args, **kwargs):
            await asyncio.sleep(10)
            return ("", 0.0, None)

        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=slow_call)

        with patch(
            "graxia.packages.quant_os.core.agents.signal_validator.get_router",
            return_value=mock_router,
        ):
            results = []
            async for event in validator.act():
                results.append(event)

        assert len(results) == 1
        assert isinstance(results[0], SignalValidationEvent)
        assert results[0].valid is True  # fallback passes through
        assert results[0].adjusted_confidence == signal.confidence


# ── Centaur → Telegram Flow ───────────────────────────────────────


class TestCentaurTelegramFlow:
    @pytest.mark.asyncio
    async def test_centaur_sends_to_telegram(self):
        """CentaurTelegramAgent should format and queue signals for Telegram."""
        agent = CentaurTelegramAgent(
            token="test_token",
            chat_id="12345",
        )

        signal = _buy_signal()
        agent.observe(signal)
        assert len(agent._pending) == 1

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        agent._client = mock_client

        await agent.act()

        # Wait for drain task to complete
        if agent._drain_task:
            await agent._drain_task

        # Verify Telegram API was called
        mock_client.post.assert_awaited()
        call_args = mock_client.post.call_args
        assert "sendMessage" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "12345"

        await agent.shutdown()


# ── Callback → Trade Flow ─────────────────────────────────────────


class TestCallbackTradeFlow:
    @pytest.mark.asyncio
    async def test_callback_approve_executes_trade(self):
        """APPROVE callback should trigger on_approve callback."""
        on_approve = AsyncMock()
        handler = TelegramCallbackHandler(
            token="test_token",
            on_approve=on_approve,
        )

        # Register a pending signal
        pending = _pending_signal()
        handler.register_signal(pending)

        # Mock HTTP calls
        handler._answer = AsyncMock()
        handler._edit_message = AsyncMock()

        callback_query = {
            "id": "cb_001",
            "data": "approve:XAUUSD:BUY",
            "message": {"message_id": 42},
        }

        result = await handler.handle_callback(callback_query)

        assert result is not None
        assert result.action == CallbackAction.APPROVE
        on_approve.assert_awaited_once()
        # Should pass PendingSignal and size_mult=1.0
        call_args = on_approve.call_args[0]
        assert call_args[1] == 1.0

    @pytest.mark.asyncio
    async def test_callback_reject_cancels_trade(self):
        """REJECT callback should trigger on_reject callback."""
        on_reject = AsyncMock()
        handler = TelegramCallbackHandler(
            token="test_token",
            on_reject=on_reject,
        )

        pending = _pending_signal()
        handler.register_signal(pending)

        handler._answer = AsyncMock()
        handler._edit_message = AsyncMock()

        callback_query = {
            "id": "cb_002",
            "data": "reject:XAUUSD:BUY",
            "message": {"message_id": 42},
        }

        result = await handler.handle_callback(callback_query)

        assert result is not None
        assert result.action == CallbackAction.REJECT
        on_reject.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_callback_half_size(self):
        """HALF callback should trigger on_approve with size_mult=0.5."""
        on_approve = AsyncMock()
        handler = TelegramCallbackHandler(
            token="test_token",
            on_approve=on_approve,
        )

        pending = _pending_signal()
        handler.register_signal(pending)

        handler._answer = AsyncMock()
        handler._edit_message = AsyncMock()

        callback_query = {
            "id": "cb_003",
            "data": "half:XAUUSD:BUY",
            "message": {"message_id": 42},
        }

        result = await handler.handle_callback(callback_query)

        assert result is not None
        assert result.action == CallbackAction.HALF
        on_approve.assert_awaited_once()
        call_args = on_approve.call_args[0]
        assert call_args[1] == 0.5


# ── Cross-Component Integration ──────────────────────────────────


class TestCrossComponentIntegration:
    @pytest.mark.asyncio
    async def test_signal_to_centaur_no_double_processing(self):
        """Signal should flow through validator then centaur independently."""
        validator = SignalValidatorAgent(timeout=5.0)
        centaur = CentaurTelegramAgent(token="test", chat_id="123")

        signal = _buy_signal()

        # Both observe the same signal
        validator.observe(signal)
        centaur.observe(signal)

        assert len(validator._pending) == 1
        assert len(centaur._pending) == 1

    @pytest.mark.asyncio
    async def test_callback_handler_tracks_results(self):
        """CallbackHandler should track all results for audit."""
        handler = TelegramCallbackHandler(token="test")
        handler._answer = AsyncMock()
        handler._edit_message = AsyncMock()

        pending = _pending_signal()
        handler.register_signal(pending)

        # Process approve
        await handler.handle_callback(
            {
                "id": "cb1",
                "data": "approve:XAUUSD:BUY",
                "message": {"message_id": 1},
            }
        )

        results = handler.get_results()
        assert len(results) == 1
        assert results[0].action == CallbackAction.APPROVE
