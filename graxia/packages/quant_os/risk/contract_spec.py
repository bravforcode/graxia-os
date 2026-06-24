"""
Contract Specification resolution from broker runtime data.

No global default for units_per_lot. Every symbol must resolve its
ContractSpec from the runtime broker symbol snapshot.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
        ts = self.snapshot_timestamp
        # ponytail: tolerance for naive stamps from callers still on utcnow()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > CONTRACT_SPEC_TTL_SECONDS

    @property
    def hash(self) -> str:
        """Deterministic content hash."""
        raw = f"{self.symbol}:{self.contract_size}:{self.volume_min}:{self.volume_max}:{self.volume_step}:{self.point}:{self.tick_size}:{self.tick_value}:{self.currency_profit}:{self.currency_margin}:{self.stops_level}:{self.freeze_level}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ── Unit Semantics ────────────────────────────────────────────────
    # These methods disambiguate "point" (MT5 raw unit) from "price_delta"
    # (USD change).  On XAUUSD point=0.01, a $10 price change is 1000
    # MT5 points.  Previously the code and reports conflated the two,
    # calling $10 "10pt" — this is the canonical fix.

    @staticmethod
    def price_delta(price_from: float, price_to: float) -> float:
        """Absolute USD price change between two price levels.

        Example: price_delta(2000, 1990) = $10.00
        """
        return abs(price_from - price_to)

    def to_mt5_points(self, price_delta: float) -> int:
        """Raw MT5 point count for a given price delta.

        XAUUSD (point=0.01):  to_mt5_points(10.00) → 1000
        EURUSD (point=1e-5):  to_mt5_points(0.0010) → 100
        """
        if self.point == 0:
            return 0
        return int(round(price_delta / self.point))

    def to_tick_count(self, price_delta: float) -> int:
        """Number of ticks = price_delta / tick_size.

        For most symbols tick_size == point, so tick_count == mt5_points.
        """
        if self.tick_size == 0:
            return 0
        return int(round(price_delta / self.tick_size))

    def supports_pips(self) -> bool:
        """Whether this symbol has a standard pip definition.

        Forex pairs (EURUSD, GBPUSD, etc.) support pips.
        Metals (XAUUSD, XAGUSD, XAU*, XAG*) and CFDs do not.
        """
        if self.symbol.startswith("XAU") or self.symbol.startswith("XAG"):
            return False
        if "CFD" in self.symbol.upper() or "METAL" in self.symbol.upper():
            return False
        return True

    def to_pips(self, price_delta: float) -> Optional[float]:
        """Convert a price delta to pips.

        1 pip = 10 points for standard forex.
        XAUUSD does NOT have a standard pip definition; this is most
        meaningful for forex pairs like EURUSD.

        Returns None for symbols without standard pip definitions (metals, CFDs).

        EURUSD (point=1e-5): to_pips(0.0010) → 10.0  (10 pip = 100 pt)
        XAUUSD: to_pips(...) → None
        """
        if not self.supports_pips():
            return None
        if self.point == 0:
            return 0.0
        return price_delta / (self.point * 10)


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
            snapshot_timestamp=datetime.now(timezone.utc),
        )

        self._cache[symbol] = spec
        return spec

    def resolve_or_fail(self, symbol: str, profile_hash: str = "") -> ContractSpec:
        """Resolve ContractSpec. Fail CLOSED if missing/stale/mismatched."""
        spec = self.resolve(symbol, profile_hash)
        if spec is None:
            raise ContractSpecError(f"ContractSpec not found for {symbol}", symbol)
        if spec.is_stale:
            raise ContractSpecError(f"ContractSpec stale for {symbol}", symbol)
        return spec

    def clear_cache(self):
        self._cache = {}


class ContractSpecError(Exception):
    def __init__(self, message: str, symbol: str):
        self.symbol = symbol
        super().__init__(f"ContractSpec[{symbol}]: {message}")
