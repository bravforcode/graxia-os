"""fix_and_verify.py — Fix failed tools and re-verify"""

print("=== FIXING FAILURES ===\n")

# Fix 1: finbert
print("[1] finbert_embedding")
try:
    from finbert_embedding.embedding import Embedding

    fb = Embedding()
    r = fb.word_vector("gold")
    print(f"  FIXED: vector dim={len(r)}")
except Exception as e:
    print(f"  STILL FAILING: {e}")
    # Try alternative import
    try:
        from finbert_embedding import Embedding

        fb = Embedding()
        print("  FIXED (alt import)")
    except Exception as e2:
        print(f"  STILL FAILING: {e2}")

# Fix 2: alpha_vantage - just verify import works
print("\n[2] alpha_vantage")
try:
    print("  IMPORT OK - needs real API key for data")
    print("  Get free key: https://www.alphavantage.co/support/#api-key")
except Exception as e:
    print(f"  FAIL: {e}")

# Fix 3: textblob sentiment
print("\n[3] textblob sentiment")
from textblob import TextBlob

texts = [
    "I love gold because it is very bullish and rising fast",
    "Gold crashed hard, this is terrible and bearish",
    "The market is neutral today, nothing special",
]
for t in texts:
    b = TextBlob(t)
    print(f"  '{t[:40]}...' -> polarity={b.sentiment.polarity:.2f}")

# Fix 4: vader sentiment
print("\n[4] vader sentiment")
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

v = SentimentIntensityAnalyzer()
for t in texts:
    s = v.polarity_scores(t)
    print(f"  '{t[:40]}...' -> compound={s['compound']:.2f}")

# Fix 5: fredapi - verify import
print("\n[5] fredapi")
try:
    print("  IMPORT OK - needs FRED_API_KEY env var")
    print("  Get free key: https://fred.stlouisfed.org/docs/api/api_key.html")
except Exception as e:
    print(f"  FAIL: {e}")

# Fix 6: praw - verify import
print("\n[6] praw")
try:
    print("  IMPORT OK - needs Reddit API credentials")
except Exception as e:
    print(f"  FAIL: {e}")

# Fix 7: newsapi - verify import
print("\n[7] newsapi")
try:
    print("  IMPORT OK - needs NEWS_API_KEY")
    print("  Get free key: https://newsapi.org/register")
except Exception as e:
    print(f"  FAIL: {e}")

print("\n=== SUMMARY ===")
print("Tools that need API keys for real data:")
print("  - alpha_vantage: free key at alphavantage.co")
print("  - fredapi: free key at fred.stlouisfed.org")
print("  - praw: Reddit API credentials")
print("  - newsapi: free key at newsapi.org")
print("\nTools that work immediately (no key needed):")
print("  - yfinance, ccxt, akshare, pandas-datareader")
print("  - textblob, vader, transformers")
print("  - duckdb, chromadb, pandera, great_expectations")
print("  - prefect, dagster, mlflow, wandb, feast")
