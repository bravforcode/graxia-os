"""Core cost model — per-asset-class pricing for backtest and live parity.

Bug #2 fix: v2.0 treated XAUUSD like an FX pair with spread + flat
per-side commission. On Pepperstone Razor, commission on metals is
embedded in the quoted spread — charging both double-counts the cost.

This module provides:
- Per-asset-class CostParams (METALS, FOREX, CRYPTO)
- Live round-trip cost from MT5 ask-bid
- Session-based cost estimates for backtesting (spreads widen in Asian)
- Hour-of-day UTC session classifier
- XAUUSD stress scenario at 72 bps (regulatory stress test)

Migration note: execution/cost_model.py handles per-trade cost calculation
with CostScenario. This module handles per-asset-class cost parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

from .live_spread import LiveSpreadTracker

# ── Per-Asset-Class Cost Parameters ──────────────────────────────────────────


@dataclass(frozen=True)
class CostParams:
    """Cost parameters for an asset class.

    Attributes:
        name: Human-readable name (e.g. "METALS", "FOREX", "CRYPTO").
        spread_bps: Typical round-trip spread in basis points.
        commission_per_lot: Commission per lot round-trip (0 for Pepperstone metals).
        slippage_bps: Typical slippage in basis points.
        swap_long_bps: Daily swap cost for long positions in bps.
        swap_short_bps: Daily swap cost for short positions in bps.
    """

    name: str
    spread_bps: float
    commission_per_lot: float = 0.0
    slippage_bps: float = 0.5
    swap_long_bps: float = 0.0
    swap_short_bps: float = 0.0


# Pepperstone Razor cost parameters (calibrated June 2026)
METALS = CostParams(
    name="METALS",
    spread_bps=12.0,  # ~0.12% round-trip for XAUUSD
    commission_per_lot=0.0,  # Commission embedded in spread
    slippage_bps=0.5,
    swap_long_bps=-0.5,  # Negative = cost
    swap_short_bps=0.2,
)

FOREX = CostParams(
    name="FOREX",
    spread_bps=1.0,  # ~0.0001 * 2 for EURUSD
    commission_per_lot=7.0,  # $7 round-trip commission
    slippage_bps=0.3,
    swap_long_bps=-0.1,
    swap_short_bps=-0.1,
)

CRYPTO = CostParams(
    name="CRYPTO",
    spread_bps=5.0,  # ~0.05% for BTCUSD
    commission_per_lot=0.0,  # Commission embedded in spread
    slippage_bps=2.0,  # Higher slippage for crypto
    swap_long_bps=-10.0,  # High funding cost
    swap_short_bps=-5.0,
)

INDICES = CostParams(
    name="INDICES",
    spread_bps=3.0,  # ~3 bps for major indices
    commission_per_lot=5.0,  # $5 round-trip commission
    slippage_bps=1.0,
    swap_long_bps=-0.2,
    swap_short_bps=-0.2,
)

# XAUUSD stress scenario: 72 bps (regulatory stress test)
XAUUSD_STRESS_72BPS = CostParams(
    name="XAUUSD_STRESS_72BPS",
    spread_bps=72.0,  # 72 basis points stress
    commission_per_lot=0.0,
    slippage_bps=5.0,  # Elevated slippage under stress
    swap_long_bps=-2.0,
    swap_short_bps=1.0,
)

# Symbol -> asset class mapping
_SYMBOL_TO_PARAMS: dict[str, CostParams] = {
    # Metals
    "XAUUSD": METALS,
    "SILVER": METALS,
    "XAGUSD": METALS,
    # Forex majors
    "EURUSD": FOREX,
    "GBPUSD": FOREX,
    "USDJPY": FOREX,
    "AUDUSD": FOREX,
    "USDCAD": FOREX,
    "USDCHF": FOREX,
    "NZDUSD": FOREX,
    # Crypto
    "BTCUSD": CRYPTO,
    "BTCUSDT": CRYPTO,
    "ETHUSD": CRYPTO,
    "ETHUSDT": CRYPTO,
}


def get_cost_params(symbol: str) -> CostParams:
    """Get cost parameters for a symbol.

    Args:
        symbol: Instrument symbol (e.g. "XAUUSD", "EURUSD").

    Returns:
        CostParams for the asset class, or METALS as safe default.
    """
    return _SYMBOL_TO_PARAMS.get(symbol.upper(), METALS)


# ── Session-Based Cost Estimation (Legacy) ──────────────────────────────────

COST_PER_TRADE_BY_SESSION: dict[str, float] = {
    "asian": 0.28,
    "london": 0.14,
    "ny": 0.15,
    "overlap": 0.12,
}

_SESSION_HOURS: dict[str, tuple[int, int]] = {
    "asian": (0, 7),
    "london": (7, 12),
    "overlap": (12, 16),
    "ny": (16, 21),
}

_spread_tracker = LiveSpreadTracker()


def get_session(hour_utc: Optional[int] = None) -> str:
    """Classify the current (or given) UTC hour into a trading session.

    Session windows (UTC):
        asian:   00:00–07:00
        london:  07:00–12:00
        overlap: 12:00–16:00  (London/NY overlap)
        ny:      16:00–21:00
        rollover/after: falls back to "asian"

    Args:
        hour_utc: UTC hour (0–23). If None, uses current UTC time.

    Returns:
        Session name: "asian", "london", "overlap", or "ny".
    """
    if hour_utc is None:
        hour_utc = datetime.now(UTC).hour

    for session, (start, end) in _SESSION_HOURS.items():
        if start <= hour_utc < end:
            return session
    return "asian"


def get_backtest_cost(symbol: str = "XAUUSD", timestamp: Optional[datetime] = None) -> float:
    """Session-aware backtest round-trip cost for a given timestamp.

    Uses live spread if available (via LiveSpreadTracker), otherwise
    falls back to session-based COST_PER_TRADE_BY_SESSION.

    Args:
        symbol: Instrument symbol.
        timestamp: UTC-aware datetime to determine session.

    Returns:
        Round-trip cost in dollars for 0.01 lot (1 oz for metals).
    """
    live_spread = _spread_tracker.get_spread(symbol)
    if live_spread > 0:
        return live_spread

    hour = timestamp.hour if timestamp and timestamp.tzinfo else (timestamp.hour if timestamp else None)
    session = get_session(hour)
    return COST_PER_TRADE_BY_SESSION.get(session, COST_PER_TRADE_BY_SESSION["asian"])


def get_live_round_trip_cost(symbol: str = "XAUUSD") -> Optional[float]:
    """Pull live round-trip cost from MT5 terminal ask-bid.

    For Pepperstone Razor XAUUSD, commission is embedded in the spread.
    The round-trip cost is simply (ask - bid) — you pay the spread once
    on entry; closing is at the prevailing bid/ask.

    Returns:
        Spread in dollars (price units for XAUUSD), or None if MT5 unavailable.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None

    return float(tick.ask - tick.bid)


def get_live_spread_as_return(symbol: str = "XAUUSD") -> Optional[float]:
    """Get live spread as a fraction of price (return units).

    Useful for converting between dollar cost and return-unit cost
    used in the walk-forward pipeline.

    Returns:
        (ask - bid) / mid_price, or None if MT5 unavailable.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None

    mid = (tick.ask + tick.bid) / 2.0
    if mid <= 0:
        return None
    return float((tick.ask - tick.bid) / mid)


# ── Backward Compatibility ──────────────────────────────────────────────────

# Re-export for tests that import from core.cost_model
__all__ = [
    "CostParams",
    "METALS",
    "FOREX",
    "CRYPTO",
    "XAUUSD_STRESS_72BPS",
    "get_cost_params",
    "get_session",
    "get_backtest_cost",
    "get_live_round_trip_cost",
    "get_live_spread_as_return",
    "COST_PER_TRADE_BY_SESSION",
]
