"""Ambiguous bar adverse resolution logic.

When a conservative OHLC bar may trigger both SL and TP,
resolve adverse outcome first (SL takes precedence).
"""

from dataclasses import dataclass
from decimal import Decimal

from .fill_model import Side


@dataclass(frozen=True)
class AmbiguousResult:
    """Result of ambiguous bar resolution."""
    is_ambiguous: bool
    resolved_reason: str  # "SL" or "TP"
    resolution_price: Decimal
    resolution_policy: str  # "ADVERSE"
    sl_distance: Decimal
    tp_distance: Decimal


@dataclass(frozen=True)
class BarTrigger:
    """A single trigger event within a bar."""
    trigger_type: str  # "SL" or "TP"
    price: Decimal
    is_ambiguous: bool


def _sl_distance(side: Side, entry_ref: Decimal, stop_loss: Decimal) -> Decimal:
    return abs(entry_ref - stop_loss)


def _tp_distance(side: Side, entry_ref: Decimal, take_profit: Decimal) -> Decimal:
    return abs(entry_ref - take_profit)


def resolve_ambiguous_bar(
    side: Side,
    stop_loss: Decimal,
    take_profit: Decimal,
    bar_high: Decimal,
    bar_low: Decimal,
    bar_open: Decimal,
    bar_close: Decimal,
) -> AmbiguousResult:
    """Resolve a bar where both SL and TP could be triggered.

    For LONG:  SL if low <= stop_loss, TP if high >= take_profit
    For SHORT: SL if high >= stop_loss, TP if low <= take_profit

    If both possible → resolve ADVERSE (SL takes precedence).
    """
    if side == Side.BUY:
        sl_triggered = bar_low <= stop_loss
        tp_triggered = bar_high >= take_profit
    else:
        sl_triggered = bar_high >= stop_loss
        tp_triggered = bar_low <= take_profit

    is_ambiguous = sl_triggered and tp_triggered

    if is_ambiguous:
        # Adverse resolution: SL wins
        resolved_reason = "SL"
        resolution_price = stop_loss
    elif sl_triggered:
        resolved_reason = "SL"
        resolution_price = stop_loss
    elif tp_triggered:
        resolved_reason = "TP"
        resolution_price = take_profit
    else:
        resolved_reason = ""
        resolution_price = bar_close

    sl_dist = _sl_distance(side, bar_open, stop_loss)
    tp_dist = _tp_distance(side, bar_open, take_profit)

    return AmbiguousResult(
        is_ambiguous=is_ambiguous,
        resolved_reason=resolved_reason,
        resolution_price=resolution_price,
        resolution_policy="ADVERSE" if is_ambiguous else "",
        sl_distance=sl_dist,
        tp_distance=tp_dist,
    )


def check_bar_triggers_with_ambiguous_resolution(
    side: Side,
    sl: Decimal,
    tp: Decimal,
    bar: dict,  # keys: open, high, low, close
) -> list[BarTrigger]:
    """Walk through bar OHLC path and return ordered triggers.

    Uses conservative assumption: worst adverse price touched first.
    For ambiguous bars, SL is returned before TP but marked ambiguous.
    """
    bar_high = Decimal(str(bar["high"]))
    bar_low = Decimal(str(bar["low"]))
    bar_open = Decimal(str(bar["open"]))
    bar_close = Decimal(str(bar["close"]))

    result = resolve_ambiguous_bar(side, sl, tp, bar_high, bar_low, bar_open, bar_close)

    triggers: list[BarTrigger] = []

    if side == Side.BUY:
        sl_possible = bar_low <= sl
        tp_possible = bar_high >= tp
    else:
        sl_possible = bar_high >= sl
        tp_possible = bar_low <= tp

    if sl_possible and tp_possible:
        # Ambiguous: adverse first, then note TP also possible
        triggers.append(BarTrigger(trigger_type="SL", price=sl, is_ambiguous=True))
        triggers.append(BarTrigger(trigger_type="TP", price=tp, is_ambiguous=True))
    elif sl_possible:
        triggers.append(BarTrigger(trigger_type="SL", price=sl, is_ambiguous=False))
    elif tp_possible:
        triggers.append(BarTrigger(trigger_type="TP", price=tp, is_ambiguous=False))

    return triggers
