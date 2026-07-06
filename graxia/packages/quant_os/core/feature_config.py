"""
Centralized feature exclusion list.
Single source of truth for all feature columns that should be excluded from model training.

Import this in every script that trains ML models:
    from core.feature_config import EXCLUDE_COLS, get_feature_cols
"""

# Columns that MUST be excluded from model features
# These are either: (a) leakage, (b) identifiers, (c) targets, (d) non-predictive
EXCLUDE_COLS = frozenset(
    {
        # Leakage - future information
        "target",
        "target_return",
        "target_3class",
        "future_return",
        "forward_return",
        "label",
        # Identifiers - non-predictive
        "timestamp",
        "date",
        "datetime",
        "time",
        "bar_index",
        "symbol",
        "instrument",
        "ticker",
        # Raw price data - causes memorization
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "tick_count",
        # Equity curve - not a feature
        "equity",
        "balance",
        "margin",
        "free_margin",
        # Already encoded - redundant
        "side_long",
        "side_short",
        # Triple-barrier labels
        "tb_label",
        "tb_bar_hit",
        "tb_side",
        "tb_ret",
        "tb_k_upper",
        "tb_k_lower",
        # Frequency/metadata
        "freq",
        # Mega model specific leakage
        "is_long",
        "next_bar_return",
        "target_class",
        "fwd_ret_1bar",
        "fwd_ret_5bar",
        "fwd_ret_10bar",
        "fwd_ret_15bar",
    }
)


def get_feature_cols(df_columns: list[str]) -> list[str]:
    """
    Get feature columns from a DataFrame, excluding EXCLUDE_COLS.

    Args:
        df_columns: List of column names from the DataFrame

    Returns:
        List of feature column names (excluding target and non-predictive columns)
    """
    return [col for col in df_columns if col not in EXCLUDE_COLS]


def validate_features(df_columns: list[str]) -> dict:
    """
    Validate feature columns and report any issues.

    Returns:
        Dict with 'valid', 'excluded', 'leakage_risk' keys
    """
    excluded = [col for col in df_columns if col in EXCLUDE_COLS]
    leakage_risk = [col for col in df_columns if col.lower().startswith(("target", "future", "forward"))]

    return {
        "valid": [col for col in df_columns if col not in EXCLUDE_COLS],
        "excluded": excluded,
        "leakage_risk": leakage_risk,
        "total_features": len(df_columns),
        "usable_features": len(df_columns) - len(excluded),
    }
