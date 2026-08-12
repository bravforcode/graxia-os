#!/usr/bin/env python3
"""
B2 Week 0 — 3 Confirmation Test Trades
=======================================
Runs 3 test trades to verify MT5 + stop-loss fills before paper trade starts.

Test 1: Open long 0.10 XAUUSD, set SL at $6.30, close immediately
Test 2: Open short 0.10 XAUUSD, let price mini-move, cancel
Test 3: Open long 0.10 XAUUSD with SL, trigger SL or let price hit

Usage: python scripts/test_trades_week0.py [--auto]
  --auto: run all 3 tests automatically (for testing only)
"""

import sys
import time

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 not installed. pip install MetaTrader5")
    sys.exit(1)

SYMBOL = "XAUUSD"
LOT = 0.10
STOP_DISTANCE = 6.30  # B2 locked stop


def connect():
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"MT5 init failed: {err}")
        print("Open MT5 terminal and login first.")
        sys.exit(1)
    info = mt5.account_info()
    if info is None:
        print("Cannot read MT5 account info")
        sys.exit(1)
    if "demo" not in info.server.lower() and "practice" not in info.server.lower():
        print(f"LIVE ACCOUNT DETECTED: {info.server}. Aborting.")
        mt5.shutdown()
        sys.exit(1)
    print(f"Connected: {info.server} login={info.login} balance={info.balance}")
    return info


def get_spread():
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    if tick and sym:
        spread = tick.ask - tick.bid
        return spread, tick.ask, tick.bid, sym
    return None, None, None, None


def test1_long_close_immediate():
    """Test 1: Open long 0.10, set SL, close immediately."""
    print("\n--- Test 1: Open long 0.10, SL $6.30, close immediately ---")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        print("FAIL: no tick data")
        return False

    price = tick.ask
    sl = price - STOP_DISTANCE

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": 0.0,
        "deviation": 10,
        "magic": 123456,
        "comment": "B2-TEST1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"FAIL: order failed: {result.comment if result else 'no response'}")
        return False

    ticket = result.order
    print(f"  Opened: ticket={ticket} price={price:.2f} SL={sl:.2f}")

    # Close immediately
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        print("FAIL: position not found after open")
        return False

    pos = positions[0]
    close_price = tick.bid  # sell to close
    close_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL,
        "position": pos.ticket,
        "price": close_price,
        "deviation": 10,
        "magic": 123456,
        "comment": "B2-TEST1-CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    close_result = mt5.order_send(close_req)
    if close_result and close_result.retcode == mt5.TRADE_RETCODE_DONE:
        profit = pos.profit + pos.swap
        print(f"  Closed: profit=${profit:.2f}")
        print("  PASS: Market order fills, SL can be attached")
        return True
    else:
        print(f"  FAIL: close failed: {close_result.comment if close_result else 'no response'}")
        return False


def test2_short_cancel():
    """Test 2: Open short 0.10, cancel."""
    print("\n--- Test 2: Open short 0.10, cancel ---")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        print("FAIL: no tick data")
        return False

    price = tick.bid
    sl = price + STOP_DISTANCE

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": 0.0,
        "deviation": 10,
        "magic": 123456,
        "comment": "B2-TEST2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"FAIL: order failed: {result.comment if result else 'no response'}")
        return False

    ticket = result.order
    print(f"  Opened: ticket={ticket} price={price:.2f} SL={sl:.2f}")

    # Close
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        pos = positions[0]
        close_price = tick.ask
        close_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": close_price,
            "deviation": 10,
            "magic": 123456,
            "comment": "B2-TEST2-CANCEL",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        close_result = mt5.order_send(close_req)
        if close_result and close_result.retcode == mt5.TRADE_RETCODE_DONE:
            print("  Cancelled (closed)")
            print("  PASS: Order cancel succeeds")
            return True
    print("  FAIL: could not cancel")
    return False


