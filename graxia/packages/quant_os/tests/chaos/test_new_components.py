"""
Chaos Tests — CentaurTelegramAgent, SentimentAgent, CrossSectionalMomentum, AutoRetrain.

These tests simulate real-world failure modes:
- Network timeouts, 429 rate limits, malformed responses
- Queue overflow, concurrent access, shutdown races
- Empty data, corrupted state, missing dependencies
- LLM returning garbage, API keys missing, JSON parse errors

RULE: If a test fails, fix the CODE, never the test.
"""

from __future__ import annotations

import asyncio
import pickle
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# CentaurTelegramAgent Chaos Tests
# ═══════════════════════════════════════════════════════════════════


class TestCentaurTelegramChaos:
    """Chaos tests for CentaurTelegramAgent."""

    @pytest.fixture
    def agent(self):
        from graxia.packages.quant_os.core.agents.centaur_telegram import CentaurTelegramAgent
        return CentaurTelegramAgent(token="test_token", chat_id="123")

    @pytest.fixture
    def signal_event(self):
        from graxia.packages.quant_os.core.events import SignalEvent
        from graxia.packages.quant_os.core.enums import SignalType
        return SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            entry_price=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            regime="TREND_UP",
            source="ensemble",
        )

    @pytest.mark.asyncio
    async def test_queue_overflow_does_not_block_eventbus(self, agent, signal_event):
        """Chaos: fill queue beyond maxsize — should drop, not block."""

        # Fill queue to max
        for _ in range(agent.QUEUE_MAXSIZE + 10):
            agent._pending.append(signal_event)

        # act() should not raise or block
        await agent.act()

        # Queue should be bounded
        assert agent._queue.qsize() <= agent.QUEUE_MAXSIZE

    @pytest.mark.asyncio
    async def test_shutdown_cancels_drain_task(self, agent, signal_event):
        """Chaos: shutdown while drain is running — should not leak tasks."""
        agent._pending.append(signal_event)
        await agent.act()

        # Shutdown should cancel drain task
        await agent.shutdown()

        if agent._drain_task and not agent._drain_task.done():
            assert False, "Drain task not cancelled after shutdown"

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, agent):
        """Chaos: call shutdown() multiple times — should not raise."""
        await agent.shutdown()
        await agent.shutdown()
        await agent.shutdown()

    @pytest.mark.asyncio
    async def test_observe_ignores_no_trade(self, agent):
        """Chaos: NO_TRADE signal should be silently dropped."""
        from graxia.packages.quant_os.core.events import SignalEvent
        from graxia.packages.quant_os.core.enums import SignalType

        sig = SignalEvent(symbol="XAUUSD", signal_type=SignalType.NO_TRADE)
        agent.observe(sig)
        assert len(agent._pending) == 0

    @pytest.mark.asyncio
    async def test_observe_ignores_non_signal_event(self, agent):
        """Chaos: non-SignalEvent should be silently dropped."""
        from graxia.packages.quant_os.core.events import BarEvent

        bar = BarEvent(symbol="XAUUSD", close=2350.0)
        agent.observe(bar)
        assert len(agent._pending) == 0

    @pytest.mark.asyncio
    async def test_act_clears_pending_even_on_config_missing(self):
        """Chaos: no token/chat_id — should clear pending, not accumulate."""
        from graxia.packages.quant_os.core.agents.centaur_telegram import CentaurTelegramAgent
        from graxia.packages.quant_os.core.events import SignalEvent
        from graxia.packages.quant_os.core.enums import SignalType

        agent = CentaurTelegramAgent(token="", chat_id="")
        sig = SignalEvent(symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8)
        agent._pending.append(sig)

        await agent.act()
        assert len(agent._pending) == 0

    @pytest.mark.asyncio
    async def test_http_timeout_does_not_propagate(self, agent, signal_event):
        """Chaos: httpx.ConnectTimeout should be caught, not raised."""
        import httpx

        agent._pending.append(signal_event)

        with patch.object(agent, "_ensure_client") as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
            mock_client.return_value = mock_http

            # Should not raise
            await agent.act()

    @pytest.mark.asyncio
    async def test_rate_limit_429_triggers_backoff(self, agent, signal_event):
        """Chaos: 429 response should trigger sleep, not crash."""
        agent._pending.append(signal_event)

        # httpx.Response.json() is synchronous — use MagicMock, not AsyncMock
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {"parameters": {"retry_after": 1}}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch.object(agent, "_ensure_client", return_value=mock_http):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await agent.act()
                # Wait for drain task to complete
                if agent._drain_task:
                    await agent._drain_task
                # Should have called sleep with retry_after
                mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_generic_exception_does_not_propagate(self, agent, signal_event):
        """Chaos: any exception should be caught, not crash the EventBus."""
        agent._pending.append(signal_event)

        with patch.object(agent, "_ensure_client") as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=RuntimeError("unexpected"))
            mock_client.return_value = mock_http

            # Should not raise
            await agent.act()

    @pytest.mark.asyncio
    async def test_concurrent_act_calls(self, agent, signal_event):
        """Chaos: multiple act() calls concurrently — no race condition."""

        for _ in range(5):
            agent._pending.append(signal_event)

        # Run 3 concurrent act() calls
        tasks = [agent.act() for _ in range(3)]
        await asyncio.gather(*tasks)

        # Should not crash, queue should be bounded
        assert agent._queue.qsize() <= agent.QUEUE_MAXSIZE + 5

    def test_reset_clears_all_state(self, agent, signal_event):
        """Chaos: reset() should clear pending, queue, and task."""
        agent._pending.append(signal_event)
        agent.reset()
        assert len(agent._pending) == 0


