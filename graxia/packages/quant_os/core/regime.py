"""
Unified regime detection interface.

Single source of truth for regime detection across the system.
Canonical implementation lives in validation/regime_detector.py.

This module re-exports it for convenient access from core/.
"""

from graxia.packages.quant_os.validation.regime_detector import (
    CorrelationRegime,
    RegimeConfig,
    RegimeDetector,
    RegimeState,
    VolRegime,
)

__all__ = [
    "RegimeDetector",
    "RegimeConfig",
    "RegimeState",
    "VolRegime",
    "CorrelationRegime",
    "create_regime_detector",
]


def create_regime_detector(
    vol_lookback_short: int = 20,
    vol_lookback_long: int = 200,
    vol_low_threshold: float = 0.7,
    vol_elevated_threshold: float = 1.3,
    vol_stressed_threshold: float = 2.0,
    corr_lookback: int = 60,
    corr_elevated_threshold: float = 0.5,
    corr_crisis_threshold: float = 0.7,
) -> RegimeDetector:
    """Create a regime detector with standard configuration.

    All parameters have sensible defaults matching RegimeConfig.
    Override only what you need.
    """
    config = RegimeConfig(
        vol_lookback_short=vol_lookback_short,
        vol_lookback_long=vol_lookback_long,
        vol_low_threshold=vol_low_threshold,
        vol_elevated_threshold=vol_elevated_threshold,
        vol_stressed_threshold=vol_stressed_threshold,
        corr_lookback=corr_lookback,
        corr_elevated_threshold=corr_elevated_threshold,
        corr_crisis_threshold=corr_crisis_threshold,
    )
    return RegimeDetector(config=config)
