"""
Live Readiness - Phase 3.2

Read-only MT5 client and snapshot services for autonomous trading.
CRITICAL: No order submission in this package.
"""

__all__ = [
    "Mt5ReadOnlyClient",
    "Mt5UnavailableError",
    "AccountSnapshot",
    "take_account_snapshot",
    "SymbolSnapshot",
    "take_symbol_snapshot",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular import issues with MT5 safety assertions."""
    if name in ("Mt5ReadOnlyClient", "Mt5UnavailableError"):
        from .mt5_readonly_client import Mt5ReadOnlyClient, Mt5UnavailableError
        return Mt5ReadOnlyClient if name == "Mt5ReadOnlyClient" else Mt5UnavailableError
    if name in ("AccountSnapshot", "take_account_snapshot"):
        from .account_snapshot_service import AccountSnapshot, take_account_snapshot
        return AccountSnapshot if name == "AccountSnapshot" else take_account_snapshot
    if name in ("SymbolSnapshot", "take_symbol_snapshot"):
        from .symbol_snapshot_service import SymbolSnapshot, take_symbol_snapshot
        return SymbolSnapshot if name == "SymbolSnapshot" else take_symbol_snapshot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