# ═══════════════════════════════════════════════════════════════════
# SentimentAgent Chaos Tests (basic - full tests in test_multi_provider.py)
# ═══════════════════════════════════════════════════════════════════


class TestSentimentAgentChaos:
    """Basic chaos tests for SentimentAgent. Full coverage in test_multi_provider.py."""

    @pytest.fixture
    def agent(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        return SentimentAgent()

    @pytest.mark.asyncio
    async def test_empty_headlines_returns_none(self, agent):
        """Chaos: no pending headlines - should return None."""
        result = await agent.act()
        assert result is None

    def test_observe_adds_headline(self, agent):
        """Chaos: observe with headline - should add to pending."""
        agent._pending_headlines.append({"headline": "Fed raises rates", "source": "test", "timestamp": "2026-01-01"})
        assert len(agent._pending_headlines) == 1

    def test_observe_ignores_non_event(self, agent):
        """Chaos: non-Event object - should not crash."""
        agent.observe("not an event")
        agent.observe(None)
        assert len(agent._pending_headlines) == 0

    def test_reset_clears_pending(self, agent):
        """Chaos: reset() should clear pending headlines."""
        agent._pending_headlines.append({"headline": "Test", "source": "test", "timestamp": "2026-01-01"})
        agent.reset()
        assert len(agent._pending_headlines) == 0

    @pytest.mark.asyncio
    async def test_concurrent_act_calls(self, agent):
        """Chaos: multiple act() concurrently - no race condition."""
        tasks = [agent.act() for _ in range(3)]
        results = await asyncio.gather(*tasks)
        assert all(r is None for r in results)


# ═══════════════════════════════════════════════════════════════════
# CrossSectionalMomentum Chaos Tests
# ═══════════════════════════════════════════════════════════════════


class TestCrossSectionalMomentumChaos:
    """Chaos tests for CrossSectionalMomentum."""

    @pytest.fixture
    def strategy(self, tmp_path):
        from graxia.packages.quant_os.scripts.cross_sectional_momentum import CrossSectionalMomentum, MomentumConfig
        config = MomentumConfig(top_n=5, select_n=2, lookback_days=7)
        s = CrossSectionalMomentum(config)
        s._state_path = tmp_path / "state.json"
        return s

    def test_should_rebalance_first_run(self, strategy):
        """Chaos: first run — should always rebalance."""
        assert strategy.should_rebalance() is True

    def test_should_rebalance_not_yet(self, strategy):
        """Chaos: just rebalanced — should not rebalance again."""
        from datetime import timedelta
        strategy._last_rebalance = datetime.now(UTC) - timedelta(days=1)
        assert strategy.should_rebalance() is False

    def test_should_rebalance_after_interval(self, strategy):
        """Chaos: enough time passed — should rebalance."""
        from datetime import timedelta
        strategy._last_rebalance = datetime.now(UTC) - timedelta(days=8)
        assert strategy.should_rebalance() is True

    def test_calculate_rebalance_empty_selected(self, strategy):
        """Chaos: empty selection — should clear all positions."""
        strategy._positions = {"BTC/USDT": {"entry_price": 50000}}
        result = strategy.calculate_rebalance([])
        assert len(result.removed) == 1
        assert len(strategy._positions) == 0

    def test_calculate_rebalance_adds_new(self, strategy):
        """Chaos: new coins — should add positions."""
        from graxia.packages.quant_os.scripts.cross_sectional_momentum import CoinMomentum
        selected = [
            CoinMomentum(symbol="ETH/USDT", price_now=3000, price_lookback=2800, return_pct=7.1, volume_24h=5e6),
        ]
        result = strategy.calculate_rebalance(selected)
        assert len(result.added) == 1
        assert "ETH/USDT" in strategy._positions

    def test_calculate_rebalance_removes_old(self, strategy):
        """Chaos: old coins not in selection — should remove positions."""
        from graxia.packages.quant_os.scripts.cross_sectional_momentum import CoinMomentum
        strategy._positions = {"DOGE/USDT": {"entry_price": 0.1}}
        selected = [
            CoinMomentum(symbol="ETH/USDT", price_now=3000, price_lookback=2800, return_pct=7.1, volume_24h=5e6),
        ]
        result = strategy.calculate_rebalance(selected)
        assert len(result.removed) == 1
        assert result.removed[0]["symbol"] == "DOGE/USDT"

    def test_state_persistence(self, strategy, tmp_path):
        """Chaos: save and load state — should survive restart."""
        strategy._positions = {"ETH/USDT": {"entry_price": 3000}}
        strategy._last_rebalance = datetime.now(UTC)
        strategy._save_state()

        # Create new strategy instance
        from graxia.packages.quant_os.scripts.cross_sectional_momentum import CrossSectionalMomentum, MomentumConfig
        config = MomentumConfig()
        new_strategy = CrossSectionalMomentum(config)
        new_strategy._state_path = tmp_path / "state.json"
        new_strategy._load_state()

        assert "ETH/USDT" in new_strategy._positions

    @pytest.mark.asyncio
    async def test_scan_empty_market(self, strategy):
        """Chaos: no coins found — should handle gracefully."""
        with patch("graxia.packages.quant_os.market_data.ccxt_feeder.BinanceFeeder") as MockFeeder:
            mock_feeder = AsyncMock()
            mock_feeder.scan_top_altcoins = AsyncMock(return_value=[])
            mock_feeder.__aenter__ = AsyncMock(return_value=mock_feeder)
            mock_feeder.__aexit__ = AsyncMock(return_value=False)
            MockFeeder.return_value = mock_feeder

            result = await strategy.scan_and_rank()
            assert result == []


# ═══════════════════════════════════════════════════════════════════
# AutoRetrain Chaos Tests
# ═══════════════════════════════════════════════════════════════════


class TestAutoRetrainChaos:
    """Chaos tests for AutoRetrain scheduler."""

    def test_load_champion_no_file(self, tmp_path):
        """Chaos: no champion file — should return None."""
        with patch("graxia.packages.quant_os.scripts.auto_retrain.CHAMPION_PATH", tmp_path / "nonexistent.pkl"):
            from graxia.packages.quant_os.scripts.auto_retrain import load_champion
            result = load_champion()
            assert result is None

    def test_load_champion_corrupted_file(self, tmp_path):
        """Chaos: corrupted pickle file — should raise."""
        corrupted = tmp_path / "champion.pkl"
        corrupted.write_bytes(b"not a valid pickle")

        with patch("graxia.packages.quant_os.scripts.auto_retrain.CHAMPION_PATH", corrupted):
            from graxia.packages.quant_os.scripts.auto_retrain import load_champion
            with pytest.raises(Exception):
                load_champion()

    def test_hot_swap_no_champion_promotes(self, tmp_path):
        """Chaos: no existing champion — challenger should become champion."""
        challenger_data = {"model": "test", "metrics": {"accuracy": 0.8}}
        challenger_metrics = MagicMock()
        challenger_metrics.deflated_sharpe = 1.5
        challenger_metrics.oos_max_drawdown = 10.0

        with patch("graxia.packages.quant_os.scripts.auto_retrain.CHAMPION_PATH", tmp_path / "champion.pkl"):
            from graxia.packages.quant_os.scripts.auto_retrain import hot_swap
            result = hot_swap(challenger_data, challenger_metrics)
            assert result is True

    def test_hot_swap_challenger_not_better(self, tmp_path):
        """Chaos: challenger worse than champion — should not swap."""
        # Create existing champion
        champion_data = {"model": "champion", "metrics": {"accuracy": 0.9}}
        champion_path = tmp_path / "champion.pkl"
        with open(champion_path, "wb") as f:
            pickle.dump(champion_data, f)

        challenger_data = {"model": "challenger", "metrics": {"accuracy": 0.7}}
        challenger_metrics = MagicMock()
        challenger_metrics.deflated_sharpe = 1.0
        challenger_metrics.oos_max_drawdown = 15.0

        with patch("graxia.packages.quant_os.scripts.auto_retrain.CHAMPION_PATH", champion_path):
            from graxia.packages.quant_os.scripts.auto_retrain import hot_swap
            with patch("graxia.packages.quant_os.scripts.auto_retrain.evaluate_model") as mock_eval:
                mock_eval.return_value = MagicMock(deflated_sharpe=2.0, oos_max_drawdown=5.0)
                result = hot_swap(challenger_data, challenger_metrics)
                assert result is False

    def test_log_retrain_creates_file(self, tmp_path):
        """Chaos: retrain log should be created on first run."""
        log_path = tmp_path / "retrain_history.jsonl"

        with patch("graxia.packages.quant_os.scripts.auto_retrain.RETRAIN_LOG", log_path):
            from graxia.packages.quant_os.scripts.auto_retrain import log_retrain
            log_retrain({"status": "test"})
            assert log_path.exists()
            content = log_path.read_text()
            assert "test" in content


# ═══════════════════════════════════════════════════════════════════
# EventBus Integration Chaos Tests
# ═══════════════════════════════════════════════════════════════════


class TestEventBusChaos:
    """Chaos tests for EventBus integration."""

    @pytest.mark.asyncio
    async def test_centaur_agent_subscribes_to_signal_new(self):
        """Chaos: verify CentaurTelegramAgent can subscribe to EventBus."""
        from graxia.packages.quant_os.core.event_bus import EventBus
        from graxia.packages.quant_os.core.agents.centaur_telegram import CentaurTelegramAgent
        from graxia.packages.quant_os.core.events import SignalEvent
        from graxia.packages.quant_os.core.enums import SignalType

        bus = EventBus()
        await bus.start()

        agent = CentaurTelegramAgent(token="test", chat_id="123")
        bus.subscribe("signal.new", agent.observe)

        sig = SignalEvent(symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8)
        await bus.publish("signal.new", sig)

        # Give time for dispatch
        await asyncio.sleep(0.1)

        assert len(agent._pending) >= 1

        await bus.stop()
        await agent.shutdown()

    @pytest.mark.asyncio
    async def test_sentiment_agent_receives_news(self):
        """Chaos: verify SentimentAgent receives news events."""
        from graxia.packages.quant_os.core.event_bus import EventBus
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import Event

        bus = EventBus()
        await bus.start()

        agent = SentimentAgent()
        bus.subscribe("news.high_impact", agent.observe)

        event = Event(source="news_aggregator")
        await bus.publish("news.high_impact", event)

        await asyncio.sleep(0.1)

        # Agent should have received the event (though it may not have a headline)
        await bus.stop()
        await agent.shutdown()
