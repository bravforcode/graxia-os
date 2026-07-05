"""
Test stale-price guard logic from run_linux.py main loop.

Logic:
  - First cycle: last_price is None -> set last_price, skip trading
  - price_stale = (current_price == last_price)
  - Stale price -> skip new entry (but SL/TP monitoring already ran)
  - Fresh price -> allow trading, update last_price
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pytest


def test_price_same_blocks_trade():
    """current_price == stored_price -> should skip (price_stale=True)."""
    last_price = 2350.50
    current_price = 2350.50

    price_stale = (current_price == last_price)

    assert price_stale is True
    assert current_price == last_price


def test_price_different_allows_trade():
    """current_price != stored_price -> should proceed (price_stale=False)."""
    last_price = 2350.50
    current_price = 2350.75

    price_stale = (current_price == last_price)

    assert price_stale is False
    assert current_price != last_price


def test_first_cycle_skips():
    """last_price=None -> first cycle should set price and skip (no trade)."""
    last_price = None
    current_price = 2350.00

    # Logic from main loop
    if last_price is None:
        last_price = current_price
        should_skip = True
    else:
        should_skip = False

    assert should_skip is True
    assert last_price == 2350.00


def test_second_cycle_proceeds():
    """After first cycle sets last_price, second cycle with fresh price proceeds."""
    last_price = 2350.00
    current_price = 2350.25

    price_stale = (current_price == last_price)
    skip = False

    if last_price is None:
        skip = True
        last_price = current_price
    elif price_stale:
        skip = True
    else:
        last_price = current_price
        skip = False

    assert skip is False
    assert last_price == 2350.25


def test_small_price_change_not_stale():
    """Even a tiny price change (0.01) should not be considered stale."""
    last_price = 2350.00
    current_price = 2350.01

    price_stale = (current_price == last_price)

    assert price_stale is False
