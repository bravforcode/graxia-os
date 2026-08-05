"""Check tickers and market_data overlap"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb

DB_PATH = r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline\storage\quant_os.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

print("=== market_data symbols ===")
r = conn.execute(
    "SELECT DISTINCT symbol, COUNT(*) as cnt FROM market_data GROUP BY symbol ORDER BY cnt DESC"
).fetchall()
for s, c in r:
    print(f"  {s}: {c} rows")

print("\n=== llm_news_sentiment tickers (sample 10) ===")
r2 = conn.execute(
    "SELECT tickers FROM llm_news_sentiment WHERE tickers IS NOT NULL AND tickers != '' LIMIT 10"
).fetchall()
for t in r2:
    print(f"  {t[0]}")

print("\n=== unique tickers in sentiment ===")
r3 = conn.execute("""
    SELECT DISTINCT TRIM(t.value) as ticker
    FROM llm_news_sentiment,
    LATERAL UNNEST(string_split(tickers, ',')) AS t(value)
    WHERE tickers IS NOT NULL AND tickers != ''
    ORDER BY ticker
""").fetchall()
for t in r3:
    print(f"  {t[0]}")
print(f"\nTotal unique tickers: {len(r3)}")

print("\n=== overlap check ===")
sentiment_tickers = set(t[0].strip() for t in r3)
market_symbols = set(s[0] for s in r)
overlap = sentiment_tickers & market_symbols
print(f"Sentiment tickers: {len(sentiment_tickers)}")
print(f"Market symbols: {len(market_symbols)}")
print(f"Overlap: {len(overlap)} — {overlap if overlap else 'NONE'}")

conn.close()
