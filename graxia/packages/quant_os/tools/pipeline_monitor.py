"""
Master Monitor — Dashboard for sentiment pipeline health
Shows data status, runs backtest if ready, checks calibration.

Usage:
    python tools/pipeline_monitor.py              # Full status
    python tools/pipeline_monitor.py --backtest   # Force backtest
    python tools/pipeline_monitor.py --calibrate  # Force calibration
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def check_daemon_status() -> dict:
    """Check daemon state."""
    state_file = BASE_DIR / "state" / "daemon_state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {"cycles": 0, "articles_total": 0, "errors": 0, "last_cycle": None}


def check_duckdb_status() -> dict:
    """Check DuckDB data counts."""
    sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
    from storage.duckdb_store import DuckDBStore

    duck = DuckDBStore()
    result = {
        "sentiment_pairs": duck.count_llm_sentiment_pairs(),
        "total_rows": duck.conn.execute("SELECT COUNT(*) FROM llm_news_sentiment").fetchone()[0],
    }
    duck.close()
    return result


def check_sentiment_snapshot() -> dict:
    """Check latest sentiment snapshot."""
    snapshot_file = BASE_DIR / "state" / "latest_sentiment.json"
    if snapshot_file.exists():
        return json.loads(snapshot_file.read_text(encoding="utf-8"))
    return {}


def run_backtest(force: bool = False) -> str:
    """Run sentiment backtest."""
    cmd = [sys.executable, str(BASE_DIR / "tools" / "sentiment_backtest.py")]
    if force:
        cmd.append("--force")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.stdout + result.stderr


def run_calibration() -> str:
    """Run confidence calibration."""
    cmd = [sys.executable, str(BASE_DIR / "tools" / "confidence_calibration.py")]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.stdout + result.stderr


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true", help="Force backtest")
    parser.add_argument("--calibrate", action="store_true", help="Force calibration")
    args = parser.parse_args()

    print("=" * 60)
    print("SENTIMENT PIPELINE MONITOR")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Daemon status
    daemon = check_daemon_status()
    print("\n--- DAEMON ---")
    print(f"Cycles: {daemon.get('cycles', 0)}")
    print(f"Total articles: {daemon.get('articles_total', 0)}")
    print(f"Errors: {daemon.get('errors', 0)}")
    print(f"Last cycle: {daemon.get('last_cycle', 'never')}")

    # DuckDB status
    db = check_duckdb_status()
    print("\n--- DATABASE ---")
    print(f"Total rows: {db['total_rows']}")
    print(f"Sentiment-price pairs: {db['sentiment_pairs']}")

    # Sentiment snapshot
    snap = check_sentiment_snapshot()
    print("\n--- LATEST SNAPSHOT ---")
    print(f"Overall: {snap.get('overall_sentiment', 'unknown')}")
    print(f"Articles: {snap.get('articles_analyzed', 0)}")
    print(f"Positive: {snap.get('positive_count', 0)}")
    print(f"Negative: {snap.get('negative_count', 0)}")
    print(f"Neutral: {snap.get('neutral_count', 0)}")
    print(f"Report time: {snap.get('report_time', 'never')}")

    # Auto-backtest if enough data
    if db["sentiment_pairs"] >= 100 or args.backtest:
        print("\n--- BACKTEST ---")
        output = run_backtest(force=args.backtest)
        print(output)

    # Auto-calibration if enough data
    if db["total_rows"] >= 50 or args.calibrate:
        print("\n--- CALIBRATION ---")
        output = run_calibration()
        print(output)

    # Next steps
    print("\n--- NEXT STEPS ---")
    if db["sentiment_pairs"] < 100:
        needed = 100 - db["sentiment_pairs"]
        print(f"Need {needed} more sentiment-price pairs for backtest")
    else:
        print("Ready for backtest! Run: python tools/sentiment_backtest.py")

    if db["total_rows"] < 50:
        needed = 50 - db["total_rows"]
        print(f"Need {needed} more headlines for calibration")
    else:
        print("Ready for calibration! Run: python tools/confidence_calibration.py")


if __name__ == "__main__":
    main()
