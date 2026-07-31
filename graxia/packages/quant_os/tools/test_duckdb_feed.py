"""Test: load latest report → write to DuckDB → query back."""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from news_events.news_sentiment import NewsSentimentStore

REPORTS_DIR = Path(__file__).parent.parent / "reports"

# Step 1: Load report
store = NewsSentimentStore(REPORTS_DIR)
loaded = store.load_latest_report()
if not loaded:
    print("[FAIL] No report found")
    sys.exit(1)

summary = store.get_summary()
print(f"[OK] Report loaded — {summary['ticker_count']} tickers, sentiment={summary['overall_sentiment']}")

# Step 2: Write to DuckDB
sys.path.insert(0, str(Path(__file__).parent.parent / "data_pipeline"))
from storage.duckdb_store import DuckDBStore

duck = DuckDBStore()
report = store._current_report
analysis = report.get("analysis", {})
articles = analysis.get("articles", [])
overall = {
    "overall_sentiment": analysis.get("overall_sentiment", "neutral"),
    "market_impact_th": analysis.get("market_impact_th", ""),
    "action_items_th": analysis.get("action_items_th", []),
    "report_time": report.get("generated_at", ""),
}
duck.upsert_llm_news_sentiment(articles, overall, summary.get("query", ""))
print("[OK] Written to DuckDB")

# Step 3: Query back
recent = duck.query_llm_sentiment(hours=6)
print(f"[OK] Query back: {len(recent)} rows from last 6h")

# Step 4: Summary
smry = duck.get_llm_sentiment_summary(hours=24)
print(f"[OK] Summary ({len(smry)} groups):")
if len(smry) > 0:
    for _, row in smry.iterrows():
        print(f"  {row['llm_ticker']:>6} | {row['llm_ticker_sentiment']:>10} | mentions={row['mentions']}")
else:
    print("  (no data — check time filter)")

# Step 5: Snapshot to state/
snapshot = REPORTS_DIR.parent / "state" / "latest_sentiment.json"
snapshot.parent.mkdir(parents=True, exist_ok=True)
snapshot.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
print(f"[OK] Snapshot saved: {snapshot}")

duck.close()
print("\n[DONE] Full pipeline test passed")
