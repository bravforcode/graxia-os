"""Diagnose: COPY_TICKS_INFO vs COPY_TICKS_ALL, all windows."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, UTC

mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=15000)
mt5.symbol_select("XAUUSD", True)
tick = mt5.symbol_info_tick("XAUUSD")
print(f"Native: bid={tick.bid} ask={tick.ask} time_msc={tick.time_msc}")

now_utc = datetime.now(UTC)

for name, flag in [("INFO", mt5.COPY_TICKS_INFO), ("ALL", mt5.COPY_TICKS_ALL)]:
    print(f"\n=== {name} ===")
    for sec in [10, 5, 3, 2, 1]:
        fr = now_utc - timedelta(seconds=sec)
        to = now_utc
        tcks = mt5.copy_ticks_range("XAUUSD", fr, to, flag)
        if tcks is not None and len(tcks) > 0:
            last = tcks[-1]
            lt = int(last["time"])
            lt_dt = datetime.fromtimestamp(lt, tz=UTC)
            age_s = (now_utc - lt_dt).total_seconds()
            bd = abs(tick.bid - last["bid"])
            print(f"  {sec}s: age={age_s:.0f}s bid={last['bid']} ask={last['ask']} "
                  f"div={bd:.2f} flags={last['flags']} count={len(tcks)}")
        else:
            print(f"  {sec}s: no ticks")

mt5.shutdown()
