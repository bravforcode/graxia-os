"""
Graxia Agent Loop — Automated News Research + Analysis Scheduler
=================================================================
Runs the research agent on a schedule (hourly before market open)
and feeds results into quant_os strategy pipeline.

Features:
- Scheduled execution (configurable cron-like schedule)
- Automatic report feeding into NewsSentimentStore
- Logging and error handling
- Graceful shutdown

Usage:
    python agent_loop.py                    # Run once
    python agent_loop.py --schedule         # Run on schedule (hourly 6-9am ET)
    python agent_loop.py --schedule --interval 30  # Every 30 minutes
    python agent_loop.py --query "Fed rate" --model qwen3.5:4b
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from news_events.news_sentiment import NewsSentimentStore

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
RESEARCH_SCRIPT = SCRIPT_DIR / "research_agent.py"
REPORTS_DIR = SCRIPT_DIR.parent / "reports"
STATE_FILE = SCRIPT_DIR.parent / "state" / "agent_loop_state.json"

# Default schedule: hourly from 6am to 9am ET (before US market open at 9:30am ET)
DEFAULT_SCHEDULE = {
    "enabled": True,
    "hours": list(range(6, 10)),  # 6am, 7am, 8am, 9am ET
    "interval_minutes": 60,
    "model": "qwen3.5:9b",
    "query": "stock market financial news",
    "max_articles": 5,
}

# Graceful shutdown
_shutdown = False


def _signal_handler(sig, frame):
    global _shutdown
    print("\n[AGENT LOOP] Shutdown signal received, finishing current run...")
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def load_state() -> dict:
    """Load agent loop state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"last_run": None, "run_count": 0, "errors": []}


def save_state(state: dict) -> None:
    """Save agent loop state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def run_research(
    query: str = "stock market financial news",
    model: str = "qwen3.5:4b",
    max_articles: int = 5,
) -> bool:
    """Run the research agent script and return success/failure."""
    cmd = [
        sys.executable,
        str(RESEARCH_SCRIPT),
        "--query",
        query,
        "--model",
        model,
        "--max",
        str(max_articles),
    ]

    print(f"\n[AGENT LOOP] Running research: {query}")
    print(f"  Model: {model}")
    print(f"  Max articles: {max_articles}")
    print(f"  Time: {datetime.now().isoformat()}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            encoding="utf-8",
        )

        if result.returncode == 0:
            print("  [OK] Research completed successfully")
            print(f"  Output preview: {result.stdout[-200:]}")
            return True
        else:
            print(f"  [FAIL] Research failed (exit code {result.returncode})")
            print(f"  stderr: {result.stderr[-500:]}")
            return False

    except subprocess.TimeoutExpired:
        print("  [TIMEOUT] Research timed out after 600s")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def feed_into_quant_os() -> bool:
    """Load latest report and feed into DuckDB + NewsSentimentStore."""
    print("\n[AGENT LOOP] Feeding report into quant_os (DuckDB + JSON)...")

    store = NewsSentimentStore(REPORTS_DIR)
    if not store.load_latest_report():
        print("  [WARN] No report found to feed")
        return False

    summary = store.get_summary()
    print(f"  Overall sentiment: {summary['overall_sentiment']}")
    print(f"  Tickers: {summary['ticker_count']}")
    print(f"  Positive: {summary['positive_tickers']}")
    print(f"  Negative: {summary['negative_tickers']}")
    print(f"  Report fresh: {summary['report_fresh']}")

    # Save sentiment snapshot for strategy consumption
    sentiment_file = REPORTS_DIR.parent / "state" / "latest_sentiment.json"
    sentiment_file.parent.mkdir(parents=True, exist_ok=True)
    sentiment_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {sentiment_file}")

    # Write to DuckDB
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "data_pipeline"))
        from storage.duckdb_store import DuckDBStore

        duck = DuckDBStore()
        report = store._current_report
        if report:
            analysis = report.get("analysis", {})
            articles = analysis.get("articles", [])
            overall = {
                "overall_sentiment": analysis.get("overall_sentiment", "neutral"),
                "market_impact_th": analysis.get("market_impact_th", ""),
                "action_items_th": analysis.get("action_items_th", []),
                "report_time": report.get("generated_at", ""),
            }
            duck.upsert_llm_news_sentiment(articles, overall, summary.get("query", ""))
            print("  DuckDB: LLM news sentiment written")

        duck.close()
    except Exception as e:
        print(f"  [WARN] DuckDB write failed: {e}")

    return True


def should_run_now(schedule: dict) -> bool:
    """Check if we should run based on schedule."""
    now = datetime.now()

    # Check hour (ET timezone approximation — for real use, use pytz)
    # For now, just use local time hour
    current_hour = now.hour

    # Check if current hour is in schedule window
    if current_hour not in schedule.get("hours", []):
        return False

    # Check interval since last run
    state = load_state()
    if state.get("last_run"):
        last_run = datetime.fromisoformat(state["last_run"])
        elapsed = (now - last_run).total_seconds() / 60
        if elapsed < schedule.get("interval_minutes", 60):
            return False

    return True


def run_once(schedule: dict) -> None:
    """Execute one research cycle."""
    state = load_state()

    # Run research
    success = run_research(
        query=schedule.get("query", "stock market financial news"),
        model=schedule.get("model", "qwen3.5:4b"),
        max_articles=schedule.get("max_articles", 5),
    )

    if success:
        # Feed into quant_os
        feed_into_quant_os()

        # Update state
        state["last_run"] = datetime.now().isoformat()
        state["run_count"] = state.get("run_count", 0) + 1
    else:
        state["errors"] = state.get("errors", [])[-10:]  # Keep last 10 errors
        state["errors"].append(
            {
                "time": datetime.now().isoformat(),
                "query": schedule.get("query", ""),
            }
        )

    save_state(state)


def run_scheduled(schedule: dict) -> None:
    """Run the agent loop on schedule."""
    print(f"\n{'='*60}")
    print("GRAXIA AGENT LOOP — SCHEDULED MODE")
    print(f"Schedule: every {schedule['interval_minutes']}min during hours {schedule['hours']}")
    print(f"Model: {schedule['model']}")
    print(f"Query: {schedule['query']}")
    print("Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    while not _shutdown:
        if should_run_now(schedule):
            run_once(schedule)
        else:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Waiting... (next run at scheduled hour)")

        # Sleep 60 seconds between checks
        for _ in range(60):
            if _shutdown:
                break
            time.sleep(1)

    print("\n[AGENT LOOP] Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Graxia Agent Loop")
    parser.add_argument("--schedule", action="store_true", help="Run on schedule")
    parser.add_argument("--interval", type=int, default=60, help="Minutes between runs (when scheduled)")
    parser.add_argument("--query", default="stock market financial news", help="Search focus")
    parser.add_argument("--model", default="qwen3.5:9b", help="Ollama model")
    parser.add_argument("--max", type=int, default=5, help="Max articles per feed")
    parser.add_argument(
        "--hours", type=int, nargs="+", default=[6, 7, 8, 9], help="Hours to run (local time, e.g. 6 7 8 9)"
    )
    args = parser.parse_args()

    schedule = {
        "enabled": True,
        "hours": args.hours,
        "interval_minutes": args.interval,
        "model": args.model,
        "query": args.query,
        "max_articles": args.max,
    }

    if args.schedule:
        run_scheduled(schedule)
    else:
        run_once(schedule)


if __name__ == "__main__":
    main()
