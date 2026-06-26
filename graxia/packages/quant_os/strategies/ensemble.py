"""
Ensemble Strategy - Combines MTM, MRB, MLB signals + optional agent pipeline

Ensemble Vote System:
- MTM (Multi-Timeframe Momentum): 40% weight
- MRB (Mean Reversion Bollinger): 25% weight
- MLB (ML Breakout): 35% weight

Agent Pipeline (C3):
- Accepts optional list of Agent instances
- Feeds BarEvent to each agent, collects opinion signals
- Weighted voting with consensus threshold and veto support

Signal Aggregation:
1. Collect signals from all strategies and agents
2. Calculate weighted vote for each direction
3. Require 60% minimum confidence for execution
4. Abstain if signals conflict or confidence too low
5. Agent veto can block trade regardless of other signals

Decision Logic:
- BUY: Long confidence >= 0.60, Short confidence < 0.40
- SELL: Short confidence >= 0.60, Long confidence < 0.40
- NO_TRADE: Confidence < 0.60 or conflicting signals or agent veto
"""

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from ..core.config import get_config
from ..core.enums import DecisionType, RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

# Optional Agent import (C1 may not exist yet)
try:
    from ..core.agents.base import Agent
except ImportError:
    Agent = None  # type: ignore[misc,assignment]


# Strategy weights (from blueprint)
STRATEGY_WEIGHTS = {
    "mtm": 0.40,  # Most reliable in trending market
    "mrb": 0.25,  # Good in range, reduce weight
    "mlb": 0.35,  # ML-driven, higher PF
}

# Minimum confidence threshold for execution
MIN_ENSEMBLE_CONFIDENCE = 0.60


@runtime_checkable
class AgentLike(Protocol):
    """Protocol for anything that can act as an ensemble agent."""

    @property
    def name(self) -> str: ...
    def observe(self, event) -> None: ...
    def act(self): ...


