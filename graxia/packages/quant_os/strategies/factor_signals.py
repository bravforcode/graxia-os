"""
Unified factor signal interface.
Combines TSMOM, Carry, and Pairs MR signals.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .carry import CarrySignal, compute_carry_signal
from .pairs_mr import PairsMRSignal, compute_pairs_mr_signal
from .tsmom import TSMOMSignal, compute_tsmom_signal


@dataclass
class FactorSignal:
    """Combined factor signal."""

    tsmom: TSMOMSignal
    carry: CarrySignal | None
    pairs_mr: PairsMRSignal | None
    combined_signal: pd.Series  # Weighted combination
    confidence: pd.Series  # Signal confidence 0-1


def compute_factor_signals(
    close: pd.Series,
    base_rate: pd.Series | None = None,
    quote_rate: pd.Series | None = None,
    pairs_price: pd.Series | None = None,
    tsmom_weight: float = 0.5,
    carry_weight: float = 0.3,
    pairs_weight: float = 0.2,
) -> FactorSignal:
    """
    Compute combined factor signals.

    Args:
        close: Price series
        base_rate: Interest rate for base currency (optional)
        quote_rate: Interest rate for quote currency (optional)
        pairs_price: Price of paired asset for mean-reversion (optional)
        tsmom_weight: Weight for TSMOM signal
        carry_weight: Weight for Carry signal
        pairs_weight: Weight for Pairs MR signal

    Returns:
        FactorSignal with combined signal
    """
    tsmom = compute_tsmom_signal(close)

    carry = None
    if base_rate is not None and quote_rate is not None:
        carry = compute_carry_signal(base_rate, quote_rate)

    pairs_mr = None
    if pairs_price is not None:
        pairs_mr = compute_pairs_mr_signal(close, pairs_price)

    signals = tsmom.signal * tsmom_weight
    weights = tsmom_weight

    if carry is not None:
        signals += carry.signal * carry_weight
        weights += carry_weight

    if pairs_mr is not None:
        signals += pairs_mr.signal * pairs_weight
        weights += pairs_weight

    combined = signals / weights if weights > 0 else signals
    confidence = combined.abs()

    return FactorSignal(
        tsmom=tsmom,
        carry=carry,
        pairs_mr=pairs_mr,
        combined_signal=np.sign(combined),
        confidence=confidence,
    )
