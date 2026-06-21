"""Fill model — bid/ask entry/exit, SL/TP triggers, ambiguous bar handling."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionQuality(Enum):
    BAR_ONLY = "bar_only"
    CONSERVATIVE_BAR = "conservative_bar"
    TICK_REPLAY = "tick_replay"
    LIVE_OBSERVED = "live_observed"


@dataclass(frozen=True)
class FillRequest:
    side: Side
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    slippage_entry: Decimal
    slippage_exit: Decimal


@dataclass(frozen=True)
class FillResult:
    entry_price: Decimal
    sl_cost: Decimal
    exit_price: Decimal
    slippage_cost: Decimal
    execution_quality: ExecutionQuality
    is_ambiguous: bool
    ambiguous_path: str


def simulate_entry(
    req: FillRequest, bid: Decimal, ask: Decimal, spread: Decimal
) -> FillResult:
    if req.side == Side.BUY:
        entry = ask + req.slippage_entry
    else:
        entry = bid - req.slippage_entry
    return FillResult(
        entry_price=entry,
        sl_cost=req.slippage_entry,
        exit_price=Decimal("0"),
        slippage_cost=req.slippage_entry,
        execution_quality=ExecutionQuality.BAR_ONLY,
        is_ambiguous=False,
        ambiguous_path="",
    )


def simulate_exit(
    side: Side, bid: Decimal, ask: Decimal, slippage: Decimal
) -> tuple[Decimal, Decimal]:
    if side == Side.BUY:
        return bid - slippage, slippage
    return ask + slippage, slippage


def check_sl_tp_trigger(
    side: Side,
    stop_loss: Decimal,
    take_profit: Decimal,
    bid: Decimal,
    ask: Decimal,
) -> str | None:
    if side == Side.BUY:
        sl_hit = bid <= stop_loss
        tp_hit = bid >= take_profit
    else:
        sl_hit = ask >= stop_loss
        tp_hit = ask <= take_profit

    if sl_hit and tp_hit:
        return "SL"
    if sl_hit:
        return "SL"
    if tp_hit:
        return "TP"
    return None


def can_fill_on_info_candle(signal_bar_index: int, fill_bar_index: int) -> bool:
    return fill_bar_index > signal_bar_index
