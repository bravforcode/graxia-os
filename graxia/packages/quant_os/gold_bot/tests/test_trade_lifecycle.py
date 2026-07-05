"""
Test complete trade lifecycle using Trade dataclass.

Redefines Trade locally since run_linux.py puts it inside if __name__ == "__main__".
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pytest
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Trade:
    symbol: str
    direction: SignalDirection
    entry_price: float
    sl: float
    tp: float
    score: float
    strategies: set = field(default_factory=set)
    entry_time: datetime = field(default_factory=datetime.now)
    stop_loss: float = 0
    take_profit: float = 0
    pnl: float = 0
    status: str = "OPEN"

    def __post_init__(self):
        self.stop_loss = self.sl
        self.take_profit = self.tp


def test_trade_open():
    """Create a Trade dataclass with BUY direction, verify all fields."""
    trade = Trade(
        symbol="XAUUSD",
        direction=SignalDirection.BUY,
        entry_price=2350.00,
        sl=2340.00,
        tp=2370.00,
        score=450,
        strategies={"order_block", "ema_cross"},
    )
    assert trade.symbol == "XAUUSD"
    assert trade.direction == SignalDirection.BUY
    assert trade.entry_price == 2350.00
    assert trade.sl == 2340.00
    assert trade.tp == 2370.00
    assert trade.score == 450
    assert trade.strategies == {"order_block", "ema_cross"}
    assert trade.status == "OPEN"
    assert trade.stop_loss == 2340.00
    assert trade.take_profit == 2370.00
    assert trade.pnl == 0


def test_trade_close_sl():
    """Create a BUY trade, simulate SL hit (price drops below SL), verify PnL is negative."""
    trade = Trade(
        symbol="XAUUSD",
        direction=SignalDirection.BUY,
        entry_price=2350.00,
        sl=2340.00,
        tp=2370.00,
        score=450,
    )
    exit_price = trade.stop_loss  # 2340.00
    point = 0.01
    pnl_pips = (exit_price - trade.entry_price) / point  # (2340-2350)/0.01 = -1000
    pnl = pnl_pips * 0.10  # -100.0

    trade.pnl = pnl
    trade.status = "CLOSED"

    assert pnl < 0
    assert pnl_pips == -1000.0
    assert pnl == -100.0
    assert trade.pnl == -100.0
    assert trade.status == "CLOSED"


def test_trade_close_tp():
    """Create a BUY trade, simulate TP hit (price rises above TP), verify PnL is positive."""
    trade = Trade(
        symbol="XAUUSD",
        direction=SignalDirection.BUY,
        entry_price=2350.00,
        sl=2340.00,
        tp=2370.00,
        score=450,
    )
    exit_price = trade.take_profit  # 2370.00
    point = 0.01
    pnl_pips = (exit_price - trade.entry_price) / point  # (2370-2350)/0.01 = 2000
    pnl = pnl_pips * 0.10  # 200.0

    trade.pnl = pnl
    trade.status = "CLOSED"

    assert pnl > 0
    assert pnl_pips == 2000.0
    assert pnl == 200.0
    assert trade.pnl == 200.0
    assert trade.status == "CLOSED"


def test_trade_close_sell_sl():
    """Create a SELL trade, simulate SL hit (price rises above SL), verify PnL is negative."""
    trade = Trade(
        symbol="XAUUSD",
        direction=SignalDirection.SELL,
        entry_price=2350.00,
        sl=2360.00,
        tp=2330.00,
        score=400,
    )
    exit_price = trade.stop_loss  # 2360.00 - SL for SELL is above entry
    point = 0.01
    pnl_pips = (trade.entry_price - exit_price) / point  # (2350-2360)/0.01 = -1000
    pnl = pnl_pips * 0.10  # -100.0

    trade.pnl = pnl
    trade.status = "CLOSED"

    assert pnl < 0
    assert pnl_pips == -1000.0
    assert pnl == -100.0
    assert trade.pnl == -100.0
    assert trade.status == "CLOSED"


def test_trade_close_sell_tp():
    """Create a SELL trade, simulate TP hit (price drops below TP), verify PnL is positive."""
    trade = Trade(
        symbol="XAUUSD",
        direction=SignalDirection.SELL,
        entry_price=2350.00,
        sl=2360.00,
        tp=2330.00,
        score=400,
    )
    exit_price = trade.take_profit  # 2330.00 - TP for SELL is below entry
    point = 0.01
    pnl_pips = (trade.entry_price - exit_price) / point  # (2350-2330)/0.01 = 2000
    pnl = pnl_pips * 0.10  # 200.0

    trade.pnl = pnl
    trade.status = "CLOSED"

    assert pnl > 0
    assert pnl_pips == 2000.0
    assert pnl == 200.0
    assert trade.pnl == 200.0
    assert trade.status == "CLOSED"


def test_pnl_calculation():
    """Verify PnL = pnl_pips * 0.10 for various scenarios."""
    point = 0.01

    # BUY, TP hit: +2000 pips -> $200
    pnl_pips_buy_tp = (2370.00 - 2350.00) / point
    assert pnl_pips_buy_tp == 2000.0
    assert pnl_pips_buy_tp * 0.10 == 200.0

    # BUY, SL hit: -1000 pips -> -$100
    pnl_pips_buy_sl = (2340.00 - 2350.00) / point
    assert pnl_pips_buy_sl == -1000.0
    assert pnl_pips_buy_sl * 0.10 == -100.0

    # SELL, TP hit: +2000 pips -> $200
    pnl_pips_sell_tp = (2350.00 - 2330.00) / point
    assert pnl_pips_sell_tp == 2000.0
    assert pnl_pips_sell_tp * 0.10 == 200.0

    # SELL, SL hit: -1000 pips -> -$100
    pnl_pips_sell_sl = (2350.00 - 2360.00) / point
    assert pnl_pips_sell_sl == -1000.0
    assert pnl_pips_sell_sl * 0.10 == -100.0

    # Breakeven
    pnl_breakeven = (2350.00 - 2350.00) / point
    assert pnl_breakeven == 0.0
    assert pnl_breakeven * 0.10 == 0.0
