"""Test MT5 higher timeframes - find max available history."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from time import mktime
import pandas as pd

mt5.initialize()

for tf_name, tf in [("M5", mt5.TIMEFRAME_M5), ("M15", mt5.TIMEFRAME_M15),
                      ("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1),
                      ("H4", mt5.TIMEFRAME_H4), ("D1", mt5.TIMEFRAME_D1),
                      ("W1", mt5.TIMEFRAME_W1), ("MN1", mt5.TIMEFRAME_MN1)]:
    best = None
    best_label = None
    for days, label in [(3650, "10yr"), (2555, "7yr"), (1825, "5yr"), (1095, "3yr"), (730, "2yr"), (365, "1yr")]:
        end_ts = int(mktime(datetime.now().timetuple()))
        start_ts = int(mktime((datetime.now() - timedelta(days=days)).timetuple()))
        rates = mt5.copy_rates_range("XAUUSD", tf, start_ts, end_ts)
        if rates is not None and len(rates) > 0:
            best = rates
            best_label = label
            break
    if best is not None:
        df = pd.DataFrame(best)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        print(f"{tf_name:4s} max={best_label:5s} {len(best):7d} bars  {df['time'].iloc[0].date()} -> {df['time'].iloc[-1].date()}")
    else:
        print(f"{tf_name:4s} NO DATA available")

mt5.shutdown()
