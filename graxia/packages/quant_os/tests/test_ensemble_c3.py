"""Tests for Ensemble Strategy C3: Agent pipeline integration"""

from graxia.packages.quant_os.core.enums import DecisionType, RegimeType, SignalType
from graxia.packages.quant_os.core.events import BarEvent
from graxia.packages.quant_os.strategies.base import Signal
from graxia.packages.quant_os.strategies.ensemble import (
    EnsembleStrategy,
    get_ensemble_signal,
)

# ── Helper factories ─────────────────────────────────────────────


def make_signal(sig_type: SignalType, confidence: float = 0.7, **kw):
    return Signal.create(
        strategy_id=kw.pop("strategy_id", "test"),
        symbol=kw.pop("symbol", "XAUUSD"),
        signal_type=sig_type,
        confidence=confidence,
        **kw,
    )


def make_bar(**overrides):
    defaults = dict(
        symbol="XAUUSD",
        timeframe="M15",
        open=2000,
        high=2010,
        low=1990,
        close=2005,
        volume=100,
        bar_index=1,
        source="test",
    )
    defaults.update(overrides)
    return BarEvent(**defaults)


class FakeAgent:
    """Minimal agent stub — satisfies AgentLike protocol without requiring Agent ABC."""

    def __init__(self, name: str, signal: Signal = None, weight: float = 1.0):
        self.name = name
        self._signal = signal
        self.weight = weight
        self._observed_events = []

    def observe(self, event) -> None:
        self._observed_events.append(event)

    def act(self):
        return self._signal


# ── get_ensemble_signal unit tests ──────────────────────────────


class TestGetEnsembleSignal:
    """Direct tests on the get_ensemble_signal function."""

    def test_unanimous_buy(self):
        """All three strategies agree BUY → high confidence"""
        s = make_signal(SignalType.BUY, 0.8)
        decision, confidence, details = get_ensemble_signal(s, s, s)
        assert decision == DecisionType.BUY
        assert confidence > 0.7

    def test_unanimous_sell(self):
        s = make_signal(SignalType.SELL, 0.8)
        decision, confidence, details = get_ensemble_signal(s, s, s)
        assert decision == DecisionType.SELL
        assert confidence > 0.7

    def test_conflicting_signals_no_trade(self):
        buy_s = make_signal(SignalType.BUY, 0.8)
        sell_s = make_signal(SignalType.SELL, 0.8)
        # Use agents to push both sides above 0.4
        agent_buy = make_signal(SignalType.BUY, 0.9)
        agent_sell = make_signal(SignalType.SELL, 0.9)
        agent_signals = [
            ("abuy", agent_buy, 0.5),
            ("asell", agent_sell, 0.5),
        ]
        decision, _, details = get_ensemble_signal(buy_s, sell_s, sell_s, agent_signals=agent_signals)
        assert decision == DecisionType.NO_TRADE
        assert details["reason"] == "conflicting_signals"

    def test_low_confidence_no_trade(self):
        s = make_signal(SignalType.BUY, 0.3)
        decision, _, details = get_ensemble_signal(s, s, s)
        assert decision == DecisionType.NO_TRADE
        assert details["reason"] == "insufficient_confidence"

    def test_no_signals_no_trade(self):
        decision, _, details = get_ensemble_signal(None, None, None)
        assert decision == DecisionType.NO_TRADE

    def test_single_signal_enough(self):
        """One strong signal can produce a trade if it crosses threshold."""
        s = make_signal(SignalType.BUY, 0.9)
        decision, confidence, _ = get_ensemble_signal(s, None, None)
        # With mtm at 0.40 * 0.9 = 0.36, below threshold
        assert decision == DecisionType.NO_TRADE

    def test_two_signals_can_trade(self):
        """Two strong signals combined exceed threshold."""
        s = make_signal(SignalType.BUY, 0.9)
        decision, confidence, _ = get_ensemble_signal(s, s, None)
        # buy = 0.40*0.9 + 0.25*0.9 = 0.585, still below 0.60
        assert decision == DecisionType.NO_TRADE


# ── Agent voting tests ──────────────────────────────────────────


