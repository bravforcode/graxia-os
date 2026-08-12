#!/usr/bin/env python3
"""
XAUUSD Stop-Loss Calculator
===========================
Computes stop-loss price distance based on a fixed $6.30 risk threshold.

Formula:
    distance = 6.30 / (lot_size * 100)
    stop_buy  = entry_price - distance   (long position)
    stop_sell = entry_price + distance   (short position)

Verification:
    0.1 lot  -> distance = $0.63
    1.0 lot  -> distance = $0.063

Usage:
    python scripts/stop_calculator.py
"""

import sys


def compute_stop(lot_size: float, entry_price: float) -> dict:
    """Calculate stop distances and levels for XAUUSD."""
    if lot_size <= 0:
        raise ValueError("lot_size must be > 0")
    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")

    distance = 6.30 / (lot_size * 100)
    stop_buy = entry_price - distance
    stop_sell = entry_price + distance

    return {
        "lot_size": lot_size,
        "entry_price": entry_price,
        "distance": round(distance, 5),
        "stop_buy": round(stop_buy, 2),
        "stop_sell": round(stop_sell, 2),
    }


def main() -> None:
    try:
        lot_size = float(input("Enter lot size (e.g. 0.1, 0.5, 1.0): "))
        entry_price = float(input("Enter current XAUUSD price (e.g. 2330.50): "))
    except ValueError:
        print("Error: please enter numeric values.", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute_stop(lot_size, entry_price)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n===== XAUUSD STOP-LOSS CALCULATION =====")
    print(f"  Lot size:          {result['lot_size']}")
    print(f"  Entry price:       ${result['entry_price']:.2f}")
    print(f"  Stop distance:     ${result['distance']:.5f}")
    print(f"  Stop-loss (BUY):   ${result['stop_buy']:.2f}")
    print(f"  Stop-loss (SELL):  ${result['stop_sell']:.2f}")
    print("=========================================")

    # Verification block
    if abs(lot_size - 0.1) < 1e-9:
        assert abs(result["distance"] - 0.63) < 1e-4, "FAIL: 0.1 lot distance != 0.63"
        print("[OK] 0.1 lot -> distance = $0.63")
    elif abs(lot_size - 1.0) < 1e-9:
        assert abs(result["distance"] - 0.063) < 1e-4, "FAIL: 1.0 lot distance != 0.063"
        print("[OK] 1.0 lot -> distance = $0.063")


if __name__ == "__main__":
    main()
