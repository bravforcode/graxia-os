"""Dynamic spread/slippage model for backtest.

P0.1 (2026-07-29) — symbol-aware, bps-denominated cost model.

WHY THIS MODULE WAS REWRITTEN
-----------------------------
The original `SpreadConfig` was documented "for XAUUSD on Pepperstone Razor"
and took no symbol.  `backtest/engine.py` instantiated it for EVERY instrument
and multiplied its pip value by that instrument's own `tick_size`, so a single
gold-shaped curve produced cost errors spanning ~4 orders of magnitude across
the universe (BTCUSD ~1000x too low, EURUSD ~5-15x too high).  Every strategy
verdict in `reports/edge_search_*.json` was produced under that model.

A first repair attempt kept the pips denomination and hand-converted
`spread_bps_measured` into per-session pips.  That conversion was wrong for
every symbol (USDJPY 40x low, OIL ~500x low) because bps->pips requires
multiplying by price and dividing by tick_size, and it is easy to invert.

This version removes the error-prone step entirely:

  * costs are stored and returned in **bps of price** — tick_size independent
  * values come from `config/cost_calibration.json`, never hand-typed here
  * unknown / unmeasured / mock symbols **raise**, they never fall back

Callers convert to a price offset at the point of use:

    spread_price = price * spread_bps / 10_000

BACK-COMPAT
-----------
`SpreadConfig` is retained with its original pip-denominated session API for
existing callers and `tests/test_dynamic_spread.py`, which assert only the
relative ordering of sessions.  It is NOT wired into the engine's measured
cost path any more — `SymbolCostProfile` is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "cost_calibration.json"

# Status values that must never reach a cost calculation.  `MOCK` is invented
# data; `UNVERIFIED_NO_DATA` is a placeholder the calibration file itself flags
# as unbacked.  See config/cost_calibration.json `data_integrity_fix_20260726`.
_UNUSABLE_STATUSES = frozenset({"MOCK", "UNVERIFIED_NO_DATA"})


class UnmeasuredCostError(RuntimeError):
    """Raised when a cost input is missing, mock, or unverified.

    Deliberately NOT a subclass of ValueError/Exception-that-gets-swallowed by
    convention: callers must not paper over this with a generic `except`.
    Silently substituting another instrument's costs is the exact defect this
    module exists to prevent.
    """


# Explicit synthetic cost profiles for the reserved test/simulation symbols.
# Mirrors the same deliberate carve-out in core/contract_specs.py:39-42
# ("Explicit synthetic spec for backtests / paper sims ... NOT a silent
# default: real unmapped symbols still raise").
#
# These are FICTIONAL round numbers, not measurements. They exist so unit tests
# and synthetic fixtures can run. Status is SYNTHETIC so any consumer that
# checks provenance can reject them, and only these exact reserved symbols can
# reach them — a real unmapped instrument still raises.
_SYNTHETIC_SYMBOLS: dict[str, dict[str, float]] = {
    "BACKTEST": {"spread_bps": 1.0, "spread_bps_p95": 2.0, "slippage_bps": 0.5},
    "TEST": {"spread_bps": 1.0, "spread_bps_p95": 2.0, "slippage_bps": 0.5},
}


@lru_cache(maxsize=1)
def _load_calibration() -> dict:
    if not _CONFIG_PATH.exists():
        raise UnmeasuredCostError(
            f"Cost calibration file not found: {_CONFIG_PATH}. Backtests cannot run without measured costs."
        )
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class SymbolCostProfile:
    """Measured, bps-denominated cost profile for one symbol.

    All values are bps **of price**, one side unless stated otherwise, so they
    are independent of `tick_size` and of any contract-spec change.
    """

    symbol: str
    spread_bps: Decimal  # median/measured, one side
    spread_bps_p95: Decimal  # for stress scenarios
    slippage_bps: Decimal | None  # None when unmeasured — caller must override
    swap_long_bps: Decimal | None
    swap_short_bps: Decimal | None
    commission_bps: Decimal
    status: str

    @classmethod
    def for_symbol(cls, symbol: str) -> SymbolCostProfile:
        """Load the measured profile for `symbol`.

        Raises UnmeasuredCostError when the symbol is absent, or its data is
        MOCK/UNVERIFIED_NO_DATA.  Never falls back to another instrument.
        """
        synthetic = _SYNTHETIC_SYMBOLS.get(symbol)
        if synthetic is not None:
            return cls(
                symbol=symbol,
                spread_bps=Decimal(str(synthetic["spread_bps"])),
                spread_bps_p95=Decimal(str(synthetic["spread_bps_p95"])),
                slippage_bps=Decimal(str(synthetic["slippage_bps"])),
                swap_long_bps=Decimal("0"),
                swap_short_bps=Decimal("0"),
                commission_bps=Decimal("0"),
                status="SYNTHETIC",
            )

        raw = _load_calibration()
        assets = raw.get("assets", {})
        entry = assets.get(symbol)
        if entry is None:
            raise UnmeasuredCostError(
                f"No measured cost data for symbol '{symbol}'. "
                f"Available: {sorted(assets)}. "
                f"Measure it (scripts/measure_spread_continuous.py) and add it to "
                f"{_CONFIG_PATH.name} before backtesting this instrument. "
                f"Do NOT substitute another symbol's costs."
            )

        status = str(entry.get("status", "UNKNOWN"))
        if status in _UNUSABLE_STATUSES:
            raise UnmeasuredCostError(
                f"Symbol '{symbol}' has cost status '{status}' — the calibration "
                f"file itself marks this data as not real. Refusing to use it. "
                f"Measure real spreads before backtesting this instrument."
            )

        spread = entry.get("spread_bps_measured")
        if spread is None:
            raise UnmeasuredCostError(f"Symbol '{symbol}' has no 'spread_bps_measured'.")

        def _opt(key: str) -> Decimal | None:
            v = entry.get(key)
            return None if v is None else Decimal(str(v))

        return cls(
            symbol=symbol,
            spread_bps=Decimal(str(spread)),
            spread_bps_p95=Decimal(str(entry.get("spread_bps_p95", spread))),
            slippage_bps=_opt("slippage_bps_measured"),
            swap_long_bps=_opt("swap_long_bps"),
            swap_short_bps=_opt("swap_short_bps"),
            commission_bps=Decimal(str(entry.get("commission_bps", 0))),
            status=status,
        )

    def get_spread_bps(self, stress: bool = False) -> Decimal:
        """Spread in bps of price, one side.

        Session variation is deliberately NOT modelled: `cost_calibration.json`
        carries a single measured figure per asset, with no per-session
        breakdown backed by real data.  Inventing a session shape here is what
        produced the original defect.  Use `stress=True` for the p95 figure.
        """
        return self.spread_bps_p95 if stress else self.spread_bps

    def get_slippage_bps(self, atr_ratio: float = 1.0) -> Decimal:
        """Slippage in bps of price, one side, scaled by volatility regime.

        Raises when slippage was never measured for this symbol — the caller
        must then supply an explicit override rather than inherit a guess.
        """
        if self.slippage_bps is None:
            raise UnmeasuredCostError(
                f"Symbol '{self.symbol}' has no measured slippage "
                f"('slippage_bps_measured' is null in {_CONFIG_PATH.name}). "
                f"Either measure it or pass an explicit slippage override."
            )
        if atr_ratio < 0.5:
            mult = Decimal("0.5")
        elif atr_ratio > 2.0:
            mult = Decimal("2.0")
        else:
            mult = Decimal("1.0")
        return self.slippage_bps * mult


def bps_to_price(bps: Decimal, price: Decimal) -> Decimal:
    """Convert a bps-of-price cost into an absolute price offset.

    This is the ONLY sanctioned conversion. It never touches `tick_size`, so a
    contract-spec change cannot silently move costs (which is what happened
    when USDJPY/NAS100/OIL tick_size were corrected on 2026-07-29).
    """
    return price * bps / Decimal("10000")


# ---------------------------------------------------------------------------
# Back-compat: pip-denominated session shape.
#
# Retained for callers that pass an explicit pip override and for
# tests/test_dynamic_spread.py, which assert only relative session ordering.
# NOT used by the engine's measured-cost path.
# ---------------------------------------------------------------------------
@dataclass
class SpreadConfig:
    """Session-shaped spread/slippage in pips (legacy, override-only).

    WARNING: these defaults are XAUUSD-shaped. Do not use them to price
    another instrument — use `SymbolCostProfile.for_symbol()` instead.
    """

    asian_spread: float = 3.0
    london_spread: float = 1.5
    ny_spread: float = 1.5
    overlap_spread: float = 1.2
    closed_spread: float = 5.0

    base_slip_pips: float = 0.3

    low_vol_slippage_mult: float = 0.5
    normal_vol_slippage_mult: float = 1.0
    high_vol_slippage_mult: float = 2.0

    def get_spread(self, utc_hour: int) -> Decimal:
        """Get spread in pips based on UTC hour."""
        if 0 <= utc_hour < 7:
            return Decimal(str(self.asian_spread))
        elif 7 <= utc_hour < 13:
            return Decimal(str(self.london_spread))
        elif 13 <= utc_hour < 17:
            return Decimal(str(self.overlap_spread))
        elif 17 <= utc_hour < 21:
            return Decimal(str(self.ny_spread))
        else:
            return Decimal(str(self.closed_spread))

    def get_slippage(self, utc_hour: int, atr: float = 1.0) -> Decimal:
        """Get slippage in pips based on session and volatility."""
        base_slip = Decimal(str(self.base_slip_pips))
        if atr < 0.5:
            mult = self.low_vol_slippage_mult
        elif atr > 2.0:
            mult = self.high_vol_slippage_mult
        else:
            mult = self.normal_vol_slippage_mult
        return base_slip * Decimal(str(mult))
