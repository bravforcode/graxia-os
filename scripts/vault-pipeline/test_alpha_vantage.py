"""test_alpha_vantage.py — Test Alpha Vantage with different endpoints"""

import os

key = os.environ.get("ALPHAVANTAGE_API_KEY", "69A2D75S09YBKLGR")
print(f"Key: {key[:8]}...")

from alpha_vantage.timeseries import TimeSeries

ts = TimeSeries(key=key)

# Test 1: Daily data (free)
try:
    data, meta = ts.get_daily("IBM")
    print(f"OK: DAILY IBM = {len(data)} rows, latest={data['4. close'].iloc[0]}")
except Exception as e:
    print(f"FAIL daily: {e}")

# Test 2: Weekly data (free)
try:
    data, meta = ts.get_weekly("IBM")
    print(f"OK: WEEKLY IBM = {len(data)} rows, latest={data['4. close'].iloc[0]}")
except Exception as e:
    print(f"FAIL weekly: {e}")

# Test 3: Forex (free)
try:
    from alpha_vantage.foreignexchange import ForeignExchange

    fx = ForeignExchange(key=key)
    data, meta = fx.get_currency_exchange_rate("EUR", "USD")
    print(f"OK: EUR/USD = {data['5. Exchange Rate']}")
except Exception as e:
    print(f"FAIL forex: {e}")
