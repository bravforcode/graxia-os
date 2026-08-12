"""verify_api_keys.py — Verify all API keys work"""

import os

print("=== VERIFYING API KEYS ===\n")

# Alpha Vantage
print("[1] Alpha Vantage")
try:
    from alpha_vantage.timeseries import TimeSeries

    key = os.environ.get("ALPHAVANTAGE_API_KEY", "69A2D75S09YBKLGR")
    ts = TimeSeries(key=key)
    data, meta = ts.get_intraday("IBM", interval="5min", outputsize="compact")
    print(f"  OK: {len(data)} rows for IBM")
    print(f"  Latest: {data['4. close'].iloc[0]}")
except Exception as e:
    print(f"  FAIL: {e}")

# FRED
print("\n[2] FRED")
try:
    from fredapi import Fred

    key = os.environ.get("FRED_API_KEY", "ca6997817f1fad59485310fc56ae594e")
    fred = Fred(api_key=key)
    gdp = fred.get_series("GDP", observation_start="2024-01-01")
    print(f"  OK: GDP series, {len(gdp)} observations")
    print(f"  Latest: {gdp.iloc[-1]:.1f}B")
except Exception as e:
    print(f"  FAIL: {e}")

# NewsAPI
print("\n[3] NewsAPI")
try:
    from newsapi import NewsApiClient

    key = os.environ.get("NEWS_API_KEY", "98acea70c06f4dd5ac1489054d877768")
    newsapi = NewsApiClient(api_key=key)
    articles = newsapi.get_everything(
        q="gold trading", language="en", sort_by="publishedAt", page_size=3
    )
    print(f"  OK: {articles['totalResults']} total articles")
    for a in articles["articles"][:3]:
        print(f"  - {a['title'][:60]}")
except Exception as e:
    print(f"  FAIL: {e}")

print("\n=== DONE ===")
