"""G2: Read-only MT5 snapshot for preflight. No order_send."""

import hashlib
import json
from datetime import UTC, datetime

import MetaTrader5 as mt5

res = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
if not res:
    print("FAIL:", mt5.last_error())
    exit(1)

info = mt5.account_info()
profile_hash = hashlib.sha256(str(info.login).encode()).hexdigest()

# Positions and orders (read-only)
positions = mt5.positions_get()
orders = mt5.orders_get()
position_count = len(positions) if positions else 0
order_count = len(orders) if orders else 0

# Symbol data
mt5.symbol_select("XAUUSD", True)
tick = mt5.symbol_info_tick("XAUUSD")
sym = mt5.symbol_info("XAUUSD")

# Margin estimate for XAUUSD 0.01 lot BUY at current ask
volume = 0.01
entry = tick.ask
margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, "XAUUSD", volume, entry)

# Order check (preflight only, NOT execution)
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": "XAUUSD",
    "volume": volume,
    "type": mt5.ORDER_TYPE_BUY,
    "price": entry,
    "sl": entry - 10 * sym.point,
    "tp": entry + 10 * sym.point,
    "deviation": 10,
    "magic": 123456,
    "comment": "G2 PREFLIGHT DRY RUN",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}
check = mt5.order_check(request)

output = {
    "generated_at_utc": datetime.now(UTC).isoformat(),
    "profile_hash": profile_hash,
    "position_count": position_count,
    "pending_order_count": order_count,
    "margin_estimate_0_01_lot": margin,
    "order_check": {
        "retcode": check.retcode,
        "comment": check.comment,
        "balance": check.balance if check else None,
        "equity": check.equity if check else None,
        "margin": check.margin if check else None,
        "margin_free": check.margin_free if check else None,
        "margin_level": check.margin_level if check else None,
    }
    if check
    else None,
    "xauusd": {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": round(tick.ask - tick.bid, 2),
        "digits": sym.digits,
        "point": sym.point,
        "trade_stops_level": sym.trade_stops_level,
        "trade_freeze_level": sym.trade_freeze_level,
    },
    "note": "READ-ONLY PREFLIGHT. No order was submitted.",
}
mt5.shutdown()
with open(r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\preflight\g2_mt5_snapshot.json", "w") as f:
    json.dump(output, f, indent=2)
print(json.dumps(output, indent=2))
