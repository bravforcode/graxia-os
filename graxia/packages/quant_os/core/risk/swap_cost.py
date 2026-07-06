"""Swap / overnight financing cost model for XAUUSD on Pepperstone Razor.

Bug #8 fix: No swap cost was modeled anywhere in the v2.0 pipeline.
Pepperstone charges TomNext-based swap on positions held past NY 5pm rollover
with triple charge on one weekday (verify which day in your terminal).

swap_mode enum (from MT5):
    0 = SWAP_BY_POINTS    — swap in symbol points
    1 = SWAP_BY_DOLLARS   — swap in account currency (base currency)
    2 = SWAP_BY_INTEREST  — swap as % per annum (interest)
    3 = SWAP_BY_MARGIN_CURRENCY — swap in margin currency
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any


def get_live_swap_rates(symbol: str = "XAUUSD") -> dict[str, Any]:
    """
    Pull live long/short swap rates directly from the MT5 terminal.

    Checks MT5 symbol_info for swap_long, swap_short, swap_mode, and
    swap_rollover3days (the weekday that carries triple swap).

    Returns dict with keys: swap_long, swap_short, swap_mode,
    swap_rollover3days, point, contract_size, currency_profit.
    Returns empty dict if MT5 is unavailable.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {}

    info = mt5.symbol_info(symbol)
    if info is None:
        return {}

    return {
        "swap_long": getattr(info, "swap_long", 0.0),
        "swap_short": getattr(info, "swap_short", 0.0),
        "swap_mode": getattr(info, "swap_mode", 0),
        "swap_rollover3days": getattr(info, "swap_rollover3days", 3),
        "point": float(getattr(info, "point", 0.01)),
        "contract_size": float(getattr(info, "trade_contract_size", 100.0)),
        "currency_profit": getattr(info, "currency_profit", "USD") or "USD",
    }


_SWAP_MODE_NAMES: dict[int, str] = {
    0: "SWAP_BY_POINTS",
    1: "SWAP_BY_DOLLARS",
    2: "SWAP_BY_INTEREST",
    3: "SWAP_BY_MARGIN_CURRENCY",
}


def estimate_overnight_cost(
    direction: str,
    lot: float,
    nights_held: int,
    triple_swap_weekday: int,
    swap_rates: dict[str, Any],
    point_value_per_lot: float = 1.0,
    apply_triple_multiplier: bool = True,
) -> float:
    """
    Estimate overnight swap cost for a position held across rollover.

    Args:
        direction: "BUY" or "SELL" — determines which swap rate to use.
        lot: Position size in lots (e.g. 0.01 = 1 oz for XAUUSD).
        nights_held: Number of rollover events the position spans.
        triple_swap_weekday: 0=Mon..6=Sun — the weekday carrying 3× swap.
            Verify in your MT5 terminal symbol spec; do not assume Wednesday.
        swap_rates: Dict from get_live_swap_rates(), or a synthetic dict
            with keys swap_long, swap_short, swap_mode, point, contract_size.
        point_value_per_lot: Dollar value of 1 point move per lot.
            For XAUUSD 0.01 lot: 1 point = $0.01 (0.01 × 1 oz × $1/point).
        apply_triple_multiplier: If True, apply 3× multiplier for single night
            on triple swap day. Set to False when nights_held already accounts
            for triple swap (e.g., from get_swap_cost_for_trade).

    Returns:
        Estimated overnight cost in account currency (negative = cost to you).
    """
    mode = swap_rates.get("swap_mode", 0)
    rate = swap_rates.get("swap_long", 0.0) if direction.upper() == "BUY" else swap_rates.get("swap_short", 0.0)
    point = swap_rates.get("point", 0.01)
    contract_size = swap_rates.get("contract_size", 100.0)

    if nights_held <= 0 or rate == 0.0:
        return 0.0

    is_triple_day = triple_swap_weekday not in (None, -1)
    multiplier_base = nights_held
    if apply_triple_multiplier and is_triple_day and nights_held == 1:
        multiplier_base = 3

    if mode == 0:
        cost = rate * point_value_per_lot * lot * multiplier_base
    elif mode == 1:
        cost = rate * lot * multiplier_base
    elif mode == 2:
        cost = rate * contract_size * lot * point / 100.0 / 365.0 * multiplier_base
    elif mode == 3:
        cost = rate * point_value_per_lot * lot * multiplier_base
    else:
        cost = rate * point_value_per_lot * lot * multiplier_base

    return float(cost)


def get_swap_cost_for_trade(
    entry_time: datetime,
    exit_time: datetime,
    side: str,
    lot: float,
    swap_rates: dict[str, Any],
    triple_swap_weekday: int,
) -> float:
    """
    Calculate actual overnight cost for a completed trade.

    Counts the number of 5pm NY rollovers (21:00 UTC) between entry_time
    and exit_time, then applies the triple-swap multiplier for the
    configured weekday.

    Returns total swap cost in account currency (negative = cost).
    """
    if swap_rates.get("swap_mode", 0) not in _SWAP_MODE_NAMES:
        return 0.0

    rate = swap_rates.get("swap_long", 0.0) if side.upper() == "BUY" else swap_rates.get("swap_short", 0.0)
    if rate == 0.0:
        return 0.0

    entry_utc = entry_time.astimezone(UTC) if entry_time.tzinfo else entry_time.replace(tzinfo=UTC)
    exit_utc = exit_time.astimezone(UTC) if exit_time.tzinfo else exit_time.replace(tzinfo=UTC)

    rollover_hour = 21
    nights_held = 0
    triple_count = 0

    current = entry_utc.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)
    if current <= entry_utc:
        from datetime import timedelta
        current += timedelta(days=1)

    while current < exit_utc:
        nights_held += 1
        if current.weekday() == triple_swap_weekday:
            triple_count += 1
        from datetime import timedelta
        current += timedelta(days=1)

    effective_nights = (nights_held - triple_count) + (triple_count * 3)

    return estimate_overnight_cost(
        direction=side,
        lot=lot,
        nights_held=effective_nights,
        triple_swap_weekday=triple_swap_weekday,
        swap_rates=swap_rates,
        apply_triple_multiplier=False,  # Already accounted for in effective_nights
    )
