"""Symbol registry — maps symbols to asset classes and trading metadata.

Provides the mapping layer between raw MT5 symbol strings and the
risk engine's asset-class awareness.  Also supplies sanity-check data
(pip value, lot size, typical price range) used by order validation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolInfo:
    """Static metadata for a trading symbol."""

    asset_class: str
    pip_value: float
    typical_lot_size: float
    typical_price_range: tuple[float, float]


_SYMBOLS: dict[str, SymbolInfo] = {
    "XAUUSD": SymbolInfo("metals", 0.01, 100.0, (1500.0, 5000.0)),
    "XAGUSD": SymbolInfo("metals", 0.01, 5000.0, (15.0, 50.0)),
    "BTCUSD": SymbolInfo("crypto", 0.01, 0.01, (10000.0, 150000.0)),
    "ETHUSD": SymbolInfo("crypto", 0.01, 0.1, (1000.0, 10000.0)),
    "SOLUSD": SymbolInfo("crypto", 0.01, 1.0, (5.0, 500.0)),
    "EURUSD": SymbolInfo("forex", 0.0001, 100000.0, (0.8000, 1.4000)),
    "GBPUSD": SymbolInfo("forex", 0.0001, 100000.0, (1.1000, 1.6000)),
    "USDJPY": SymbolInfo("forex", 0.01, 100000.0, (90.0, 170.0)),
    "US30": SymbolInfo("indices", 0.01, 1.0, (20000.0, 50000.0)),
    "NAS100": SymbolInfo("indices", 0.01, 1.0, (8000.0, 25000.0)),
    "SPX500": SymbolInfo("indices", 0.01, 1.0, (3000.0, 7000.0)),
    "XAUJPY": SymbolInfo("metals", 0.01, 100.0, (200000.0, 700000.0)),
    "XAUEUR": SymbolInfo("metals", 0.01, 100.0, (1300.0, 4500.0)),
    "USDCAD": SymbolInfo("forex", 0.0001, 100000.0, (1.2000, 1.6000)),
    "NZDUSD": SymbolInfo("forex", 0.0001, 100000.0, (0.5000, 0.9000)),
    "AUDUSD": SymbolInfo("forex", 0.0001, 100000.0, (0.6000, 1.1000)),
    "USDCHF": SymbolInfo("forex", 0.0001, 100000.0, (0.8000, 1.2000)),
    "GER40": SymbolInfo("indices", 0.01, 1.0, (10000.0, 25000.0)),
    "UK100": SymbolInfo("indices", 0.01, 1.0, (5000.0, 12000.0)),
}

_DEFAULT = SymbolInfo("unknown", 0.01, 100000.0, (0.0, 1_000_000.0))


class SymbolRegistry:
    """Registry mapping symbol strings to asset classes and trading metadata."""

    def __init__(self, overrides: dict[str, SymbolInfo] | None = None) -> None:
        self._symbols: dict[str, SymbolInfo] = {**_SYMBOLS}
        if overrides:
            self._symbols.update(overrides)

    def get_asset_class(self, symbol: str) -> str:
        return self._symbols.get(symbol, _DEFAULT).asset_class

    def get_pip_value(self, symbol: str) -> float:
        return self._symbols.get(symbol, _DEFAULT).pip_value

    def get_lot_size(self, symbol: str) -> float:
        return self._symbols.get(symbol, _DEFAULT).typical_lot_size

    def get_price_range(self, symbol: str) -> tuple[float, float]:
        return self._symbols.get(symbol, _DEFAULT).typical_price_range

    def get_info(self, symbol: str) -> SymbolInfo:
        return self._symbols.get(symbol, _DEFAULT)

    def is_known(self, symbol: str) -> bool:
        return symbol in self._symbols

    def list_symbols(self) -> list[str]:
        return list(self._symbols.keys())

    def list_by_class(self, asset_class: str) -> list[str]:
        return [s for s, info in self._symbols.items() if info.asset_class == asset_class]

    def validate_price(self, symbol: str, price: float) -> bool:
        lo, hi = self.get_price_range(symbol)
        return lo <= price <= hi

    def register(self, symbol: str, info: SymbolInfo) -> None:
        self._symbols[symbol] = info

    def unregister(self, symbol: str) -> bool:
        return self._symbols.pop(symbol, None) is not None
