"""Slippage budget model — session-aware cost estimation for XAUUSD.

Provides realistic slippage estimates per trading session and volatility
regime, then combines spread + slippage + commission into a single
per-trade cost dictionary.

Slippage values are calibrated for Pepperstone Razor XAUUSD (0.01 lot = 1 oz).
All slippage figures are in *points* (price units), not pips.
1 pip XAUUSD = $0.10 = 0.1 price points.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VolatilityRegime(str, Enum):
    """Volatility regime classification for slippage scaling."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class TradingSession(str, Enum):
    """Trading session classification (UTC-based)."""

    ASIAN = "asian"
    LONDON = "london"
    NY = "ny"
    OVERLAP = "overlap"
    ROLLOVER = "rollover"


# ---------------------------------------------------------------------------
# Session → slippage mapping (price points, NOT pips)
# ---------------------------------------------------------------------------
# Asian 0.3 pips = 0.03 price points  →  3.0 in raw XAUUSD points
# London 0.2 pips = 0.02 price points  →  2.0 in raw XAUUSD points
# Overlap 0.15 pips = 0.015 price points → 1.5 in raw XAUUSD points
# Rollover 3.0 pips = 0.30 price points  → 30.0 in raw XAUUSD points
#
# BUT: the spec asks for values in "pips" so we store as pips and convert
# at the point-of-use.  Internal representation = pips.

DEFAULT_SESSION_SLIPPAGE_PIPS: dict[TradingSession, float] = {
    TradingSession.ASIAN: 0.30,  # low volatility, wider spreads
    TradingSession.LONDON: 0.20,  # high liquidity
    TradingSession.NY: 0.20,  # high liquidity
    TradingSession.OVERLAP: 0.15,  # peak liquidity
    TradingSession.ROLLOVER: 3.00,  # DANGEROUS — 5-10x normal
}

# Volatility multipliers applied on top of base session slippage.
_VOLATILITY_MULTIPLIERS: dict[VolatilityRegime, float] = {
    VolatilityRegime.LOW: 0.8,
    VolatilityRegime.NORMAL: 1.0,
    VolatilityRegime.HIGH: 1.5,
    VolatilityRegime.EXTREME: 2.5,
}

# Per-symbol overrides — only XAUUSD calibrated; others fall back to default.
_SYMBOL_SLIPPAGE_OVERRIDE: dict[str, dict[TradingSession, float]] = {}

# ---------------------------------------------------------------------------
# Symbol-specific trade cost constants (Pepperstone Razor)
# ---------------------------------------------------------------------------
# Commission on metals is *embedded* in the spread for Razor accounts.
# We expose a separate commission field for transparency but it should be
# zero for metals on Pepperstone Razor.

_SYMBOL_SPREAD_PIPS: dict[str, dict[TradingSession, float]] = {
    "XAUUSD": {
        TradingSession.ASIAN: 2.8,
        TradingSession.LONDON: 1.4,
        TradingSession.NY: 1.5,
        TradingSession.OVERLAP: 1.2,
        TradingSession.ROLLOVER: 14.0,
    },
}

_SYMBOL_COMMISSION_PER_LOT: dict[str, float] = {
    "XAUUSD": 0.0,  # embedded in spread on Pepperstone Razor
}

# pip_value(symbol, lot_size): dollar value of 1 pip
_SYMBOL_PIP_VALUE: dict[str, float] = {
    "XAUUSD": 0.10,  # 1 pip = $0.10 per 0.01 lot (1 oz)
}


# ---------------------------------------------------------------------------
# Helper: classify UTC time into a TradingSession
# ---------------------------------------------------------------------------


def classify_session(ts: datetime) -> TradingSession:
    """Classify a UTC timestamp into a trading session.

    Windows (UTC):
        rollover  : 21:55 – 22:15  (dangoues — block trades)
        asian     : 00:00 – 07:00
        london    : 07:00 – 12:00
        overlap   : 12:00 – 16:00  (London/NY overlap)
        ny        : 16:00 – 21:55

    Args:
        ts: UTC-aware datetime.

    Returns:
        TradingSession enum value.
    """
    t = ts.time()

    # Rollover dead zone — check first (highest priority)
    if time(21, 55) <= t and t < time(22, 16):
        return TradingSession.ROLLOVER

    # Standard sessions
    for session, (start, end) in _SESSION_RANGES.items():
        if start <= t < end:
            return session

    return TradingSession.ASIAN  # fallback


_SESSION_RANGES: dict[TradingSession, tuple[time, time]] = {
    TradingSession.ASIAN: (time(0, 0), time(7, 0)),
    TradingSession.LONDON: (time(7, 0), time(12, 0)),
    TradingSession.OVERLAP: (time(12, 0), time(16, 0)),
    TradingSession.NY: (time(16, 0), time(21, 55)),
}


# ---------------------------------------------------------------------------
# SlippageModel
# ---------------------------------------------------------------------------


