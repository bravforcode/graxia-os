"""Multi-Asset Manager — handles XAUUSD, EURUSD, GBPUSD."""

from dataclasses import dataclass


@dataclass
class AssetConfig:
    symbol: str
    pip_value: float          # Value of 1 pip in account currency
    spread_pips: float        # Typical spread
    session_hours: tuple      # (start_utc, end_utc)
    news_impact: str          # "high", "medium", "low"


ASSETS = {
    "XAUUSD": AssetConfig(
        symbol="XAUUSD", pip_value=0.01, spread_pips=0.35,
        session_hours=(7, 21), news_impact="high",
    ),
    "EURUSD": AssetConfig(
        symbol="EURUSD", pip_value=0.0001, spread_pips=0.10,
        session_hours=(7, 21), news_impact="medium",
    ),
    "GBPUSD": AssetConfig(
        symbol="GBPUSD", pip_value=0.0001, spread_pips=0.15,
        session_hours=(7, 21), news_impact="medium",
    ),
}


def get_asset(symbol: str) -> AssetConfig | None:
    return ASSETS.get(symbol.upper())


def get_all_symbols() -> list[str]:
    return list(ASSETS.keys())


def calculate_pip_value(symbol: str, lot_size: float) -> float:
    asset = get_asset(symbol)
    if asset is None:
        return 0.0
    return asset.pip_value * lot_size * 100000
