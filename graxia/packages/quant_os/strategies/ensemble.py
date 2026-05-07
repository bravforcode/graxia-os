"""
Ensemble Strategy - Combines MTM, MRB, and MLB signals

Ensemble Vote System:
- MTM (Multi-Timeframe Momentum): 40% weight
- MRB (Mean Reversion Bollinger): 25% weight  
- MLB (ML Breakout): 35% weight

Signal Aggregation:
1. Collect signals from all 3 strategies
2. Calculate weighted vote for each direction
3. Require 60% minimum confidence for execution
4. Abstain if signals conflict or confidence too low

Decision Logic:
- BUY: Long confidence >= 0.60, Short confidence < 0.40
- SELL: Short confidence >= 0.60, Long confidence < 0.40
- NO_TRADE: Confidence < 0.60 or conflicting signals
"""

from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal

from .base import Strategy, Signal
from ..core.enums import SignalType, RegimeType, DecisionType
from ..core.config import get_config


# Strategy weights (from blueprint)
STRATEGY_WEIGHTS = {
    "mtm": 0.40,    # Most reliable in trending market
    "mrb": 0.25,    # Good in range, reduce weight
    "mlb": 0.35,    # ML-driven, higher PF
}

# Minimum confidence threshold for execution
MIN_ENSEMBLE_CONFIDENCE = 0.60


def get_ensemble_signal(
    mtm_signal: Optional[Signal],
    mrb_signal: Optional[Signal],
    mlb_signal: Optional[Signal],
    regime: Optional[RegimeType] = None,
    weights: Optional[Dict[str, float]] = None
) -> Tuple[DecisionType, float, Dict[str, Any]]:
    """
    Calculate ensemble signal from individual strategy signals.
    
    Args:
        mtm_signal: Signal from MTM strategy
        mrb_signal: Signal from MRB strategy
        mlb_signal: Signal from MLB strategy
        regime: Current market regime
        weights: Optional custom weights
    
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
    
    # Determine decision
    best_direction = max(votes, key=votes.get)
    confidence = votes[best_direction]
    
    # Check if confidence meets threshold
    if confidence < MIN_ENSEMBLE_CONFIDENCE:
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
    consensus_levels = _calculate_consensus_levels(
        mtm_signal, mrb_signal, mlb_signal, best_direction
    )
    
    details = {
        "votes": votes,
        "individual_signals": signal_details,
        "consensus": consensus_levels,
        "reason": reason,
        "regime": regime.value if regime else None,
    }
    
    return decision, confidence, details


def _calculate_consensus_levels(
    mtm_signal: Optional[Signal],
    mrb_signal: Optional[Signal],
    mlb_signal: Optional[Signal],
    direction: str
) -> Dict[str, Optional[Decimal]]:
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
    
    consensus_sl = sum(sl * w for sl, w in zip(sl_levels, weights)) / total_weight
    consensus_tp = sum(tp * w for tp, w in zip(tp_levels, weights)) / total_weight
    
    return {
        "stop_loss": Decimal(str(consensus_sl)),
        "take_profit": Decimal(str(consensus_tp)),
    }


class EnsembleStrategy(Strategy):
    """
    Ensemble strategy that combines multiple sub-strategies.
    """
    
    def __init__(
        self,
        mtm_strategy=None,
        mrb_strategy=None,
        mlb_strategy=None
    ):
        from ..core.config import get_config
        config = get_config()
        
        super().__init__(StrategyConfig(
            name="Ensemble",
            version="1.0",
            symbols=config.symbols,
            timeframes=["M15"],
            risk_per_trade_pct=config.max_risk_per_trade_pct,
            min_confidence=config.ensemble_confidence_threshold,
        ))
        
        # Sub-strategies
        self.mtm = mtm_strategy
        self.mrb = mrb_strategy
        self.mlb = mlb_strategy
        
        # Weights
        self.weights = STRATEGY_WEIGHTS
    
    def required_features(self) -> List[str]:
        """All features from sub-strategies"""
        features = []
        if self.mtm:
            features.extend(self.mtm.required_features())
        if self.mrb:
            features.extend(self.mrb.required_features())
        if self.mlb:
            features.extend(self.mlb.required_features())
        return list(set(features))  # Deduplicate
    
    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: Dict[str, List],
        indicators: Optional[Dict[str, Any]] = None,
        regime: Optional[RegimeType] = None
    ) -> Optional[Signal]:
        """Generate ensemble signal"""
        
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
        
        # Calculate ensemble decision
        decision, confidence, details = get_ensemble_signal(
            mtm_signal, mrb_signal, mlb_signal, regime, self.weights
        )
        
        # Check if we should trade
        if decision not in [DecisionType.BUY, DecisionType.SELL]:
            return None
        
        # Get price
        current_price = Decimal(str(ohlcv_data.get("close", [0])[-1]))
        
        # Get consensus levels
        direction = "buy" if decision == DecisionType.BUY else "sell"
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
            notes=f"Ensemble signal: {decision.value} with {confidence:.2f} confidence"
        )
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Get stats from all sub-strategies"""
        stats = {
            "ensemble": self.get_stats(),
        }
        
        if self.mtm:
            stats["mtm"] = self.mtm.get_stats()
        if self.mrb:
            stats["mrb"] = self.mrb.get_stats()
        if self.mlb:
            stats["mlb"] = self.mlb.get_stats()
        
        return stats