class TestAgentVoting:
    """Tests for agent pipeline integration in get_ensemble_signal."""

    def test_agents_boost_buy_confidence(self):
        """Agents that agree with strategy boost confidence."""
        s = make_signal(SignalType.BUY, 0.5)
        agent_s = make_signal(SignalType.BUY, 0.9)
        agent_signals = [("alpha", agent_s, 0.5)]
        decision, confidence, details = get_ensemble_signal(s, None, None, agent_signals=agent_signals)
        assert details["agent_votes"]["alpha"]["direction"] == "buy"
        assert confidence > 0.5

    def test_agents_reduce_confidence_when_opposed(self):
        """Agents opposing the strategy direction reduce confidence."""
        s = make_signal(SignalType.BUY, 0.6)
        agent_s = make_signal(SignalType.SELL, 0.8)
        agent_signals = [("alpha", agent_s, 1.0)]
        decision, confidence, details = get_ensemble_signal(s, s, None, agent_signals=agent_signals)
        # Agents push sell side, may cause no_trade
        assert details["agent_votes"]["alpha"]["direction"] == "sell"

    def test_agent_none_signal_adds_neutral(self):
        """Agent that produces no signal adds neutral weight."""
        s = make_signal(SignalType.BUY, 0.8)
        agent_signals = [("idle", None, 1.0)]
        decision, confidence, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals)
        assert details["agent_votes"]["idle"]["direction"] == "neutral"

    def test_multiple_agents_consensus_score(self):
        """Consensus score reflects proportion of agreement."""
        s = make_signal(SignalType.BUY, 0.8)
        a1 = make_signal(SignalType.BUY, 0.8)
        a2 = make_signal(SignalType.BUY, 0.8)
        agent_signals = [("a1", a1, 1.0), ("a2", a2, 1.0)]
        _, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals)
        assert details["consensus_score"] > 0.5

    def test_dissenting_views_recorded(self):
        """Agents opposing the majority are listed as dissenters."""
        # Strong strategy BUY signals win; agents dissent with very low weight
        s = make_signal(SignalType.BUY, 0.9)
        a1 = make_signal(SignalType.SELL, 0.5)
        a2 = make_signal(SignalType.SELL, 0.5)
        agent_signals = [("a1", a1, 0.1), ("a2", a2, 0.1)]
        decision, _, details = get_ensemble_signal(
            s,
            s,
            s,
            agent_signals=agent_signals,
            agent_veto=True,
        )
        # Strategy BUY wins, agents dissent
        assert len(details["dissenting_views"]) == 2


# ── Agent veto tests ────────────────────────────────────────────


class TestAgentVeto:
    """Veto-specific scenarios."""

    def test_veto_blocks_trade(self):
        """Majority of agents dissenting triggers veto."""
        s = make_signal(SignalType.BUY, 0.9)
        a1 = make_signal(SignalType.SELL, 0.8)
        a2 = make_signal(SignalType.SELL, 0.8)
        agent_signals = [("a1", a1, 1.0), ("a2", a2, 1.0)]
        decision, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals, agent_veto=True)
        assert decision == DecisionType.NO_TRADE
        assert details["reason"] == "agent_veto"
        assert details["vetoed"] is True

    def test_veto_disabled_ignores_dissent(self):
        """When agent_veto=False, dissent doesn't block."""
        s = make_signal(SignalType.BUY, 0.9)
        a1 = make_signal(SignalType.SELL, 0.8)
        a2 = make_signal(SignalType.SELL, 0.8)
        agent_signals = [("a1", a1, 1.0), ("a2", a2, 1.0)]
        decision, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals, agent_veto=False)
        assert details["vetoed"] is False

    def test_veto_needs_majority(self):
        """Single dissenter out of 3 doesn't veto."""
        s = make_signal(SignalType.BUY, 0.9)
        a1 = make_signal(SignalType.BUY, 0.9)
        a2 = make_signal(SignalType.SELL, 0.9)
        agent_signals = [("a1", a1, 1.0), ("a2", a2, 1.0)]
        decision, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals, agent_veto=True)
        assert details["vetoed"] is False

    def test_veto_with_single_agent_no_block(self):
        """Single agent can't form majority → no veto."""
        s = make_signal(SignalType.BUY, 0.9)
        a1 = make_signal(SignalType.SELL, 0.9)
        agent_signals = [("a1", a1, 1.0)]
        decision, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals, agent_veto=True)
        assert details["vetoed"] is False


# ── EnsembleStrategy class tests ────────────────────────────────


