"""query_data.py — Query stored data from DuckDB"""
import sys
sys.path.insert(0, r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline")
from storage.duckdb_store import DuckDBStore

db = DuckDBStore()

print("=== MARKET DATA ===")
df = db.query("SELECT symbol, ANY_VALUE(close) as close, source FROM market_data WHERE close IS NOT NULL GROUP BY symbol, source ORDER BY source, symbol")
for _, r in df.iterrows():
    val = r['close']
    print(f"  {r['symbol']}: {val:.2f} ({r['source']})" if val == val else f"  {r['symbol']}: nan ({r['source']})")

print()
print("=== MACRO DATA ===")
df = db.query("SELECT series_id, value FROM macro_data WHERE timestamp > '2025-01-01' AND value IS NOT NULL ORDER BY series_id, timestamp DESC LIMIT 10")
for _, r in df.iterrows():
    print(f"  {r['series_id']}: {r['value']:.2f}")

print()
print("=== NEWS SENTIMENT (top 5 bullish) ===")
df = db.query("SELECT title, vader_compound FROM news_sentiment WHERE vader_compound IS NOT NULL ORDER BY vader_compound DESC LIMIT 5")
for _, r in df.iterrows():
    print(f"  [{r['vader_compound']:+.2f}] {r['title'][:60]}")

print()
print("=== DB STATS ===")
stats = db.query("SELECT (SELECT COUNT(*) FROM market_data) as market, (SELECT COUNT(*) FROM macro_data) as macro, (SELECT COUNT(*) FROM news_sentiment) as news")
print(f"  Market: {stats['market'].iloc[0]} rows")
print(f"  Macro: {stats['macro'].iloc[0]} rows")
print(f"  News: {stats['news'].iloc[0]} rows")

db.close()
