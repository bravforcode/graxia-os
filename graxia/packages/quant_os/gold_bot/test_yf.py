import yfinance as yf

# Test XAUUSD
gold = yf.Ticker("GC=F")
hist = gold.history(period="1d", interval="15m")
print(f"XAUUSD M15 candles: {len(hist)}")
if len(hist) > 0:
    last = hist.iloc[-1]
    print(f"Last candle: O={last['Open']:.2f} H={last['High']:.2f} L={last['Low']:.2f} C={last['Close']:.2f}")

# Test EURUSD
eur = yf.Ticker("EURUSD=X")
hist2 = eur.history(period="1d", interval="15m")
print(f"EURUSD M15 candles: {len(hist2)}")
if len(hist2) > 0:
    last2 = hist2.iloc[-1]
    print(f"Last candle: O={last2['Open']:.5f} H={last2['High']:.5f} L={last2['Low']:.5f} C={last2['Close']:.5f}")

# Test BTCUSD
btc = yf.Ticker("BTC-USD")
hist3 = btc.history(period="1d", interval="15m")
print(f"BTCUSD M15 candles: {len(hist3)}")
if len(hist3) > 0:
    last3 = hist3.iloc[-1]
    print(f"Last candle: O={last3['Open']:.2f} H={last3['High']:.2f} L={last3['Low']:.2f} C={last3['Close']:.2f}")
