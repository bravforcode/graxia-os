"""Quick MT5 10yr M15 test."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from time import mktime
import pandas as pd

mt5.initialize()

end_ts = int(mktime(datetime.now().timetuple()))
start_ts = int(mktime((datetime.now() - timedelta(days=365*10)).timetuple()))
rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, start_ts, end_ts)
if rates is not None and len(rates) > 0:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    print(f"MT5 10yr M15: {len(df)} bars")
    print(f"Range: {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
    print(f"Columns: {list(df.columns)}")
    print("\nFirst 3 rows:")
    print(df[["time","open","high","low","close","volume"]].head(3).to_string())
    print("\nLast 3 rows:")
    print(df[["time","open","high","low","close","volume"]].tail(3).to_string())
    
    # Save to parquet
    out = "data/mt5_xauusd_m15_10yr.parquet"
    df.to_parquet(out, index=False)
    print(f"\nSaved to {out}")
else:
    print(f"No data. Error: {mt5.last_error()}")

mt5.shutdown()
