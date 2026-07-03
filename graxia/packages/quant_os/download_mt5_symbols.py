import MetaTrader5 as mt5
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ["EURUSD", "GBPUSD"]
TIMEFRAMES = {
    "D1": (mt5.TIMEFRAME_D1, 5000),
    "H1": (mt5.TIMEFRAME_H1, 50000),
    "M15": (mt5.TIMEFRAME_M15, 50000),
}


def main():
    if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    try:
        for symbol in SYMBOLS:
            if not mt5.symbol_select(symbol, True):
                print(f"Failed to select {symbol}: {mt5.last_error()}")
                continue

            for tf_name, (tf_const, bars) in TIMEFRAMES.items():
                rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)
                if rates is None or len(rates) == 0:
                    print(f"{symbol} {tf_name}: no data ({mt5.last_error()})")
                    continue

                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")
                df = df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
                    columns={"tick_volume": "volume"}
                )

                fpath = DATA_DIR / f"{symbol}_{tf_name}.csv"
                df.to_csv(fpath, index=False)

                first = df["time"].iloc[0]
                last = df["time"].iloc[-1]
                print(f"{symbol:6s} {tf_name:4s}: {len(df):>6,} bars  {first} -> {last}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
