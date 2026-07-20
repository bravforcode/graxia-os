"""
Standalone grid strategy backtest harness.
Import from grid_strategy.py. No engine subclassing.

KEY FIX (2026-07-20): Unrealized mark-to-market tracking.
- Previous version counted cycle_profit on first fill (BUY) without waiting for
  counter-fill (SELL). Result: overcounted realized PnL, zero unrealized tracking.
- Now: tracks open_lots (net position) + avg_entry_price. PnL only realized when
  position closes. Unrealized P&L computed every bar against close price.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

try:
    from .grid_strategy import GridConfig, GridOrder
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grid_strategy import GridConfig, GridOrder  # type: ignore[no-redef]


# ── Local backtest state (ponytail: self-contained, simpler than strategy GridState) ──

class _BacktestState:
    __slots__ = (
        "levels", "fill_count", "cumulative_pnl", "peak_equity",
        "max_drawdown", "deactivated", "deactivation_bar",
        "active_bars", "bars_with_fill", "equity_curve", "fill_events",
        "open_lots", "avg_entry_price", "total_fees",
    )
    def __init__(self):
        self.levels: list = []           # PENDING orders only (removed on fill)
        self.fill_count = 0
        self.cumulative_pnl = 0.0        # realized P&L only
        self.peak_equity = INITIAL_CAPITAL
        self.max_drawdown = 0.0
        self.deactivated = False
        self.deactivation_bar = -1
        self.active_bars = 0
        self.bars_with_fill = 0
        self.equity_curve: list[float] = []
        self.fill_events: list[dict] = []
        # Position tracking (THE FIX): net lots + weighted avg entry
        self.open_lots: float = 0.0
        self.avg_entry_price: float = 0.0
        self.total_fees: float = 0.0

INITIAL_CAPITAL = 100_000.0
FEE_RATE = 0.001  # 0.1% per fill
GRID_ACTIVATION_BAR = 20  # need warmup for ATR


# ── ATR (simple numpy, no numba dep) ──────────────────────────────────

def _calc_atr(high: list[float], low: list[float], close: list[float], period: int) -> np.ndarray:
    h, l, c = np.array(high), np.array(low), np.array(close)
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - c[:-1]),
        np.abs(l[1:] - c[:-1]),
    ])
    atr = np.zeros(len(close), dtype=np.float64)
    atr[period] = np.mean(tr[:period])
    for i in range(period + 1, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i - 1]) / period
    return atr


# ── Grid helpers ──────────────────────────────────────────────────────

def _build_grid_orders(
    range_low: float, range_high: float, grid_count: int, side_alt: str = "SELL",
) -> list[GridOrder]:
    """Build evenly spaced grid orders. side_alt = starting side at range_high."""
    step = (range_high - range_low) / (grid_count - 1) if grid_count > 1 else 0.0
    orders: list[GridOrder] = []
    for i in range(grid_count):
        price = range_high - i * step
        side = side_alt if i % 2 == 0 else ("BUY" if side_alt == "SELL" else "SELL")
        orders.append(GridOrder(price=price, side=side, volume=0.01))
    # Reverse so index 0 = range_low (bottom)
    orders.reverse()
    return orders


def _fill_position(s: _BacktestState, order_price: float, volume: float, is_buy: bool) -> None:
    """Update net position on a fill. Handles long/short/flip transitions.

    BUY : open_lots += volume, entry = weighted average
    SELL: open_lots -= volume, realize P&L when closing
    """
    fee = order_price * volume * FEE_RATE
    s.total_fees += fee

    if is_buy:
        if s.open_lots >= 0:
            # Adding to long: weighted average entry
            total_cost = s.avg_entry_price * s.open_lots + order_price * volume
            s.open_lots += volume
            s.avg_entry_price = total_cost / s.open_lots if s.open_lots > 0 else 0.0
        else:
            # Closing a short (partially or fully)
            close_vol = min(volume, abs(s.open_lots))
            realized = (s.avg_entry_price - order_price) * close_vol
            s.cumulative_pnl += realized - fee
            s.open_lots += close_vol
            remaining = volume - close_vol
            if remaining > 0:
                s.avg_entry_price = order_price
                s.open_lots = remaining
            elif s.open_lots == 0:
                s.avg_entry_price = 0.0
    else:
        if s.open_lots > 0:
            # Closing long
            close_vol = min(volume, s.open_lots)
            realized = (order_price - s.avg_entry_price) * close_vol
            s.cumulative_pnl += realized - fee
            s.open_lots -= close_vol
            remaining = volume - close_vol
            if remaining > 0:
                s.avg_entry_price = order_price
                s.open_lots = -remaining
            elif s.open_lots == 0:
                s.avg_entry_price = 0.0
        else:
            # Adding to short
            total_cost = s.avg_entry_price * abs(s.open_lots) + order_price * volume
            s.open_lots -= volume
            s.avg_entry_price = total_cost / abs(s.open_lots) if s.open_lots != 0 else 0.0


def _unrealized_pnl(s: _BacktestState, current_price: float) -> float:
    """Mark-to-market unrealized P&L on open position."""
    if s.open_lots > 0:
        return (current_price - s.avg_entry_price) * s.open_lots
    elif s.open_lots < 0:
        return (s.avg_entry_price - current_price) * abs(s.open_lots)
    return 0.0


# ── Main backtest function ────────────────────────────────────────────

def run_grid_backtest(
    config: GridConfig,
    ohlcv_data: dict[str, list],
    timestamps: list | None = None,
) -> dict:
    """Run grid strategy backtest on OHLCV data.

    Returns dict with fills, pnl, drawdown, equity curve, etc.
    """
    close = ohlcv_data["close"]
    high = ohlcv_data["high"]
    low = ohlcv_data["low"]
    n = len(close)

    # ── Determine range ───────────────────────────────────────────────
    activation_bar = GRID_ACTIVATION_BAR
    if config.range_method == "atr":
        atr = _calc_atr(high, low, close, config.atr_period)
        activation_bar = max(GRID_ACTIVATION_BAR, config.atr_period + 1)
        if n <= activation_bar:
            return _empty_result(n, "not enough bars for ATR warmup")

        mid = close[activation_bar - 1]
        atr_val = float(atr[activation_bar - 1])  # atr[period] is first valid value
        if atr_val <= 0:
            return _empty_result(n, "ATR is zero at activation bar")

        grid_range = atr_val * config.atr_multiplier
        range_low = mid - grid_range
        range_high = mid + grid_range
    else:
        activation_bar = 0
        if config.low_price == 0 and config.high_price == 0:
            return _empty_result(n, "fixed range requires high_price and low_price")
        range_low = float(config.low_price)
        range_high = float(config.high_price)
        if range_low >= range_high:
            return _empty_result(n, "range_low must be < range_high")

    grid_count = config.grid_count
    step = config.grid_step if config.grid_step != 0 else (range_high - range_low) / (grid_count - 1)
    range_width = range_high - range_low

    # -- State --
    s = _BacktestState()
    s.levels = _build_grid_orders(range_low, range_high, grid_count)
    peak_total_equity = INITIAL_CAPITAL
    max_total_dd = 0.0

    # ── Bar loop ──────────────────────────────────────────────────────
    for i in range(n):
        bar_close = close[i]

        # Grid activation
        grid_active = i >= activation_bar and not s.deactivated
        if not grid_active:
            unrealized = _unrealized_pnl(s, bar_close)
            total_equity = INITIAL_CAPITAL + s.cumulative_pnl + unrealized
            s.equity_curve.append(total_equity)
            continue

        s.active_bars += 1
        bar_high = high[i]
        bar_low = low[i]
        bar_had_fill = False

        # 1. Evaluate fills: check pending orders against bar range
        filled_indices = []
        for j, order in enumerate(s.levels):
            if order.status != "PENDING":
                continue
            filled = False
            if order.side in ("BUY", "COUNTER_BUY") and bar_low <= order.price:
                filled = True
            elif order.side in ("SELL", "COUNTER_SELL") and bar_high >= order.price:
                filled = True

            if not filled:
                continue

            filled_indices.append(j)

        # Process fills in reverse order (remove from end first)
        for j in reversed(filled_indices):
            order = s.levels[j]
            del s.levels[j]
            bar_had_fill = True
            s.fill_count += 1

            # Position tracking (THE FIX)
            is_buy = order.side in ("BUY", "COUNTER_BUY")
            _fill_position(s, order.price, config.order_volume, is_buy)

            # Place counter-order (only within range + limit total orders)
            if is_buy:
                counter_price = order.price + step
                counter_side = "SELL"
            else:
                counter_price = order.price - step
                counter_side = "BUY"

            if range_low <= counter_price <= range_high and len(s.levels) < 1000:
                counter = GridOrder(
                    id="", price=counter_price, side=counter_side, volume=config.order_volume,
                )
                s.levels.append(counter)

            # Record fill event
            s.fill_events.append({
                "bar": i,
                "price": order.price,
                "side": order.side,
                "fee": round(order.price * config.order_volume * FEE_RATE, 4),
                "open_lots_after": round(s.open_lots, 4),
            })

        if bar_had_fill:
            s.bars_with_fill += 1

        # 2. Mark-to-market: unrealized P&L on open position (THE FIX)
        unrealized = _unrealized_pnl(s, bar_close)
        total_equity = INITIAL_CAPITAL + s.cumulative_pnl + unrealized

        # 3. Track drawdown on TOTAL equity (realized + unrealized) (THE FIX)
        if total_equity > peak_total_equity:
            peak_total_equity = total_equity
        dd = (peak_total_equity - total_equity) / peak_total_equity if peak_total_equity > 0 else 0.0
        if dd > max_total_dd:
            max_total_dd = dd

        # 4. Record total equity point
        s.equity_curve.append(total_equity)

    # ── Build result ──────────────────────────────────────────────────
    # Pad equity curve if grid activated late
    while len(s.equity_curve) < n:
        s.equity_curve.append(INITIAL_CAPITAL)

    range_eff = (s.bars_with_fill / s.active_bars * 100) if s.active_bars > 0 else 0.0
    final_unrealized = _unrealized_pnl(s, close[-1])
    final_total_equity = INITIAL_CAPITAL + s.cumulative_pnl + final_unrealized

    return {
        "grid_fills": s.fill_count,
        "realized_pnl": round(s.cumulative_pnl, 2),
        "unrealized_pnl": round(final_unrealized, 2),
        "total_pnl": round(s.cumulative_pnl + final_unrealized, 2),
        "total_fees": round(s.total_fees, 2),
        "max_drawdown": round(max_total_dd, 4),
        "open_lots": round(s.open_lots, 4),
        "avg_entry_price": round(s.avg_entry_price, 2),
        "grid_active_bars": s.active_bars,
        "total_bars": n,
        "range_efficiency": round(range_eff, 2),
        "equity_curve": [round(e, 2) for e in s.equity_curve],
        "fill_events": s.fill_events,
        "final_equity": round(final_total_equity, 2),
        "return_pct": round((final_total_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
        "deactivation_bar": s.deactivation_bar,
    }


def _empty_result(total_bars: int, reason: str = "") -> dict:
    return {
        "grid_fills": 0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "total_pnl": 0.0,
        "total_fees": 0.0,
        "max_drawdown": 0.0,
        "open_lots": 0.0,
        "avg_entry_price": 0.0,
        "grid_active_bars": 0,
        "total_bars": total_bars,
        "range_efficiency": 0.0,
        "equity_curve": [INITIAL_CAPITAL] * total_bars,
        "fill_events": [],
        "final_equity": INITIAL_CAPITAL,
        "return_pct": 0.0,
        "reason": reason,
    }


# ── Self-test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from scripts.edge_search_all import load_asset_data

    print("Loading XAUUSD D1 data...")
    df = load_asset_data("XAUUSD")

    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
    }

    configs = [
        ("Tight_10x1",   10, 1.0, 0.01),
        ("Tight_10x2",   10, 2.0, 0.01),
        ("Medium_20x1",  20, 1.0, 0.01),
        ("Medium_20x2",  20, 2.0, 0.01),
        ("Wide_30x2",    30, 2.0, 0.01),
        ("Dense_50x1",   50, 1.0, 0.01),
    ]

    n = len(ohlcv["close"])
    print(f"XAUUSD Grid | {n} bars | ~${ohlcv['close'][-1]:.0f}")
    print(f"{'='*80}")
    print(f"{'Config':<16} {'Fills':>6} {'Real':>9} {'Unreal':>9} {'Total':>9} {'MaxDD%':>7} {'Lots':>6} {'Eff%':>5}")
    print(f"{'-'*80}")
    for label, gc, am, ov in configs:
        cfg = GridConfig(symbol="XAUUSD", range_method="atr", atr_period=20,
                         atr_multiplier=am, grid_count=gc, order_volume=ov)
        r = run_grid_backtest(cfg, ohlcv)
        print(f"{label:<16} {r['grid_fills']:>6} {r['realized_pnl']:>9.1f} {r['unrealized_pnl']:>9.1f} {r['total_pnl']:>9.1f} {r['max_drawdown']*100:>6.2f}% {r['open_lots']:>6.2f} {r['range_efficiency']:>4.1f}%")
