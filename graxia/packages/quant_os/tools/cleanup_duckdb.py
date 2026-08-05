"""Clean up old batch-mode rows from DuckDB."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb

DB = r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline\storage\quant_os.duckdb"
db = duckdb.connect(DB)

count = db.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0]
print(f"Total rows: {count}")

bad = db.execute(
    "SELECT title, tickers FROM llm_news_sentiment WHERE tickers LIKE '%[%' OR tickers LIKE '%]%'"
).fetchall()
print(f"Rows with bracket tickers: {len(bad)}")
for b in bad:
    print(f"  [{b[1]}] {b[0][:60]}")

# Delete old batch-mode rows
db.execute("DELETE FROM llm_news_sentiment WHERE tickers LIKE '%[%' OR tickers LIKE '%]%'")
remaining = db.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0]
print(f"After cleanup: {remaining} rows")

# Show all remaining tickers
rows = db.execute(
    "SELECT title, sentiment, tickers FROM llm_news_sentiment ORDER BY analyzed_at DESC LIMIT 10"
).fetchall()
for r in rows:
    print(f"  S={r[1][:4]:4} T={r[2][:10]:10} | {r[0][:55]}")

db.close()
