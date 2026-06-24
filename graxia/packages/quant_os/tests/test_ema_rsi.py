import sys, os
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from graxia.packages.quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
fmt = "%Y-%m-%d %H:%M:%S"

xau_d1 = os.path.join(data_dir, "XAUUSD_D1.csv")
if not os.path.exists(xau_d1):
    raise ImportError(f"Data file not found: {xau_d1}")

d1, ts1 = load_csv_data(xau_d1, date_column="time", date_format=fmt)
h1, tsh1 = load_csv_data(os.path.join(data_dir, "XAUUSD_H1.csv"), date_column="time", date_format=fmt)
m15, tsm15 = load_csv_data(os.path.join(data_dir, "XAUUSD_M15.csv"), date_column="time", date_format=fmt)

# Test with D1 data (what the backtest uses)
data_d1 = {k: v[-200:] for k, v in d1.items()}
price = data_d1["close"][-1]

# Build nested data with real M15
nested = {
    "D1": data_d1,
    "H1": {k: v[-500:] for k, v in h1.items()},
    "M15": {k: v[-2000:] for k, v in m15.items()},
}

# Test ema_cross
ema = EMACrossStrategy()
close_m15 = ema._get_close(nested, "M15")
close_h4 = ema._get_close(nested, "H4")
print(f"EMA cross: M15 bars={len(close_m15)}, H4 bars={len(close_h4)}")
print(f"  M15 last 5: {close_m15[-5:]}")

sig = ema.analyze(nested, price, "XAUUSD")
print(f"  Signal: {sig}")

# Test rsi_divergence
rsi_strat = RSIDivergenceStrategy()
close_m15_rsi = rsi_strat._get_close(nested, "M15")
print(f"\nRSI: M15 bars={len(close_m15_rsi)}")
rsi_val = rsi_strat._calc_rsi(close_m15_rsi, 14)
print(f"  RSI(14): {rsi_val}")

sig2 = rsi_strat.analyze(nested, price, "XAUUSD")
print(f"  Signal: {sig2}")
