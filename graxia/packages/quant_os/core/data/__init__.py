"""Core data layer — FRED, COT, macro features, point-in-time store."""

from .fred_client import FredClient
from .cot_reports import fetch_cot_gold, fetch_cot_gold_range
from .macro_features import build_macro_features
from .point_in_time_store import PointInTimeStore

__all__ = [
    "FredClient",
    "fetch_cot_gold",
    "fetch_cot_gold_range",
    "build_macro_features",
    "PointInTimeStore",
]
