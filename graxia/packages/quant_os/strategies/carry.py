"""
Carry signal — interest rate differential.
Profit from holding high-yield currencies vs low-yield.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CarrySignal:
    """Carry signal result."""

    signal: pd.Series  # Signal: -1, 0, +1
    carry: pd.Series  # Raw carry (interest rate diff)
    strength: pd.Series  # Signal strength


def compute_carry_signal(
    base_rate: pd.Series,
    quote_rate: pd.Series,
    vol_target: float = 0.10,
) -> CarrySignal:
    """
    Compute carry signal from interest rate differential.

    Args:
        base_rate: Interest rate series for base currency
        quote_rate: Interest rate series for quote currency
        vol_target: Annualized vol target

    Returns:
        CarrySignal with signal and carry
    """
    carry = base_rate - quote_rate
    signal = np.sign(carry)

    max_carry = carry.abs().rolling(252, min_periods=1).max()
    strength = carry.abs() / max_carry.clip(lower=0.01)

    return CarrySignal(
        signal=signal,
        carry=carry,
        strength=strength,
    )
