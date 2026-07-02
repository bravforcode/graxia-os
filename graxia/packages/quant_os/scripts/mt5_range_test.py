"""Test MT5 data range limits."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from time import mktime
import pandas as pd

mt5.initialize()

# Test various ranges
for label, days in [("1yr", 365), ("2yr", 730), ("3yr", 1095), ("5yr", 1825), ("7yr", 2555), ("10yr", 3650)]:
    end_ts = int(mktime(datetime.now().timetuple()))
    start_ts = int(mktime((datetime.now() - timedelta(days=days)).timetuple()))
    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, start_ts, end_ts)
    if rates is not None and len(rates) > 0:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        print(f"{label}: {len(df)} bars, first={df['time'].iloc[0]}, last={df['time'].iloc[-1]}")
    else:
        print(f"{label}: NO DATA (error: {mt5.last_error()})")

# Also test copy_rates_from_pos with a large count
rates2 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M15, 0, 100000)
if rates2 is not None:
    print(f"\nFrom-pos (100k): {len(rates2)} bars")
else:
    print("\nFrom-pos (100k): NO DATA")

mt5.shutdown()