def get_ensemble_signal(
    mtm_signal: Signal | None,
    mrb_signal: Signal | None,
    mlb_signal: Signal | None,
    regime: RegimeType | None = None,
    weights: dict[str, float] | None = None,
    agent_signals: list[tuple[str, Signal | None, float]] | None = None,
    agent_veto: bool = False,
) -> tuple[DecisionType, float, dict[str, Any]]:
    """
    Calculate ensemble signal from individual strategy signals and optional agents.

    Args:
        mtm_signal: Signal from MTM strategy
        mrb_signal: Signal from MRB strategy
        mlb_signal: Signal from MLB strategy
        regime: Current market regime
        weights: Optional custom weights
        agent_signals: List of (agent_name, signal_or_none, weight) tuples
        agent_veto: If True, agents can veto the ensemble decision

    Returns:
        Tuple of (decision, confidence, details)
    """
    weights = weights or STRATEGY_WEIGHTS

    # Collect votes
    votes = {
        "buy": 0.0,
        "sell": 0.0,
        "neutral": 0.0,
    }

    signal_details = {
        "mtm": None,
        "mrb": None,
        "mlb": None,
    }

    # MTM vote
    if mtm_signal:
        signal_details["mtm"] = {
            "signal": mtm_signal.signal_type.value,
            "confidence": mtm_signal.confidence,
            "stop_loss": str(mtm_signal.stop_loss) if mtm_signal.stop_loss else None,
            "take_profit": str(mtm_signal.take_profit) if mtm_signal.take_profit else None,
        }
        if mtm_signal.signal_type == SignalType.BUY:
            votes["buy"] += weights["mtm"] * mtm_signal.confidence
        elif mtm_signal.signal_type == SignalType.SELL:
            votes["sell"] += weights["mtm"] * mtm_signal.confidence
        else:
            votes["neutral"] += weights["mtm"]
    else:
        votes["neutral"] += weights["mtm"]

    # MRB vote
    if mrb_signal:
        signal_details["mrb"] = {
            "signal": mrb_signal.signal_type.value,
            "confidence": mrb_signal.confidence,
            "stop_loss": str(mrb_signal.stop_loss) if mrb_signal.stop_loss else None,
            "take_profit": str(mrb_signal.take_profit) if mrb_signal.take_profit else None,
        }
        if mrb_signal.signal_type == SignalType.BUY:
            votes["buy"] += weights["mrb"] * mrb_signal.confidence
        elif mrb_signal.signal_type == SignalType.SELL:
            votes["sell"] += weights["mrb"] * mrb_signal.confidence
        else:
            votes["neutral"] += weights["mrb"]
    else:
        votes["neutral"] += weights["mrb"]

    # MLB vote
    if mlb_signal:
        signal_details["mlb"] = {
            "signal": mlb_signal.signal_type.value,
            "confidence": mlb_signal.confidence,
            "stop_loss": str(mlb_signal.stop_loss) if mlb_signal.stop_loss else None,
            "take_profit": str(mlb_signal.take_profit) if mlb_signal.take_profit else None,
        }
        if mlb_signal.signal_type == SignalType.BUY:
            votes["buy"] += weights["mlb"] * mlb_signal.confidence
        elif mlb_signal.signal_type == SignalType.SELL:
            votes["sell"] += weights["mlb"] * mlb_signal.confidence
        else:
            votes["neutral"] += weights["mlb"]
    else:
        votes["neutral"] += weights["mlb"]

    # Agent pipeline votes
    agent_votes: dict[str, dict[str, Any]] = {}
    vetoed = False
    dissenting_views: list[dict[str, Any]] = []

    if agent_signals:
        total_agent_weight = sum(w for _, _, w in agent_signals)
        strategy_total = sum(weights.values())

        for agent_name, sig, agent_weight in agent_signals:
            # Normalize agent weight relative to strategy total
            normalized_weight = (
                (agent_weight / max(total_agent_weight, 1e-9)) * strategy_total
                if total_agent_weight > 0
                else agent_weight
            )

            vote_record = {
                "direction": "neutral",
                "confidence": 0.0,
                "weight": agent_weight,
                "normalized_weight": normalized_weight,
            }

            if sig is not None:
                if sig.signal_type == SignalType.BUY:
                    votes["buy"] += normalized_weight * sig.confidence
                    vote_record["direction"] = "buy"
                    vote_record["confidence"] = sig.confidence
                elif sig.signal_type == SignalType.SELL:
                    votes["sell"] += normalized_weight * sig.confidence
                    vote_record["direction"] = "sell"
                    vote_record["confidence"] = sig.confidence
                else:
                    votes["neutral"] += normalized_weight
            else:
                votes["neutral"] += normalized_weight

            agent_votes[agent_name] = vote_record

        # Check for agent veto: majority of agents disagree with winning direction
        if agent_veto and len(agent_signals) >= 2:
            best_direction = (
                max(("buy", "sell"), key=lambda d: votes[d])
                if max(votes["buy"], votes["sell"]) > votes["neutral"]
                else "neutral"
            )

            if best_direction != "neutral":
                dissent_count = 0
                for agent_name, sig, _ in agent_signals:
                    if sig is not None:
                        agent_dir = "buy" if sig.signal_type == SignalType.BUY else "sell"
                        if agent_dir != best_direction:
                            dissent_count += 1
                            dissenting_views.append(
                                {
                                    "agent": agent_name,
                                    "direction": agent_dir,
                                    "confidence": sig.confidence,
                                }
                            )
                # Veto if majority of agents dissent
                if dissent_count > len(agent_signals) / 2:
                    vetoed = True

    # Determine decision
    best_direction = max(votes, key=votes.get)
    confidence = votes[best_direction]

    if vetoed:
        decision = DecisionType.NO_TRADE
        reason = "agent_veto"
    elif confidence < MIN_ENSEMBLE_CONFIDENCE:
        decision = DecisionType.NO_TRADE
        reason = "insufficient_confidence"
    elif best_direction == "neutral":
        decision = DecisionType.NO_TRADE
        reason = "no_clear_direction"
    elif votes["buy"] > 0.4 and votes["sell"] > 0.4:
        # Conflicting signals
        decision = DecisionType.NO_TRADE
        reason = "conflicting_signals"
    elif best_direction == "buy":
        decision = DecisionType.BUY
        reason = "ensemble_vote"
    elif best_direction == "sell":
        decision = DecisionType.SELL
        reason = "ensemble_vote"
    else:
        decision = DecisionType.NO_TRADE
        reason = "unclear"

    # Build consensus SL and TP
    consensus_levels = _calculate_consensus_levels(mtm_signal, mrb_signal, mlb_signal, best_direction)

    # Consensus score: ratio of votes for winning direction to total
    total_votes = votes["buy"] + votes["sell"] + votes["neutral"]
    consensus_score = votes[best_direction] / total_votes if total_votes > 0 else 0.0

    details = {
        "votes": votes,
        "individual_signals": signal_details,
        "consensus": consensus_levels,
        "consensus_score": round(consensus_score, 4),
        "agent_votes": agent_votes,
        "dissenting_views": dissenting_views,
        "vetoed": vetoed,
        "reason": reason,
        "regime": regime.value if regime else None,
    }

    return decision, confidence, details


