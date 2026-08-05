import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb

db = duckdb.connect(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline\storage\quant_os.duckdb", read_only=True
)
rows = db.execute(
    "SELECT title, sentiment, tickers FROM llm_news_sentiment ORDER BY analyzed_at DESC LIMIT 15"
).fetchall()
for r in rows:
    print(f"S={r[1][:4]:4} T=[{r[2]}] {r[0][:60]}")
# Count with/without tickers
with_t = db.execute("SELECT COUNT(*) FROM llm_news_sentiment WHERE tickers != '' AND tickers IS NOT NULL").fetchone()[0]
total = db.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0]
print(f"\nWith tickers: {with_t}/{total}")
db.close()
