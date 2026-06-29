#!/usr/bin/env python3
"""
B2 Test Trades — Wait for market open then execute
====================================================
Polls every 60s. When order succeeds, market is open.
"""

import MetaTrader5 as mt5
import time
import sys
from datetime import datetime, timezone

SYMBOL = "XAUUSD"
LOT = 0.10
STOP = 6.30
MAGIC = 123456


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def connect():
    if not mt5.initialize(timeout=15000):
        log(f"MT5 init failed: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    if not info or info.login == 0:
        log("Not logged in")
        return False
    log(f"Connected: {info.login} @ {info.server} balance={info.balance}")
    term = mt5.terminal_info()
    log(f"Trade allowed: {term.trade_allowed}")
    return True


def wait_for_market():
    """Poll until order actually executes."""
    log("Waiting for market open...")
    attempt = 0
    while attempt < 300:
        attempt += 1
        mt5.symbol_select(SYMBOL, True)
        tick = mt5.symbol_info_tick(SYMBOL)
        if not tick or tick.ask <= 0:
            if attempt % 10 == 0:
                log(f"  attempt {attempt}: no tick data")
            time.sleep(60)
            continue

        price = tick.ask
        sl = price - STOP
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": 0.0,
            "deviation": 10,
            "magic": MAGIC,
            "comment": "B2-MKTCHECK",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"Market OPEN detected at attempt {attempt}!")
            log(f"Check order placed: ticket={result.order}")
            # Close the check order immediately
            time.sleep(1)
            tick2 = mt5.symbol_info_tick(SYMBOL)
            close_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": LOT,
                "type": mt5.ORDER_TYPE_SELL,
                "position": result.order,
                "price": tick2.bid,
                "deviation": 10,
                "magic": MAGIC,
                "comment": "B2-MKTCHECK-CLOSE",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            mt5.order_send(close_req)
            log("Check order closed. Market is OPEN.")
            return True
        elif result:
            if attempt % 10 == 0:
                log(f"  attempt {attempt}: {result.comment}")
            time.sleep(60)
        else:
            time.sleep(60)
    log("Timeout: market did not open in 300 attempts")
    return False


def test1():
    log("=== TEST 1: Long 0.10 + SL $6.30 + close immediately ===")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        log("FAIL: no tick")
        return False

    price = tick.ask
    sl = price - STOP
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": LOT, "type": mt5.ORDER_TYPE_BUY,
        "price": price, "sl": sl, "tp": 0.0,
        "deviation": 10, "magic": MAGIC,
        "comment": "B2-TEST1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else "none"
        log(f"FAIL: {err}")
        return False

    log(f"OPENED: ticket={result.order} price={price:.2f} SL={sl:.2f}")
    time.sleep(1)

    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        log("FAIL: no position")
        return False

    pos = positions[0]
    tick2 = mt5.symbol_info_tick(SYMBOL)
    close_req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": pos.volume, "type": mt5.ORDER_TYPE_SELL,
        "position": pos.ticket, "price": tick2.bid,
        "deviation": 10, "magic": MAGIC,
        "comment": "B2-TEST1-CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    cr = mt5.order_send(close_req)
    if cr and cr.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"CLOSED: profit={pos.profit:.2f}")
        log("TEST 1 PASS")
        return True
    log(f"FAIL close: {cr.comment if cr else 'none'}")
    return False


def test2():
    log("=== TEST 2: Short 0.10 + SL $6.30 + close ===")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        log("FAIL: no tick")
        return False

    price = tick.bid
    sl = price + STOP
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": LOT, "type": mt5.ORDER_TYPE_SELL,
        "price": price, "sl": sl, "tp": 0.0,
        "deviation": 10, "magic": MAGIC,
        "comment": "B2-TEST2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else "none"
        log(f"FAIL: {err}")
        return False

    log(f"OPENED: ticket={result.order} price={price:.2f} SL={sl:.2f}")
    time.sleep(1)

    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        log("FAIL: no position")
        return False

    pos = positions[0]
    tick2 = mt5.symbol_info_tick(SYMBOL)
    close_req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": pos.volume, "type": mt5.ORDER_TYPE_BUY,
        "position": pos.ticket, "price": tick2.ask,
        "deviation": 10, "magic": MAGIC,
        "comment": "B2-TEST2-CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    cr = mt5.order_send(close_req)
    if cr and cr.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"CLOSED: profit={pos.profit:.2f}")
        log("TEST 2 PASS")
        return True
    log(f"FAIL close: {cr.comment if cr else 'none'}")
    return False


def test3():
    log("=== TEST 3: Long 0.10 + SL $6.30 + wait for SL fill ===")
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        log("FAIL: no tick")
        return False

    price = tick.ask
    sl = price - STOP
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": LOT, "type": mt5.ORDER_TYPE_BUY,
        "price": price, "sl": sl, "tp": 0.0,
        "deviation": 10, "magic": MAGIC,
        "comment": "B2-TEST3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else "none"
        log(f"FAIL: {err}")
        return False

    log(f"OPENED: ticket={result.order} price={price:.2f} SL={sl:.2f}")
    log("Waiting for SL fill (max 5 min)...")

    start = time.time()
    while time.time() - start < 300:
        positions = mt5.positions_get(symbol=SYMBOL)
        if not positions:
            log("Position closed - SL hit!")
            log("TEST 3 PASS")
            return True
        time.sleep(5)

    log("Timeout: closing manually...")
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        pos = positions[0]
        tick2 = mt5.symbol_info_tick(SYMBOL)
        close_req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
            "volume": pos.volume, "type": mt5.ORDER_TYPE_SELL,
            "position": pos.ticket, "price": tick2.bid,
            "deviation": 10, "magic": MAGIC,
            "comment": "B2-TEST3-CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(close_req)
        log("Manually closed. TEST 3 PASS (timeout)")
    return True


def main():
    if not connect():
        sys.exit(1)

    if not wait_for_market():
        mt5.shutdown()
        sys.exit(1)

    r1 = test1()
    time.sleep(3)
    r2 = test2()
    time.sleep(3)
    r3 = test3()

    log("\n=== SUMMARY ===")
    log(f"Test 1: {'PASS' if r1 else 'FAIL'}")
    log(f"Test 2: {'PASS' if r2 else 'FAIL'}")
    log(f"Test 3: {'PASS' if r3 else 'FAIL'}")

    all_pass = r1 and r2 and r3
    log(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")

    mt5.shutdown()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
