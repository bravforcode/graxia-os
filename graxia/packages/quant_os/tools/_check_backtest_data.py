"""Check backtest prerequisites."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "data_pipeline"))
from storage.duckdb_store import DuckDBStore

duck = DuckDBStore()
r1 = duck.conn.execute("SELECT COUNT(*) FROM llm_news_sentiment WHERE tickers IS NOT NULL AND tickers != ''").fetchone()
r2 = duck.conn.execute(
    "SELECT COUNT(*) FROM llm_news_sentiment WHERE sentiment IN ('positive','negative','neutral')"
).fetchone()
r3 = duck.conn.execute(
    "SELECT COUNT(*) FROM llm_news_sentiment WHERE tickers IS NOT NULL AND tickers != '' AND sentiment IN ('positive','negative','neutral')"
).fetchone()
print(f"With tickers: {r1[0]}")
print(f"With sentiment: {r2[0]}")
print(f"With both (usable for backtest): {r3[0]}")

r4 = duck.conn.execute(
    "SELECT tickers, sentiment, COUNT(*) as cnt FROM llm_news_sentiment "
    "WHERE tickers IS NOT NULL AND tickers != '' "
    "GROUP BY tickers, sentiment ORDER BY cnt DESC LIMIT 15"
).fetchall()
print("\nTop ticker+sentiment combos:")
for t, s, c in r4:
    print(f"  {t}: {s} ({c})")

r5 = duck.conn.execute(
    "SELECT source, COUNT(*) as cnt FROM llm_news_sentiment " "GROUP BY source ORDER BY cnt DESC"
).fetchall()
print("\nBy source:")
for s, c in r5:
    print(f"  {s}: {c}")
duck.close()
