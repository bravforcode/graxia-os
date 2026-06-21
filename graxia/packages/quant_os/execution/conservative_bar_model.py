"""
Conservative bar-based execution model.
Uses bar high/low to simulate bid/ask when tick data is unavailable.

Assumptions:
- Bar high approximates the max ask during the bar
- Bar low approximates the min bid during the bar
- Spread is estimated as (ask - bid) from the bar
- SL/TP triggers use the conservative (adverse) assumption
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .fill_model import FillRequest, FillResult, Side, simulate_entry, check_sl_tp_trigger


@dataclass
class BarTick:
    """Synthetic tick from bar data."""
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    high: Decimal
    low: Decimal


def estimate_bid_ask_from_bar(
    open_price: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    spread_estimate: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Estimate bid/ask from OHLC bar.
    Conservative: use high for ask side, low for bid side.
    """
    mid = (high + low) / Decimal("2")
    bid = mid - spread_estimate / Decimal("2")
    ask = mid + spread_estimate / Decimal("2")
    return bid, ask


def simulate_bar_execution(
    bars: list[dict],  # OHLCV bars with keys: timestamp, open, high, low, close, volume
    signals: list[dict],  # signals with keys: bar_index, side, stop_loss, take_profit, slippage_entry, slippage_exit
    spread_estimate: Decimal,
    slippage: Decimal,
) -> list[dict]:
    """
    Execute signals using conservative bar model.
    Signal generates on bar close, fills on NEXT bar open (with bid/ask).
    """
    results = []
    for sig in signals:
        bar_idx = sig["bar_index"]
        # Next-bar fill timing (Section 9.4)
        fill_idx = bar_idx + 1
        if fill_idx >= len(bars):
            continue

        bar = bars[fill_idx]
        bid, ask = estimate_bid_ask_from_bar(
            bar["open"], bar["high"], bar["low"], bar["close"], spread_estimate
        )
        req = FillRequest(
            side=Side.BUY if sig["side"] == "BUY" else Side.SELL,
            entry_price=Decimal(str(sig.get("entry_price", bar["open"]))),
            stop_loss=Decimal(str(sig["stop_loss"])),
            take_profit=Decimal(str(sig["take_profit"])) if sig.get("take_profit") is not None else None,
            slippage_entry=slippage,
            slippage_exit=slippage,
        )
        spread = ask - bid
        fill = simulate_entry(req, bid, ask, spread)
        trigger = check_sl_tp_trigger(req.side, req.stop_loss, req.take_profit, bid, ask)
        results.append({
            "signal_bar": bar_idx,
            "fill_bar": fill_idx,
            "fill_price": fill.entry_price,
            "trigger": trigger,
            "bid": bid,
            "ask": ask,
        })
    return results


def next_bar_fill(
    signal_bar_index: int,
    signal: FillRequest,
    bars: list[dict],
    bar_timestamps: list[datetime],
    spread: Decimal,
    slippage: Decimal,
) -> FillResult | None:
    """
    Fill a signal on the NEXT bar after the signal bar.
    Returns None if no next bar exists.
    Entry price = next bar's estimated bid/ask + slippage.
    """
    fill_idx = signal_bar_index + 1
    if fill_idx >= len(bars):
        return None

    bar = bars[fill_idx]
    bid, ask = estimate_bid_ask_from_bar(
        bar["open"], bar["high"], bar["low"], bar["close"], spread
    )
    fill = simulate_entry(signal, bid, ask, ask - bid)
    trigger = check_sl_tp_trigger(signal.side, signal.stop_loss, signal.take_profit, bid, ask)
    return FillResult(
        entry_price=fill.entry_price,
        sl_cost=fill.sl_cost,
        triggered=trigger is not None,
    )
