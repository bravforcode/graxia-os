"""
Sentiment-Price Backtest — Auto-runs when 100+ sentiment-price pairs exist
Pre-registered as Trial #1031 (Bonferroni-corrected α = 0.000049)

Usage:
    python tools/sentiment_backtest.py              # Run if enough data
    python tools/sentiment_backtest.py --force       # Run even with <100 pairs
    python tools/sentiment_backtest.py --status      # Show current data count
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
from storage.duckdb_store import DuckDBStore

# Pre-registered parameters (Trial #1031)
MIN_PAIRS = 100
ALPHA_BONFERRONI = 0.000049  # 0.05 / 1029 prior trials (pre-registration doc: 1030 = 1029 prior + current)
MIN_EFFECT_SIZE = 0.2  # Cohen's d
MIN_HIT_RATE = 0.55  # Direction consistency
MAX_PAIR_GAP_DAYS = 5  # reject baseline/outcome pairs further apart than a long weekend

REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_sentiment_price_pairs(duck: DuckDBStore, days: int = 30) -> pd.DataFrame:
    """Match sentiment to next-day ticker returns.

    For each sentiment record with a ticker:
    1. Look up the ticker's price the next trading day
    2. Calculate the return
    3. Check if sentiment direction matches price direction
    """
    # Get all sentiment records with tickers
    sentiment_df = duck.get_llm_sentiment_data(days=days)

    if len(sentiment_df) == 0:
        return pd.DataFrame()

    pairs = []
    for _, row in sentiment_df.iterrows():
        tickers_str = row.get("tickers", "")
        if not tickers_str:
            continue

        # Split multiple tickers (e.g., "SPX,NASDAQ")
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]

        for ticker in tickers:
            # Get price data for this ticker
            price_data = duck.conn.execute(
                """
                SELECT close, timestamp
                FROM market_data
                WHERE symbol = ? AND close IS NOT NULL
                ORDER BY timestamp ASC
            """,
                [ticker],
            ).fetchdf()

            if len(price_data) < 2:
                continue

            # Find the sentiment timestamp
            sentiment_time = pd.to_datetime(row["analyzed_at"])
            sentiment_date = sentiment_time.date()

            # T+1 matching (pre-registered): baseline = close on or before the
            # sentiment date; outcome = first close strictly after it (next
            # trading day). Non-trading days have no rows, so weekend/holiday
            # sentiment naturally lands on the next bar (e.g., Fri -> Mon).
            price_data["date"] = pd.to_datetime(price_data["timestamp"]).dt.date

            # Baseline: last price on or before sentiment date (close of T)
            past_prices = price_data[price_data["date"] <= sentiment_date]

            # Outcome: first price strictly after sentiment date (close of T+1)
            future_prices = price_data[price_data["date"] > sentiment_date]
            if len(future_prices) == 0:
                continue

            if len(past_prices) > 0:
                baseline_row = past_prices.iloc[-1]
                outcome_row = future_prices.iloc[0]
            else:
                # No past prices — use first two prices as baseline/outcome
                if len(future_prices) < 2:
                    continue
                baseline_row = future_prices.iloc[0]
                outcome_row = future_prices.iloc[1]
                # Anchor to sentiment date: if price history only starts weeks
                # later (obscure/typo'd ticker), this pair is disconnected from
                # the sentiment event even if baseline/outcome are adjacent.
                if (baseline_row["date"] - sentiment_date).days > MAX_PAIR_GAP_DAYS:
                    continue

            # Reject pairs where baseline/outcome are far apart (stale price
            # history, data gaps) — both branches above must stay within this
            # bound, not just the has-past-price case.
            if (outcome_row["date"] - baseline_row["date"]).days > MAX_PAIR_GAP_DAYS:
                continue

            price_at_sentiment = baseline_row["close"]
            price_next_day = outcome_row["close"]

            # Calculate return
            ret = (price_next_day - price_at_sentiment) / price_at_sentiment

            # Determine sentiment direction
            sentiment = row.get("sentiment", "neutral")
            if sentiment == "positive":
                sentiment_dir = 1
            elif sentiment == "negative":
                sentiment_dir = -1
            else:
                sentiment_dir = 0

            # Determine price direction
            price_dir = 1 if ret > 0 else (-1 if ret < 0 else 0)

            # Check if directions match
            match = (sentiment_dir == price_dir) if sentiment_dir != 0 else False

            pairs.append(
                {
                    "ticker": ticker,
                    "sentiment": sentiment,
                    "sentiment_dir": sentiment_dir,
                    "price_return": ret,
                    "price_dir": price_dir,
                    "match": match,
                    "analyzed_at": row["analyzed_at"],
                    "title": row.get("title", "")[:100],
                }
            )

    return pd.DataFrame(pairs)


def compute_hit_rate(pairs_df: pd.DataFrame) -> dict:
    """Compute hit rate and statistical tests."""
    if len(pairs_df) == 0:
        return {"error": "No pairs"}

    # Filter to non-neutral sentiment only
    non_neutral = pairs_df[pairs_df["sentiment_dir"] != 0]

    if len(non_neutral) < 10:
        return {"error": f"Too few non-neutral pairs: {len(non_neutral)}"}

    # Hit rate (direction consistency)
    hits = non_neutral["match"].sum()
    total = len(non_neutral)
    hit_rate = hits / total

    # Cohen's d (effect size)
    pos_returns = non_neutral[non_neutral["sentiment_dir"] == 1]["price_return"]
    neg_returns = non_neutral[non_neutral["sentiment_dir"] == -1]["price_return"]

    if len(pos_returns) > 1 and len(neg_returns) > 1:
        pooled_std = np.sqrt(
            ((len(pos_returns) - 1) * pos_returns.std() ** 2 + (len(neg_returns) - 1) * neg_returns.std() ** 2)
            / (len(pos_returns) + len(neg_returns) - 2)
        )
        if pooled_std > 0:
            cohens_d = (pos_returns.mean() - neg_returns.mean()) / pooled_std
        else:
            cohens_d = 0
    else:
        cohens_d = 0

    # Simple z-test for hit rate vs 50%
    se = np.sqrt(0.5 * 0.5 / total)
    z_score = (hit_rate - 0.5) / se if se > 0 else 0

    # Exact two-tailed normal p-value (stdlib, no scipy dependency)
    p_value = math.erfc(abs(z_score) / math.sqrt(2))

    return {
        "total_pairs": len(pairs_df),
        "non_neutral_pairs": len(non_neutral),
        "hits": int(hits),
        "hit_rate": round(hit_rate, 4),
        "cohens_d": round(cohens_d, 4),
        "z_score": round(z_score, 4),
        "p_value": round(p_value, 8),
        "significant_bonferroni": bool(p_value < ALPHA_BONFERRONI),
        "significant_uncorrected": bool(p_value < 0.05),
        "meets_effect_size": bool(abs(cohens_d) >= MIN_EFFECT_SIZE),
        "meets_hit_rate": bool(hit_rate >= MIN_HIT_RATE),
    }


def generate_report(pairs_df: pd.DataFrame, stats: dict) -> str:
    """Generate human-readable backtest report."""
    report = []
    report.append("=" * 60)
    report.append("SENTIMENT-PRICE BACKTEST RESULTS")
    report.append("Trial #1031 (Pre-registered)")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("=" * 60)
    report.append("")

    if "error" in stats:
        report.append(f"ERROR: {stats['error']}")
        return "\n".join(report)

    report.append(f"Total sentiment-price pairs: {stats['total_pairs']}")
    report.append(f"Non-neutral pairs analyzed: {stats['non_neutral_pairs']}")
    report.append(f"Hits (direction match): {stats['hits']}")
    report.append("")
    report.append("--- STATISTICAL RESULTS ---")
    report.append(f"Hit rate: {stats['hit_rate']:.1%} (threshold: {MIN_HIT_RATE:.0%})")
    report.append(f"Cohen's d: {stats['cohens_d']:.3f} (threshold: {MIN_EFFECT_SIZE})")
    report.append(f"Z-score: {stats['z_score']:.3f}")
    report.append(f"P-value: {stats['p_value']:.2e}")
    report.append("")
    report.append("--- DECISION ---")
    report.append(f"Significant at α=0.05: {'YES' if stats['significant_uncorrected'] else 'NO'}")
    report.append(
        f"Significant at Bonferroni α={ALPHA_BONFERRONI:.6f}: {'YES' if stats['significant_bonferroni'] else 'NO'}"
    )
    report.append(f"Effect size ≥ {MIN_EFFECT_SIZE}: {'YES' if stats['meets_effect_size'] else 'NO'}")
    report.append(f"Hit rate ≥ {MIN_HIT_RATE:.0%}: {'YES' if stats['meets_hit_rate'] else 'NO'}")
    report.append("")

    if stats["significant_bonferroni"] and stats["meets_effect_size"]:
        report.append("VERDICT: SENTIMENT HAS PREDICTIVE POWER (Bonferroni-corrected)")
    elif stats["significant_uncorrected"] and stats["meets_effect_size"]:
        report.append("VERDICT: WEAK EVIDENCE (significant but not Bonferroni-corrected)")
    else:
        report.append("VERDICT: NO SIGNIFICANT PREDICTIVE POWER DETECTED")

    # Per-ticker breakdown
    if len(pairs_df) > 0:
        report.append("")
        report.append("--- PER-TICKER BREAKDOWN ---")
        ticker_stats = (
            pairs_df.groupby("ticker")
            .agg(count=("match", "count"), hits=("match", "sum"), avg_return=("price_return", "mean"))
            .sort_values("count", ascending=False)
        )

        for ticker, row in ticker_stats.head(10).iterrows():
            hr = row["hits"] / row["count"] if row["count"] > 0 else 0
            report.append(
                f"  {ticker:8} | {int(row['count']):3} pairs | {hr:.0%} hit | avg ret: {row['avg_return']:.3%}"
            )

    return "\n".join(report)


def build_deviations(pair_count: int, stats: dict) -> list[str]:
    """Collect pre-registration deviations for the registry record.

    Uses the actual pair count (pair_count), not stats.get("total_pairs") —
    compute_hit_rate returns an {"error": ...} dict without a "total_pairs"
    key when non-neutral pairs < 10, which would otherwise misreport "0 pairs".

    T+1 matching is now the pre-registered behavior, so no T+0 deviation is
    appended here — a compliant run produces an empty list and the registry
    record is marked "EXECUTED".
    """
    deviations = []
    if pair_count < MIN_PAIRS:
        deviations.append(f"Only {pair_count} pairs (pre-registration requires >= {MIN_PAIRS})")
    if "error" in stats:
        deviations.append(f"compute_hit_rate error: {stats['error']}")
    return deviations


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run even with <100 pairs")
    parser.add_argument("--status", action="store_true", help="Show current data count")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()

    duck = DuckDBStore()

    # Show status
    count = duck.count_llm_sentiment_pairs()
    print(f"Current sentiment-price pairs: {count}")

    if args.status:
        duck.close()
        return

    # Check minimum
    if count < MIN_PAIRS and not args.force:
        print(f"Need {MIN_PAIRS} pairs (have {count}). Use --force to run anyway.")
        duck.close()
        return

    # Run backtest
    print(f"\nRunning backtest on {args.days}-day window...")
    pairs_df = get_sentiment_price_pairs(duck, days=args.days)

    if len(pairs_df) == 0:
        print("No pairs found. Need market_data + llm_news_sentiment with matching tickers.")
        duck.close()
        return

    stats = compute_hit_rate(pairs_df)
    report = generate_report(pairs_df, stats)
    print(report)

    # Save report
    report_path = REPORTS_DIR / f"sentiment_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    # Update hypothesis registry
    deviations = build_deviations(len(pairs_df), stats)

    try:
        registry_path = BASE_DIR / "research" / "hypothesis_registry.json"
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            for h in registry.get("hypotheses", []):
                if h.get("trial_number") == 1031:
                    # T+1 matching is now active (pre-registered); exploratory
                    # only when genuine deviations exist (pairs < MIN_PAIRS or
                    # compute_hit_rate error).
                    h["status"] = "EXECUTED" if not deviations else "EXECUTED_EXPLORATORY"
                    h["pre_registration_deviations"] = deviations
                    h["results"] = stats
                    h["executed_at"] = datetime.now().isoformat()
                    h["report_path"] = str(report_path)
                    break
            registry_path.write_text(json.dumps(registry, indent=2, default=str), encoding="utf-8")
            print("Hypothesis registry updated.")
    except Exception as e:
        print(f"Registry update error: {e}")

    duck.close()


if __name__ == "__main__":
    main()
