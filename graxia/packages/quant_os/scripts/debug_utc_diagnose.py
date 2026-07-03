"""Diagnose copy_ticks_range UTC timestamps."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, UTC

mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=15000)
mt5.symbol_select("XAUUSD", True)
tick = mt5.symbol_info_tick("XAUUSD")
now_utc = datetime.now(UTC)
print(f"Now UTC: {now_utc.isoformat()}")

for sec in [10, 5, 3, 2, 1]:
    fr = now_utc - timedelta(seconds=sec)
    to = now_utc
    tcks = mt5.copy_ticks_range("XAUUSD", fr, to, mt5.COPY_TICKS_INFO)
    if tcks is not None and len(tcks) > 0:
        last = tcks[-1]
        lt = int(last["time"])
        lt_dt = datetime.fromtimestamp(lt, tz=UTC)
        age_s = (now_utc - lt_dt).total_seconds()
        bid = float(last["bid"])
        ask = float(last["ask"])
        flags = int(last["flags"])
        print(f"{sec}s: utc={lt_dt.isoformat()} age={age_s:.0f}s bid={bid} ask={ask} flags={flags}")
    else:
        print(f"{sec}s: no ticks")

mt5.shutdown()
