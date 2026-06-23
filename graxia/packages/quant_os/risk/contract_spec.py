"""
Contract Specification resolution from broker runtime data.

No global default for units_per_lot. Every symbol must resolve its
ContractSpec from the runtime broker symbol snapshot.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import logging

logger = logging.getLogger(__name__)

CONTRACT_SPEC_TTL_SECONDS = 300  # 5 minute freshness


@dataclass(frozen=True)
class ContractSpec:
    """Immutable contract specification from broker snapshot."""
    symbol: str
    contract_size: int
    volume_min: float
    volume_max: float
    volume_step: float
    point: float
    tick_size: float
    tick_value: float
    currency_profit: str
    currency_margin: str
    stops_level: int
    freeze_level: int
    profile_hash: str
    snapshot_timestamp: datetime

    @property
    def is_stale(self) -> bool:
        age = (datetime.utcnow() - self.snapshot_timestamp).total_seconds()
        return age > CONTRACT_SPEC_TTL_SECONDS

    @property
    def hash(self) -> str:
        """Deterministic content hash."""
        raw = f"{self.symbol}:{self.contract_size}:{self.volume_min}:{self.volume_max}:{self.volume_step}:{self.point}:{self.tick_size}:{self.tick_value}:{self.currency_profit}:{self.currency_margin}:{self.stops_level}:{self.freeze_level}"
        return hashlib.sha256(raw.encode()).hexdigest()


class ContractSpecResolver:
    """Resolves ContractSpec from MT5 runtime snapshot.

    Never falls back to a global default. Missing/stale → fail closed.
    """

    def __init__(self, mt5_connection=None):
        self._mt5 = mt5_connection
        self._cache: dict[str, ContractSpec] = {}

    def set_connection(self, mt5_connection):
        self._mt5 = mt5_connection

    def resolve(self, symbol: str, profile_hash: str = "") -> ContractSpec:
        """Resolve contract spec for symbol. Fail closed if unavailable."""
        if self._mt5 is None:
            raise ContractSpecError("No MT5 connection available", symbol)

        # Try cache first (if fresh)
        cached = self._cache.get(symbol)
        if cached and not cached.is_stale and cached.hash:
            return cached

        # Fetch from broker runtime
        sym_info = self._mt5.symbol_info(symbol)
        if sym_info is None:
            raise ContractSpecError(f"symbol_info() returned None for {symbol}", symbol)

        spec = ContractSpec(
            symbol=symbol,
            contract_size=sym_info.trade_contract_size,
            volume_min=sym_info.volume_min,
            volume_max=sym_info.volume_max,
            volume_step=sym_info.volume_step,
            point=sym_info.point,
            tick_size=sym_info.trade_tick_size,
            tick_value=sym_info.trade_tick_value,
            currency_profit=sym_info.currency_profit,
            currency_margin=sym_info.currency_margin,
            stops_level=sym_info.trade_stops_level,
            freeze_level=sym_info.trade_freeze_level,
            profile_hash=profile_hash,
            snapshot_timestamp=datetime.utcnow(),
        )

        self._cache[symbol] = spec
        return spec

    def clear_cache(self):
        self._cache = {}


class ContractSpecError(Exception):
    def __init__(self, message: str, symbol: str):
        self.symbol = symbol
        super().__init__(f"ContractSpec[{symbol}]: {message}")