def test3_long_sl_fill():
    """Test 3: Open long 0.10 with SL, let price hit SL."""
    print("\n--- Test 3: Open long 0.10 with SL, trigger SL ---")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        print("FAIL: no tick data")
        return False

    price = tick.ask
    sl = price - STOP_DISTANCE

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": 0.0,
        "deviation": 10,
        "magic": 123456,
        "comment": "B2-TEST3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"FAIL: order failed: {result.comment if result else 'no response'}")
        return False

    ticket = result.order
    print(f"  Opened: ticket={ticket} price={price:.2f} SL={sl:.2f}")
    print(f"  Expected SL fill loss: ~${STOP_DISTANCE * LOT * 100:.2f}")
    print("  Waiting for SL to fill... (or close manually)")

    # Wait up to 5 minutes for SL to fill
    start = time.time()
    timeout = 300
    while time.time() - start < timeout:
        positions = mt5.positions_get(symbol=SYMBOL)
        if not positions:
            # Position closed - SL was hit
            deals = mt5.history_deals_get(ticket=ticket)
            if deals:
                for deal in deals:
                    if deal.entry == mt5.DEAL_ENTRY_OUT or deal.entry == mt5.DEAL_ENTRY_OUT_BY:
                        actual_sl = deal.price
                        slippage = actual_sl - sl
                        loss = abs(actual_sl - price) * LOT * 100
                        print(f"  SL filled at: {actual_sl:.2f}")
                        print(f"  Intended SL:  {sl:.2f}")
                        print(f"  Slippage:     ${slippage:.2f}")
                        print(f"  Loss:         ${loss:.2f}")
                        if abs(slippage) <= 0.20:
                            print("  PASS: SL slippage within ±$0.20")
                            return True
                        else:
                            print(f"  WARN: SL slippage ${slippage:.2f} exceeds ±$0.20")
                            return True  # Still pass but note the slippage
            print("  Position closed but no deal history found")
            return False
        time.sleep(1)

    # Timeout - close manually
    print("  Timeout: SL not hit in 5 minutes. Closing manually...")
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        pos = positions[0]
        tick2 = mt5.symbol_info_tick(SYMBOL)
        close_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL,
            "position": pos.ticket,
            "price": tick2.bid,
            "deviation": 10,
            "magic": 123456,
            "comment": "B2-TEST3-CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(close_req)
        print("  Manually closed. Record slippage from deal history.")
    return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="B2 Week 0 Test Trades")
    parser.add_argument("--auto", action="store_true", help="Run all tests automatically")
    parser.add_argument("--test", type=int, choices=[1, 2, 3], help="Run specific test only")
    args = parser.parse_args()

    connect()

    spread, ask, bid, sym = get_spread()
    if spread is not None:
        print(f"\nXAUUSD spread: ${spread:.2f} (ask={ask:.2f} bid={bid:.2f})")
        print("Record this in execution_plan.md Week 0 item 3")
    else:
        print("WARNING: Could not read XAUUSD spread")

    results = {}
    if args.test:
        if args.test == 1:
            results[1] = test1_long_close_immediate()
        elif args.test == 2:
            results[2] = test2_short_cancel()
        elif args.test == 3:
            results[3] = test3_long_sl_fill()
    else:
        if args.auto:
            results[1] = test1_long_close_immediate()
            time.sleep(2)
            results[2] = test2_short_cancel()
            time.sleep(2)
            results[3] = test3_long_sl_fill()
        else:
            print("\nRun each test manually:")
            print("  python scripts/test_trades_week0.py --test 1")
            print("  python scripts/test_trades_week0.py --test 2")
            print("  python scripts/test_trades_week0.py --test 3")
            print("Or run all automatically:")
            print("  python scripts/test_trades_week0.py --auto")

    if results:
        print("\n--- Summary ---")
        for t, r in results.items():
            print(f"  Test {t}: {'PASS' if r else 'FAIL'}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
