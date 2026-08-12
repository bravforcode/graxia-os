import yfinance as yf
import pandas as pd

for sym in ["EURUSD=X", "GC=F", "^DJI"]:
    t = yf.Ticker(sym)
    df = t.history(period="5d")
    if len(df) > 0:
        last = df["Close"].iloc[-1]
        print(f"  {sym}: last={last}, isnan={pd.isna(last)}, type={type(last)}")
        print(f"    all Close: {df['Close'].tolist()}")
    else:
        print(f"  {sym}: NO DATA")
