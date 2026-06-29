#!/usr/bin/env python3
"""Fix test 2: short + close"""
import MetaTrader5 as mt5
import time

mt5.initialize(timeout=15000)
info = mt5.account_info()
print("Connected: {} @ {} balance={}".format(info.login, info.server, info.balance))

symbol = "XAUUSD"
mt5.symbol_select(symbol, True)
tick = mt5.symbol_info_tick(symbol)
print("ask={:.2f} bid={:.2f}".format(tick.ask, tick.bid))

price = tick.bid
sl = price + 6.30
req = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": 0.10,
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
    err = result.comment if result else "none"
    print("OPEN FAIL: " + str(err))
    mt5.shutdown()
    exit(1)

print("OPENED: ticket={} price={:.2f} SL={:.2f}".format(result.order, price, sl))
time.sleep(2)

positions = mt5.positions_get(symbol=symbol)
if not positions:
    print("No position found")
    mt5.shutdown()
    exit(1)

pos = positions[0]
print("Position: ticket={} type={} volume={} profit={}".format(pos.ticket, pos.type, pos.volume, pos.profit))

tick2 = mt5.symbol_info_tick(symbol)
close_price = tick2.ask
print("Closing at ask={:.2f}".format(close_price))

close_req = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": pos.volume,
    "type": mt5.ORDER_TYPE_BUY,
    "position": pos.ticket,
    "price": close_price,
    "deviation": 20,
    "magic": 123456,
    "comment": "B2-TEST2-CLOSE",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}
cr = mt5.order_send(close_req)
if cr and cr.retcode == mt5.TRADE_RETCODE_DONE:
    print("CLOSED: profit={:.2f}".format(pos.profit))
    print("TEST 2 PASS")
else:
    err = cr.comment if cr else "none"
    print("CLOSE FAIL: " + str(err))
    
    close_req["type_filling"] = mt5.ORDER_FILLING_FOK
    cr2 = mt5.order_send(close_req)
    if cr2 and cr2.retcode == mt5.TRADE_RETCODE_DONE:
        print("CLOSED (FOK): profit={:.2f}".format(pos.profit))
        print("TEST 2 PASS")
    else:
        err2 = cr2.comment if cr2 else "none"
        print("CLOSE FAIL FOK: " + str(err2))

mt5.shutdown()
