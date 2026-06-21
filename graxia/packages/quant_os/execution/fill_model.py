"""
Canonical bid/ask fill rules per the Master Plan Section 9.3.

Market buy entry   = ask + entry slippage
Market sell entry  = bid - entry slippage

Close long         = bid - exit slippage
Close short        = ask + exit slippage

Long SL trigger    = bid <= stop_loss
Long TP trigger    = bid >= take_profit

Short SL trigger   = ask >= stop_loss
Short TP trigger   = ask <= take_profit
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionQuality(Enum):
    """Labels for execution quality tracking."""
    BAR_ONLY = "BAR_ONLY"                 # Close-price only (legacy, not for evidence)
    CONSERVATIVE_BAR = "CONSERVATIVE_BAR" # Bid/ask from bar high/low
    TICK_REPLAY = "TICK_REPLAY"           # Actual tick data
    LIVE_OBSERVED = "LIVE_OBSERVED"       # From live broker feed


@dataclass(frozen=True)
class FillRequest:
    side: Side
    entry_price: Decimal  # Signal's intended entry
    stop_loss: Decimal
    take_profit: Decimal | None
    slippage_entry: Decimal  # In price units
    slippage_exit: Decimal


@dataclass(frozen=True)
class FillResult:
    entry_price: Decimal     # Actual fill price (entry + slippage)
    sl_cost: Decimal         # Slippage cost in account currency
    triggered: bool          # Was the fill immediately stopped out?


def simulate_entry(
    request: FillRequest,
    bid: Decimal,
    ask: Decimal,
    spread: Decimal,
) -> FillResult:
    """
    Simulate market order entry using bid/ask.
    Long fills at ask + slippage, short fills at bid - slippage.
    """
    if request.side == Side.BUY:
        entry = ask + request.slippage_entry
    else:
        entry = bid - request.slippage_entry
    return FillResult(entry_price=entry, sl_cost=request.slippage_entry, triggered=False)


def check_sl_tp_trigger(
    side: Side,
    stop_loss: Decimal,
    take_profit: Decimal | None,
    bid: Decimal,
    ask: Decimal,
) -> str | None:
    """
    Check if SL or TP is triggered by current bid/ask.
    Returns "SL", "TP", or None.

    Rules:
    - Long SL triggers when bid <= stop_loss
    - Long TP triggers when bid >= take_profit
    - Short SL triggers when ask >= stop_loss
    - Short TP triggers when ask <= take_profit
    """
    if side == Side.BUY:
        if bid <= stop_loss:
            return "SL"
        if take_profit is not None and bid >= take_profit:
            return "TP"
    else:
        if ask >= stop_loss:
            return "SL"
        if take_profit is not None and ask <= take_profit:
            return "TP"
    return None


def simulate_exit(
    side: Side,
    bid: Decimal,
    ask: Decimal,
    slippage: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Simulate closing a position.
    Long closes at bid - slippage, short closes at ask + slippage.
    Returns (exit_price, sl_cost).
    """
    if side == Side.BUY:
        price = bid - slippage
    else:
        price = ask + slippage
    return price, slippage


def can_fill_on_info_candle(signal_bar_index: int, fill_bar_index: int) -> bool:
    """No same-bar fill — fill must be strictly after signal bar."""
    return fill_bar_index > signal_bar_index


# ── Spec-named aliases ────────────────────────────────────────────────
# ponytail: aliases so tests can import canonical names without changing
# the existing API that other modules already depend on.

def calculate_entry_fill(req: FillRequest, bid: Decimal, ask: Decimal, spread: Decimal) -> FillResult:
    """Alias for simulate_entry — same bid/ask entry rules."""
    return simulate_entry(req, bid, ask, spread)


def calculate_exit_fill(side: Side, bid: Decimal, ask: Decimal, slippage: Decimal) -> Decimal:
    """Alias for simulate_exit — returns price only."""
    price, _ = simulate_exit(side, bid, ask, slippage)
    return price


def check_sl_tp_triggers(
    side: Side,
    stop_loss: Decimal,
    take_profit: Decimal | None,
    bid: Decimal,
    ask: Decimal,
) -> str | None:
    """Alias for check_sl_tp_trigger."""
    return check_sl_tp_trigger(side, stop_loss, take_profit, bid, ask)
