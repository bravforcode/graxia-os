"""Trading strategies module"""

from .base import HyperparameterRange, Signal, Strategy, StrategyConfig, TradeResult
from .carry import CarrySignal, compute_carry_signal
from .ensemble import EnsembleResult, EnsembleVote, StrategyEnsemble
from .factor_signals import FactorSignal, compute_factor_signals
from .mlb import MLBreakout
from .mrb import MeanReversionBollinger
from .mtm import MultiTimeframeMomentum
from .pairs_mr import PairsMRSignal, compute_pairs_mr_signal
from .tsmom import TSMOMSignal, compute_tsmom_signal
from .walk_forward import (
    StrategyComparison,
    WalkForwardFold,
    WalkForwardResults,
    WalkForwardValidator,
)

__all__ = [
    "Strategy",
    "Signal",
    "StrategyConfig",
    "TradeResult",
    "HyperparameterRange",
    "MultiTimeframeMomentum",
    "MeanReversionBollinger",
    "MLBreakout",
    "StrategyEnsemble",
    "EnsembleResult",
    "EnsembleVote",
    "WalkForwardValidator",
    "WalkForwardResults",
    "WalkForwardFold",
    "StrategyComparison",
    "TSMOMSignal",
    "compute_tsmom_signal",
    "CarrySignal",
    "compute_carry_signal",
    "PairsMRSignal",
    "compute_pairs_mr_signal",
    "FactorSignal",
    "compute_factor_signals",
]
