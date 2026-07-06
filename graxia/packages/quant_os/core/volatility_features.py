"""
Volatility features for HAR model.
V1-V7: Parkinson, Garman-Klass, realized vol, vol-of-vol, etc.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class VolatilityFeatures:
    """Container for volatility feature vectors."""

    parkinson: pd.Series  # V1: Parkinson (high-low) vol
    garman_klass: pd.Series  # V2: Garman-Klass vol
    realized_vol: pd.Series  # V3: Realized (close-to-close) vol
    vol_of_vol: pd.Series  # V4: Volatility of volatility
    vol_regime: pd.Series  # V5: Vol regime (LOW/MED/HIGH)
    vol_ratio: pd.Series  # V6: Short/long vol ratio
    vol_autocorr: pd.Series  # V7: Vol autocorrelation


def compute_parkinson_vol(high: pd.Series, low: pd.Series, window: int = 20) -> pd.Series:
    """
    Parkinson (1980) volatility estimator.
    Uses high-low range, 5.2x more efficient than close-to-close.
    """
    log_hl = np.log(high / low)
    return np.sqrt((log_hl**2).rolling(window).mean() / (4 * np.log(2)))


def compute_garman_klass_vol(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Garman-Klass (1980) volatility estimator.
    Uses OHLC, 8x more efficient than close-to-close.
    """
    log_hl = np.log(high / low)
    log_co = np.log(close / open_)
    return np.sqrt((0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2).rolling(window).mean())


def compute_realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Realized (close-to-close) volatility, annualized."""
    returns = np.log(close / close.shift(1))
    return returns.rolling(window).std() * np.sqrt(252)


def compute_vol_of_vol(vol: pd.Series, window: int = 20) -> pd.Series:
    """Volatility of volatility — how much vol itself fluctuates."""
    return vol.rolling(window).std()


def compute_vol_regime(vol: pd.Series, window: int = 252) -> pd.Series:
    """
    Classify vol regime as LOW/MED/HIGH based on historical percentiles.
    """
    percentile = vol.rolling(window).rank(pct=True)
    return pd.cut(percentile, bins=[0, 0.33, 0.67, 1.0], labels=["LOW", "MED", "HIGH"])


def compute_vol_ratio(vol_short: pd.Series, vol_long: pd.Series) -> pd.Series:
    """Short/long vol ratio — >1 means vol expanding."""
    return vol_short / vol_long


def compute_vol_autocorr(vol: pd.Series, window: int = 20, lag: int = 1) -> pd.Series:
    """Vol autocorrelation — high means vol clusters."""
    return vol.rolling(window).apply(lambda x: pd.Series(x).autocorr(lag=lag), raw=False)


def build_volatility_features(df: pd.DataFrame, windows: list[int] = [5, 20, 60]) -> VolatilityFeatures:
    """
    Build all volatility features from OHLCV DataFrame.

    Args:
        df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
        windows: List of lookback windows for multi-scale features

    Returns:
        VolatilityFeatures with all V1-V7 computed
    """
    w = windows[0]

    parkinson = compute_parkinson_vol(df["high"], df["low"], w)
    garman_klass = compute_garman_klass_vol(df["open"], df["high"], df["low"], df["close"], w)
    realized_vol = compute_realized_vol(df["close"], w)
    vol_of_vol = compute_vol_of_vol(realized_vol, w)
    vol_regime = compute_vol_regime(realized_vol)

    vol_short = compute_realized_vol(df["close"], windows[0])
    vol_long = compute_realized_vol(df["close"], windows[-1])
    vol_ratio = compute_vol_ratio(vol_short, vol_long)

    vol_autocorr = compute_vol_autocorr(realized_vol, w)

    return VolatilityFeatures(
        parkinson=parkinson,
        garman_klass=garman_klass,
        realized_vol=realized_vol,
        vol_of_vol=vol_of_vol,
        vol_regime=vol_regime,
        vol_ratio=vol_ratio,
        vol_autocorr=vol_autocorr,
    )
