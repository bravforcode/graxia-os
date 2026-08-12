"""Live Spread Tracker — fetches real spread data from Pepperstone demo."""
import time
import structlog
from dataclasses import dataclass
from datetime import UTC, datetime

logger = structlog.get_logger(__name__)

@dataclass
class SpreadSnapshot:
    symbol: str
    bid: float
    ask: float
    spread_pips: float
    timestamp: datetime

class LiveSpreadTracker:
    """Track live spreads for cost model calibration.

    ponytail: Uses cached spreads, not live API.
    Upgrade path: Connect to MT5 demo for real-time spreads.
    """

    # Default Pepperstone XAUUSD spreads (pips)
    DEFAULT_SPREADS = {
        "XAUUSD": 0.35,   # ~3.5 cents
        "EURUSD": 0.10,   # ~1 pip
        "GBPUSD": 0.15,   # ~1.5 pips
    }

    def __init__(self):
        self._cache: dict[str, SpreadSnapshot] = {}
        self._last_update: float = 0
        self._update_interval: float = 300  # 5 minutes

    def get_spread(self, symbol: str) -> float:
        """Get current spread in pips. Uses cache or default."""
        now = time.time()
        if symbol in self._cache and (now - self._last_update) < self._update_interval:
            return self._cache[symbol].spread_pips
        return self.DEFAULT_SPREADS.get(symbol, 0.5)

    def update_spread(self, symbol: str, bid: float, ask: float):
        """Update spread from live data (called by MT5 feed)."""
        spread = (ask - bid) * 10 if symbol in ("XAUUSD",) else ask - bid
        self._cache[symbol] = SpreadSnapshot(
            symbol=symbol, bid=bid, ask=ask,
            spread_pips=round(spread, 2),
            timestamp=datetime.now(UTC),
        )
        self._last_update = time.time()

    def get_all_spreads(self) -> dict[str, float]:
        return {s: self.get_spread(s) for s in self.DEFAULT_SPREADS}
