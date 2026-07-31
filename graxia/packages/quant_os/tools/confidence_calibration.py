"""
Confidence Calibration Check — Does model's confidence predict accuracy?

Approach:
1. Label 50 headlines for ambiguity (clear vs ambiguous)
2. Check if confidence score correlates with correct extraction
3. Compute calibration metrics

Usage:
    python tools/confidence_calibration.py           # Run calibration
    python tools/confidence_calibration.py --status   # Show current data
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
from storage.duckdb_store import DuckDBStore

REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def label_headlines(duck: DuckDBStore, n: int = 50) -> pd.DataFrame:
    """Get recent headlines for manual labeling."""
    df = duck.conn.execute(f"""
        SELECT url, title, source, tickers, sentiment, impact, summary
        FROM llm_news_sentiment
        WHERE analyzed_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
          AND title IS NOT NULL AND title != ''
        ORDER BY analyzed_at DESC
        LIMIT {n}
    """).fetchdf()
    return df


def compute_calibration(headlines: pd.DataFrame) -> dict:
    """Compute calibration metrics from labeled data.

    For each headline, we check:
    1. Was the ticker extraction correct?
    2. Was the sentiment correct?
    3. Does the model's confidence (impact level) predict accuracy?
    """
    if len(headlines) == 0:
        return {"error": "No headlines to analyze"}

    results = []
    for _, row in headlines.iterrows():
        title = row.get("title", "")
        tickers = row.get("tickers", "")
        sentiment = row.get("sentiment", "neutral")
        impact = row.get("impact", "low")

        # Heuristic: if title mentions a specific company/ticker, extraction should succeed
        has_ticker_hint = any(
            word in title.upper()
            for word in [
                "AAPL",
                "MSFT",
                "GOOGL",
                "AMZN",
                "TSLA",
                "NVDA",
                "META",
                "JPM",
                "GS",
                "BAC",
                "WFC",
                "C",
                "MS",
                "BLK",
                "SHELL",
                "BP",
                "TOTAL",
                "EXXON",
                "CHEVRON",
                "S&P",
                "NASDAQ",
                "DOW",
                "FTSE",
                "NIKKEI",
                "BITCOIN",
                "ETHEREUM",
                "CRYPTO",
                "FED",
                "ECB",
                "BOJ",
                "BOE",
            ]
        )

        # Check if extraction was successful
        extraction_ok = bool(tickers and tickers.strip())

        # Map impact to confidence score
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        confidence = confidence_map.get(impact, 0.5)

        results.append(
            {
                "title": title[:80],
                "has_ticker_hint": has_ticker_hint,
                "extraction_ok": extraction_ok,
                "confidence": confidence,
                "impact": impact,
                "sentiment": sentiment,
            }
        )

    df = pd.DataFrame(results)

    # Calibration metrics
    total = len(df)
    extraction_rate = df["extraction_ok"].mean()

    # Confidence vs accuracy correlation
    if "confidence" in df.columns and "extraction_ok" in df.columns:
        correlation = df["confidence"].corr(df["extraction_ok"].astype(float))
    else:
        correlation = 0

    # Impact level breakdown
    impact_stats = (
        df.groupby("impact")
        .agg(count=("extraction_ok", "count"), extraction_rate=("extraction_ok", "mean"))
        .to_dict("index")
    )

    return {
        "total_headlines": total,
        "extraction_rate": round(extraction_rate, 4),
        "confidence_correlation": round(correlation, 4),
        "impact_stats": impact_stats,
    }


def generate_calibration_report(stats: dict) -> str:
    """Generate calibration report."""
    report = []
    report.append("=" * 60)
    report.append("CONFIDENCE CALIBRATION REPORT")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("=" * 60)
    report.append("")

    if "error" in stats:
        report.append(f"ERROR: {stats['error']}")
        return "\n".join(report)

    report.append(f"Headlines analyzed: {stats['total_headlines']}")
    report.append(f"Overall extraction rate: {stats['extraction_rate']:.1%}")
    report.append(f"Confidence-accuracy correlation: {stats['confidence_correlation']:.3f}")
    report.append("")

    report.append("--- IMPACT LEVEL BREAKDOWN ---")
    for impact, data in stats.get("impact_stats", {}).items():
        report.append(f"  {impact:8} | {data['count']:3} headlines | {data['extraction_rate']:.0%} extraction")

    report.append("")
    report.append("--- INTERPRETATION ---")
    corr = stats["confidence_correlation"]
    if corr > 0.3:
        report.append("CONFIDENCE IS WELL-CALIBRATED: Higher impact = more reliable extraction")
    elif corr > 0.1:
        report.append("CONFIDENCE IS WEAKLY CALIBRATED: Some correlation with accuracy")
    else:
        report.append("CONFIDENCE IS POORLY CALIBRATED: Impact level doesn't predict accuracy")

    return "\n".join(report)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="Show current data")
    parser.add_argument("--n", type=int, default=50, help="Number of headlines to analyze")
    args = parser.parse_args()

    duck = DuckDBStore()

    count = duck.count_llm_sentiment_pairs()
    print(f"Current sentiment pairs: {count}")

    if args.status:
        duck.close()
        return

    print(f"\nFetching {args.n} headlines for calibration...")
    headlines = label_headlines(duck, n=args.n)
    print(f"Got {len(headlines)} headlines")

    if len(headlines) < 10:
        print("Need at least 10 headlines for calibration.")
        duck.close()
        return

    stats = compute_calibration(headlines)
    report = generate_calibration_report(stats)
    print(report)

    # Save report
    report_path = REPORTS_DIR / f"confidence_calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    duck.close()


if __name__ == "__main__":
    main()
