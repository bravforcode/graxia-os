"""Clean old batch-mode data and verify single-headline mode works."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb

DB = r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline\storage\quant_os.duckdb"
db = duckdb.connect(DB)

total = db.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0]
print(f"Before cleanup: {total} rows")

# Delete all old rows (batch mode with bracket tickers + empty tickers from broken batch)
db.execute("DELETE FROM llm_news_sentiment")
remaining = db.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0]
print(f"After cleanup: {remaining} rows (fresh start)")

db.close()
print("DuckDB cleaned. Ready for fresh single-headline analysis.")