def _calculate_consensus_levels(
    mtm_signal: Signal | None, mrb_signal: Signal | None, mlb_signal: Signal | None, direction: str
) -> dict[str, Decimal | None]:
    """Calculate consensus stop loss and take profit levels"""

    sl_levels = []
    tp_levels = []
    weights = []

    for signal, weight in [
        (mtm_signal, STRATEGY_WEIGHTS["mtm"]),
        (mrb_signal, STRATEGY_WEIGHTS["mrb"]),
        (mlb_signal, STRATEGY_WEIGHTS["mlb"]),
    ]:
        if signal and signal.stop_loss and signal.take_profit:
            sl_levels.append(float(signal.stop_loss))
            tp_levels.append(float(signal.take_profit))
            weights.append(weight)

    if not sl_levels or not tp_levels:
        return {"stop_loss": None, "take_profit": None}

    # Weighted average
    total_weight = sum(weights)
    if total_weight == 0:
        return {"stop_loss": None, "take_profit": None}

    consensus_sl = sum(sl * w for sl, w in zip(sl_levels, weights, strict=False)) / total_weight
    consensus_tp = sum(tp * w for tp, w in zip(tp_levels, weights, strict=False)) / total_weight

    return {
        "stop_loss": Decimal(str(consensus_sl)),
        "take_profit": Decimal(str(consensus_tp)),
    }


