"""Check native vs canonical price coherence."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, UTC

mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=15000)
mt5.symbol_select("XAUUSD", True)
tick = mt5.symbol_info_tick("XAUUSD")
print(f"Native: bid={tick.bid} ask={tick.ask}")

now_utc = datetime.now(UTC)
tcks = mt5.copy_ticks_range("XAUUSD", now_utc - timedelta(seconds=5), now_utc, mt5.COPY_TICKS_INFO)
if tcks is not None and len(tcks) > 0:
    last = tcks[-1]
    bid = float(last["bid"])
    ask = float(last["ask"])
    flags = int(last["flags"])
    bd = abs(tick.bid - bid)
    ad = abs(tick.ask - ask)
    print(f"Canonical: bid={bid} ask={ask} flags={flags}")
    print(f"Div: bid={bd:.4f} ask={ad:.4f}")
    print(f"Coherent: {bd < 0.5 and ad < 0.5}")
mt5.shutdown()
