"""Symbol Registry — single source of truth for symbol-to-asset-class mapping.

Every module that maps symbols to asset classes MUST import from here.
Do NOT define local copies of this mapping.
"""

_SYMBOL_TO_ASSET_CLASS: dict[str, str] = {
    # Metals
    "XAUUSD": "metals",
    "XAGUSD": "metals",
    "GOLD": "metals",
    # Indices
    "US30": "indices",
    "NAS100": "indices",
    "US100": "indices",
    "USTEC": "indices",
    "SPX500": "indices",
    "US500": "indices",
    "DAX40": "indices",
    "DE40": "indices",
    # Energy
    "USOIL": "energy",
    "UKOIL": "energy",
    "NGAS": "energy",
    # Forex
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "USDCHF": "forex",
    "AUDUSD": "forex",
    "NZDUSD": "forex",
    "USDCAD": "forex",
    "EURAUD": "forex",
    "EURGBP": "forex",
    "EURJPY": "forex",
    "GBPJPY": "forex",
    "AUDJPY": "forex",
    # Crypto
    "BTCUSD": "crypto",
    "ETHUSD": "crypto",
    "SOLUSD": "crypto",
}


def symbol_to_asset_class(symbol: str) -> str:
    """Get asset class for a symbol. Returns 'unknown' if not found."""
    return _SYMBOL_TO_ASSET_CLASS.get(symbol.upper(), "unknown")


def get_all_symbols() -> dict[str, str]:
    """Return all registered symbols."""
    return dict(_SYMBOL_TO_ASSET_CLASS)