class EnsembleStrategy(Strategy):
    """
    Ensemble strategy that combines multiple sub-strategies and/or agent pipeline.

    Agents are optional and gracefully degrade if none provided or Agent ABC unavailable.
    """

    def __init__(
        self,
        mtm_strategy=None,
        mrb_strategy=None,
        mlb_strategy=None,
        agents: list | None = None,
        agent_veto: bool = False,
        consensus_threshold: float = MIN_ENSEMBLE_CONFIDENCE,
    ):
        config = get_config()

        super().__init__(
            StrategyConfig(
                name="Ensemble",
                version="1.0",
                symbols=config.symbols,
                timeframes=["M15"],
                risk_per_trade_pct=config.max_risk_per_trade_pct,
                min_confidence=config.ensemble_confidence_threshold,
            )
        )

        # Sub-strategies
        self.mtm = mtm_strategy
        self.mrb = mrb_strategy
        self.mlb = mlb_strategy

        # Weights
        self.weights = STRATEGY_WEIGHTS
        self.consensus_threshold = consensus_threshold

        # Agent pipeline (C3)
        self._agents: list = agents or []
        self.agent_veto = agent_veto

        # Validate agents if Agent ABC is available
        if Agent is not None:
            for a in self._agents:
                if not isinstance(a, Agent) and not (hasattr(a, "observe") and hasattr(a, "act")):
                    raise TypeError(
                        f"Agent {a!r} does not implement the Agent ABC. " "Ensure it has observe() and act() methods."
                    )

    def add_agent(self, agent) -> None:
        """Add an agent to the pipeline at runtime."""
        if (
            Agent is not None
            and not isinstance(agent, Agent)
            and not (hasattr(agent, "observe") and hasattr(agent, "act"))
        ):
            raise TypeError(f"Agent {agent!r} must implement observe() and act() methods.")
        self._agents.append(agent)

    def remove_agent(self, name: str) -> bool:
        """Remove agent by name. Returns True if found and removed."""
        for i, a in enumerate(self._agents):
            if getattr(a, "name", None) == name:
                self._agents.pop(i)
                return True
        return False

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    def required_features(self) -> list[str]:
        """All features from sub-strategies"""
        features = []
        if self.mtm:
            features.extend(self.mtm.required_features())
        if self.mrb:
            features.extend(self.mrb.required_features())
        if self.mlb:
            features.extend(self.mlb.required_features())
        return list(set(features))  # Deduplicate

    def _collect_agent_signals(
        self,
        bar_event,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None,
        regime: RegimeType | None,
    ) -> list[tuple[str, Signal | None, float]]:
        """
        Feed BarEvent to all agents and collect (name, signal_or_none, weight) tuples.

        Each agent:
        1. Receives observe(bar_event)
        2. Calls act() which should return a SignalEvent or None
        3. We convert SignalEvent to Signal if needed
        """
        agent_signals: list[tuple[str, Signal | None, float]] = []

        for agent in self._agents:
            try:
                agent.observe(bar_event)
                result = agent.act()

                agent_signal = None
                if result is not None:
                    # If agent returns a Signal, use it directly
                    if isinstance(result, Signal):
                        agent_signal = result
                    # If agent returns a SignalEvent, convert
                    elif hasattr(result, "signal_type") and hasattr(result, "confidence"):
                        try:
                            sig_type = (
                                SignalType(result.signal_type)
                                if isinstance(result.signal_type, str)
                                else result.signal_type
                            )
                        except (ValueError, AttributeError):
                            sig_type = SignalType.NO_TRADE

                        agent_signal = Signal.create(
                            strategy_id=f"agent_{agent.name}",
                            symbol=getattr(result, "symbol", symbol),
                            signal_type=sig_type,
                            confidence=getattr(result, "confidence", 0.0),
                        )

                # Default weight of 1.0 if agent doesn't declare one
                weight = getattr(agent, "weight", 1.0)
                agent_signals.append((agent.name, agent_signal, float(weight)))

            except Exception as e:
                # Agent errors are isolated — log and skip
                import logging

                logging.getLogger(__name__).warning("Agent %s error: %s", getattr(agent, "name", "?"), e)

        return agent_signals

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """Generate ensemble signal from sub-strategies and agent pipeline."""

        # Get signals from sub-strategies
        mtm_signal = None
        mrb_signal = None
        mlb_signal = None

        if self.mtm:
            mtm_signal = self.mtm.generate_signal(symbol, ohlcv_data, indicators, regime)

        if self.mrb:
            mrb_signal = self.mrb.generate_signal(symbol, ohlcv_data, indicators, regime)

        if self.mlb:
            mlb_signal = self.mlb.generate_signal(symbol, ohlcv_data, indicators, regime)

        # Collect agent signals if agents present
        agent_signals: list[tuple[str, Signal | None, float]] | None = None
        if self._agents:
            # Build a lightweight BarEvent for agents
            from ..core.events import BarEvent

            bar_event = BarEvent(
                symbol=symbol,
                timeframe="M15",
                open=ohlcv_data.get("open", [0])[-1],
                high=ohlcv_data.get("high", [0])[-1],
                low=ohlcv_data.get("low", [0])[-1],
                close=ohlcv_data.get("close", [0])[-1],
                volume=ohlcv_data.get("volume", [0])[-1],
                bar_index=len(ohlcv_data.get("close", [])),
                source="ensemble",
            )
            agent_signals = self._collect_agent_signals(bar_event, symbol, ohlcv_data, indicators, regime)

        # Calculate ensemble decision
        decision, confidence, details = get_ensemble_signal(
            mtm_signal,
            mrb_signal,
            mlb_signal,
            regime,
            self.weights,
            agent_signals=agent_signals,
            agent_veto=self.agent_veto,
        )

        # Check if we should trade
        if decision not in [DecisionType.BUY, DecisionType.SELL]:
            return None

        # Get price
        current_price = Decimal(str(ohlcv_data.get("close", [0])[-1]))

        # Get consensus levels
        consensus = details["consensus"]

        self.signals_generated += 1

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=SignalType.BUY if decision == DecisionType.BUY else SignalType.SELL,
            confidence=confidence,
            strength="strong" if confidence > 0.75 else "medium" if confidence > 0.65 else "weak",
            entry_price=current_price,
            stop_loss=consensus.get("stop_loss"),
            take_profit=consensus.get("take_profit"),
            regime=regime,
            timeframe="M15",
            indicator_values=details,
            notes=f"Ensemble signal: {decision.value} with {confidence:.2f} confidence",
        )

    def get_strategy_stats(self) -> dict[str, Any]:
        """Get stats from all sub-strategies and agents"""
        stats = {
            "ensemble": self.get_stats(),
            "agent_count": self.agent_count,
            "agent_veto": self.agent_veto,
        }

        if self.mtm:
            stats["mtm"] = self.mtm.get_stats()
        if self.mrb:
            stats["mrb"] = self.mrb.get_stats()
        if self.mlb:
            stats["mlb"] = self.mlb.get_stats()

        agent_names = [getattr(a, "name", f"agent_{i}") for i, a in enumerate(self._agents)]
        if agent_names:
            stats["agents"] = agent_names

        return stats
