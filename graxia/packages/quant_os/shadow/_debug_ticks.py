"""Debug tick fetching on Pepperstone."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, UTC

ok = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
if not ok:
    print(f"FAILED: {mt5.last_error()}")
    exit(1)

acct = mt5.account_info()
print(f"Server: {acct.server}")
print(f"System UTC: {datetime.now(UTC).isoformat()}")

# Test 1: symbol_info_tick
tick = mt5.symbol_info_tick("XAUUSD")
if tick:
    tick_dt = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
    print(f"symbol_info_tick: bid={tick.bid} ask={tick.ask} time={tick_dt.isoformat()}")
else:
    err = mt5.last_error()
    print(f"symbol_info_tick: None ({err})")

# Test 2: copy_ticks_range with UTC-aware datetime
now = datetime.now(UTC)
fr = now - timedelta(minutes=5)
print(f"Query: from={fr.isoformat()} to={now.isoformat()}")
ticks = mt5.copy_ticks_range("XAUUSD", fr, now, mt5.COPY_TICKS_ALL)
if ticks is not None:
    print(f"copy_ticks_range: {len(ticks)} ticks")
    if len(ticks) > 0:
        first = ticks[0]
        last = ticks[-1]
        print(f"  first: {int(first[0])} -> {datetime.fromtimestamp(int(first[0]), tz=UTC).isoformat()}")
        print(f"  last: {int(last[0])} -> {datetime.fromtimestamp(int(last[0]), tz=UTC).isoformat()}")
else:
    err = mt5.last_error()
    print(f"copy_ticks_range: None ({err})")

# Test 3: copy_ticks_from
ticks_from = mt5.copy_ticks_from("XAUUSD", 0, 5, mt5.COPY_TICKS_ALL)
if ticks_from is not None:
    print(f"copy_ticks_from: {len(ticks_from)} ticks")
else:
    err = mt5.last_error()
    print(f"copy_ticks_from: None ({err})")

# Test 4: Check symbol
sym = mt5.symbol_info("XAUUSD")
if sym:
    print(f"XAUUSD visible={sym.visible} trade_mode={sym.trade_mode}")
else:
    print("XAUUSD: not found")

# Test 5: Wider window
fr_wide = now - timedelta(hours=24)
print(f"Wide query: from={fr_wide.isoformat()} to={now.isoformat()}")
ticks_wide = mt5.copy_ticks_range("XAUUSD", fr_wide, now, mt5.COPY_TICKS_ALL)
if ticks_wide is not None:
    print(f"copy_ticks_range (24h): {len(ticks_wide)} ticks")
else:
    err = mt5.last_error()
    print(f"copy_ticks_range (24h): None ({err})")

mt5.shutdown()
