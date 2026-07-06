"""
Unified feature engineering interface.
Single source of truth for OHLCV feature generation.

Usage:
    from core.features import build_features

    # From DataFrame
    df_feat = build_features(df)

    # From dict (canonical FeatureEngineer input)
    df_feat = build_features({"open": [...], "high": [...], ...})

    # Get FeatureSet (with labels) for ML training
    from core.features import build_feature_set
    feature_set = build_feature_set(df)
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

try:
    from ml.pipeline import FeatureEngineer, FeatureSet
except ImportError:
    from graxia.packages.quant_os.ml.pipeline import FeatureEngineer, FeatureSet

__all__ = ["build_features", "build_feature_set", "FeatureEngineer", "FeatureSet"]

_ENGINEER = FeatureEngineer()


def _df_to_ohlcv_dict(df: pd.DataFrame) -> dict[str, list]:
    """Convert DataFrame to OHLCV dict format expected by FeatureEngineer."""
    cols = {c.lower() for c in df.columns}
    required = {"open", "high", "low", "close"}
    if not required.issubset(cols):
        missing = required - cols
        raise ValueError(f"Missing OHLCV columns: {missing}")

    out = {}
    for col in ("open", "high", "low", "close"):
        matching = [c for c in df.columns if c.lower() == col]
        out[col] = df[matching[0]].tolist()

    # Volume: use 'volume' or 'tick_volume', default 0
    if "volume" in cols:
        vol_col = [c for c in df.columns if c.lower() == "volume"][0]
        out["volume"] = df[vol_col].tolist()
    elif "tick_volume" in cols:
        vol_col = [c for c in df.columns if c.lower() == "tick_volume"][0]
        out["volume"] = df[vol_col].tolist()
    else:
        out["volume"] = [0.0] * len(df)

    return out


def _timestamps_from_df(df: pd.DataFrame) -> list[datetime] | None:
    """Extract timestamps from DataFrame index or 'time' column."""
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index.to_pydatetime().tolist()
    if "time" in df.columns:
        return pd.to_datetime(df["time"]).tolist()
    return None


def build_feature_set(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    timeframe: str = "H1",
) -> FeatureSet:
    """Build FeatureSet from OHLCV DataFrame.

    Args:
        df: DataFrame with open/high/low/close/volume columns.
        symbol: Symbol name for metadata.
        timeframe: Timeframe string for metadata.

    Returns:
        FeatureSet with features, labels, timestamps, feature_names.
    """
    ohlcv = _df_to_ohlcv_dict(df)
    timestamps = _timestamps_from_df(df)
    fs = _ENGINEER.generate_features(ohlcv, timestamps=timestamps)
    fs.symbol = symbol
    fs.timeframe = timeframe
    return fs


def build_features(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    timeframe: str = "H1",
) -> pd.DataFrame:
    """Build features from OHLCV DataFrame, returned as DataFrame.

    Convenience wrapper that returns a DataFrame with feature columns
    appended, suitable for script-level use.

    Args:
        df: DataFrame with open/high/low/close/volume columns.
        symbol: Symbol name for metadata.
        timeframe: Timeframe string for metadata.

    Returns:
        DataFrame with feature columns added (NaN rows trimmed).
    """
    fs = build_feature_set(df, symbol=symbol, timeframe=timeframe)

    feat_df = pd.DataFrame(fs.features)

    # Align with original index if lengths match
    valid_start = len(df) - len(feat_df)
    if valid_start > 0 and isinstance(df.index, pd.DatetimeIndex):
        feat_df.index = df.index[valid_start:]
    elif "time" in df.columns:
        time_col = pd.to_datetime(df["time"])
        feat_df.index = time_col.iloc[valid_start:].values

    # Merge original OHLCV columns back (for downstream target creation)
    ohlcv_cols = [
        c for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "tick_volume", "time")
    ]
    for col in ohlcv_cols:
        if col not in feat_df.columns:
            feat_df[col] = df[col].iloc[valid_start:].values

    return feat_df