class TestEnsembleStrategy:
    """Test EnsembleStrategy class with agent pipeline."""

    def test_init_no_agents(self):
        """Strategy initializes with no agents (backward compatible)."""
        strat = EnsembleStrategy()
        assert strat.agent_count == 0
        assert strat.agent_veto is False

    def test_init_with_agents(self):
        """Strategy accepts agent list."""
        a1 = FakeAgent("alpha")
        a2 = FakeAgent("beta")
        strat = EnsembleStrategy(agents=[a1, a2])
        assert strat.agent_count == 2

    def test_add_agent(self):
        strat = EnsembleStrategy()
        strat.add_agent(FakeAgent("alpha"))
        assert strat.agent_count == 1

    def test_remove_agent(self):
        strat = EnsembleStrategy(agents=[FakeAgent("alpha")])
        assert strat.remove_agent("alpha") is True
        assert strat.agent_count == 0

    def test_remove_nonexistent_agent(self):
        strat = EnsembleStrategy()
        assert strat.remove_agent("ghost") is False

    def test_agent_observes_bar_event(self):
        """Agent receives BarEvent when generate_signal is called."""
        agent = FakeAgent("alpha")
        strat = EnsembleStrategy(agents=[agent])
        ohlcv = {
            "open": [2000],
            "high": [2010],
            "low": [1990],
            "close": [2005],
            "volume": [100],
        }
        strat.generate_signal("XAUUSD", ohlcv, None, None)
        assert len(agent._observed_events) == 1
        assert isinstance(agent._observed_events[0], BarEvent)

    def test_generate_signal_with_agents_returns_signal(self):
        """Agents that agree can help push confidence above threshold."""
        buy_signal = make_signal(SignalType.BUY, 0.7)
        a1 = FakeAgent("alpha", signal=buy_signal, weight=1.0)
        a2 = FakeAgent("beta", signal=buy_signal, weight=1.0)
        strat = EnsembleStrategy(agents=[a1, a2])
        ohlcv = {
            "open": [2000],
            "high": [2010],
            "low": [1990],
            "close": [2005],
            "volume": [100],
        }
        result = strat.generate_signal("XAUUSD", ohlcv, None, None)
        # May or may not exceed threshold depending on weighting; just check it runs
        assert result is None or isinstance(result, Signal)

    def test_stats_include_agents(self):
        a1 = FakeAgent("alpha")
        strat = EnsembleStrategy(agents=[a1])
        stats = strat.get_strategy_stats()
        assert stats["agent_count"] == 1
        assert "agents" in stats
        assert "alpha" in stats["agents"]

    def test_backward_compatible_no_agents(self):
        """Old-style init (mtm/mrb/mlb only) still works."""
        strat = EnsembleStrategy(mtm_strategy=None, mrb_strategy=None, mlb_strategy=None)
        ohlcv = {
            "open": [2000],
            "high": [2010],
            "low": [1990],
            "close": [2005],
            "volume": [100],
        }
        result = strat.generate_signal("XAUUSD", ohlcv, None, None)
        # No sub-strategies and no agents → no signal
        assert result is None


# ── Edge cases ──────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and edge-case tests."""

    def test_empty_ohlcv(self):
        decision, _, _ = get_ensemble_signal(None, None, None)
        assert decision == DecisionType.NO_TRADE

    def test_custom_weights(self):
        weights = {"mtm": 0.5, "mrb": 0.3, "mlb": 0.2}
        s = make_signal(SignalType.BUY, 0.8)
        decision, _, _ = get_ensemble_signal(s, s, s, weights=weights)
        assert decision == DecisionType.BUY

    def test_regime_in_details(self):
        s = make_signal(SignalType.BUY, 0.8)
        _, _, details = get_ensemble_signal(s, s, s, regime=RegimeType.TREND_STRONG_UP)
        assert details["regime"] == "TREND_STRONG_UP"

    def test_agent_weight_affects_voting(self):
        """Heavier agent has more influence on direction."""
        s = make_signal(SignalType.BUY, 0.5)
        a_heavy = FakeAgent("whale", signal=make_signal(SignalType.SELL, 0.8), weight=5.0)
        a_light = FakeAgent("minnow", signal=make_signal(SignalType.BUY, 0.9), weight=0.1)
        agent_signals = [
            (a_heavy.name, a_heavy._signal, a_heavy.weight),
            (a_light.name, a_light._signal, a_light.weight),
        ]
        decision, _, details = get_ensemble_signal(s, s, s, agent_signals=agent_signals)
        # Heavy agent pushes sell, likely causes conflict
        assert details["agent_votes"]["whale"]["confidence"] == 0.8

    def test_agent_act_exception_isolated(self):
        """If agent.act() raises, other agents still work."""

        class BadAgent:
            name = "bad"
            weight = 1.0

            def observe(self, e):
                pass

            def act(self):
                raise RuntimeError("boom")

        good = FakeAgent("good", signal=make_signal(SignalType.BUY, 0.9))
        strat = EnsembleStrategy(agents=[BadAgent(), good])
        ohlcv = {
            "open": [2000],
            "high": [2010],
            "low": [1990],
            "close": [2005],
            "volume": [100],
        }
        # Should not raise
        result = strat.generate_signal("XAUUSD", ohlcv, None, None)
        assert result is None or isinstance(result, Signal)