class SlippageModel:
    """Session-aware slippage estimator with volatility scaling.

    Usage::

        model = SlippageModel()
        slippage = model.get_slippage("XAUUSD", TradingSession.LONDON, VolatilityRegime.NORMAL)
        adjusted = model.apply_slippage(2350.50, "BUY", slippage)
        cost = model.estimate_cost_per_trade("XAUUSD", TradingSession.LONDON, 0.01)
    """

    def __init__(
        self,
        session_slippage: dict[TradingSession, float] | None = None,
        symbol_overrides: dict[str, dict[TradingSession, float]] | None = None,
    ) -> None:
        """Initialise with optional overrides.

        Args:
            session_slippage: Override default per-session slippage (pips).
            symbol_overrides: Per-symbol session slippage overrides (pips).
        """
        self._session_slippage = session_slippage or dict(DEFAULT_SESSION_SLIPPAGE_PIPS)
        self._symbol_overrides = symbol_overrides or dict(_SYMBOL_SLIPPAGE_OVERRIDE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_slippage(
        self,
        symbol: str,
        session: TradingSession | str,
        volatility_regime: VolatilityRegime | str = VolatilityRegime.NORMAL,
    ) -> float:
        """Return estimated slippage in pips for the given context.

        Args:
            symbol: Instrument symbol (e.g. ``"XAUUSD"``).
            session: Trading session (enum or string key).
            volatility_regime: Current volatility regime.

        Returns:
            Slippage estimate in pips (price points ÷ 10 for XAUUSD).
        """
        session_enum = self._coerce_session(session)
        vol_enum = self._coerce_volatility(volatility_regime)

        # Base slippage from symbol override or session default
        base = self._resolve_base_slippage(symbol.upper(), session_enum)

        # Apply volatility multiplier
        multiplier = _VOLATILITY_MULTIPLIERS.get(vol_enum, 1.0)
        slippage = base * multiplier

        logger.debug(
            "slippage: symbol=%s session=%s vol=%s base=%.2f mult=%.1f → %.2f pips",
            symbol,
            session_enum.value,
            vol_enum.value,
            base,
            multiplier,
            slippage,
        )
        return slippage

    def apply_slippage(self, price: float, side: str, slippage: float) -> float:
        """Adjust a price by slippage in the adverse direction.

        For BUY orders, slippage pushes the fill price *up* (higher cost).
        For SELL orders, slippage pushes the fill price *down* (lower fill).

        Args:
            price: Theoretical entry price.
            side: ``"BUY"`` or ``"SELL"`` (case-insensitive).
            slippage: Slippage in pips.

        Returns:
            Adjusted fill price.
        """
        pip_value = _SYMBOL_PIP_VALUE.get("XAUUSD", 0.10)
        adjustment = slippage * pip_value

        if side.upper() == "BUY":
            return price + adjustment
        return price - adjustment

    def estimate_cost_per_trade(
        self,
        symbol: str,
        session: TradingSession | str,
        lot_size: float = 0.01,
        volatility_regime: VolatilityRegime | str = VolatilityRegime.NORMAL,
    ) -> dict[str, float]:
        """Estimate total round-trip cost for one trade.

        Returns a dict with::

            {
                "spread_pips":   float,  # round-trip spread cost in pips
                "slippage_pips": float,  # one-way slippage estimate in pips
                "commission":    float,  # per-side commission in USD
                "total_pips":    float,  # total cost in pips
                "total_usd":     float,  # total cost converted to USD
            }

        Args:
            symbol: Instrument symbol.
            session: Trading session.
            lot_size: Position size in lots (0.01 = 1 oz for XAUUSD).
            volatility_regime: Current volatility regime.

        Returns:
            Cost breakdown dictionary.
        """
        sym = symbol.upper()
        session_enum = self._coerce_session(session)

        # Spread (round-trip = 2 × one-way spread for metals on Pepperstone Razor)
        spread_pips = _SYMBOL_SPREAD_PIPS.get(sym, {}).get(session_enum, 2.0)

        # Slippage (one-way estimate)
        slippage_pips = self.get_slippage(sym, session_enum, volatility_regime)

        # Commission
        commission_per_side = _SYMBOL_COMMISSION_PER_LOT.get(sym, 0.0)
        lots = lot_size / 0.01  # normalise to 0.01-lot units
        commission = commission_per_side * lots

        # Totals
        total_pips = spread_pips + slippage_pips
        pip_value = _SYMBOL_PIP_VALUE.get(sym, 0.10)
        total_usd = total_pips * pip_value * lots + commission

        result = {
            "spread_pips": round(spread_pips, 4),
            "slippage_pips": round(slippage_pips, 4),
            "commission": round(commission, 4),
            "total_pips": round(total_pips, 4),
            "total_usd": round(total_usd, 4),
        }

        logger.debug(
            "cost_estimate: symbol=%s session=%s lots=%.2f → %s",
            sym,
            session_enum.value,
            lot_size,
            result,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_base_slippage(self, symbol: str, session: TradingSession) -> float:
        """Look up base slippage: symbol override → session default."""
        sym_map = self._symbol_overrides.get(symbol)
        if sym_map and session in sym_map:
            return sym_map[session]
        return self._session_slippage.get(session, 0.20)

    @staticmethod
    def _coerce_session(value: TradingSession | str) -> TradingSession:
        if isinstance(value, TradingSession):
            return value
        return TradingSession(value.lower())

    @staticmethod
    def _coerce_volatility(value: VolatilityRegime | str) -> VolatilityRegime:
        if isinstance(value, VolatilityRegime):
            return value
        return VolatilityRegime(value.upper())
