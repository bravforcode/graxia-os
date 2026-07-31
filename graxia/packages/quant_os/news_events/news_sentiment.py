"""
News Sentiment Bridge — Converts research agent reports → quant_os strategy format.
====================================================================================
Provides:
- Load latest research report from reports/
- Extract sentiment per ticker
- Provide overall market sentiment for strategy consumption
- Historical sentiment tracking for backtesting

Usage:
    from news_events.news_sentiment import NewsSentimentStore
    store = NewsSentimentStore()
    store.load_latest_report()
    sentiment = store.get_ticker_sentiment("NVO")
    overall = store.get_overall_sentiment()
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path


class NewsSentimentStore:
    """
    Stores and queries news sentiment from research agent reports.
    Designed for strategy consumption — provides ticker-level and overall sentiment.
    """

    def __init__(self, reports_dir: Path | None = None):
        self._reports_dir = reports_dir or Path(__file__).parent.parent / "reports"
        self._current_report: dict | None = None
        self._report_time: datetime | None = None
        self._ticker_sentiments: dict[str, list[dict]] = {}  # ticker → [sentiment records]
        self._overall_sentiment: str = "neutral"
        self._market_impact_th: str = ""
        self._action_items_th: list[str] = []

    def load_latest_report(self) -> bool:
        """Load the most recent research report from reports/."""
        if not self._reports_dir.exists():
            return False

        report_files = sorted(
            self._reports_dir.glob("research_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not report_files:
            return False

        latest = report_files[0]
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            self._parse_report(data)
            return True
        except (json.JSONDecodeError, KeyError):
            return False

    def load_report(self, report_path: Path) -> bool:
        """Load a specific research report."""
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self._parse_report(data)
            return True
        except (json.JSONDecodeError, KeyError):
            return False

    def _parse_report(self, data: dict) -> None:
        """Parse a research report into internal state."""
        self._current_report = data
        self._report_time = datetime.fromisoformat(data.get("generated_at", datetime.now().isoformat()))

        analysis = data.get("analysis", {})
        self._overall_sentiment = analysis.get("overall_sentiment", "neutral")
        self._market_impact_th = analysis.get("market_impact_th", "")
        self._action_items_th = analysis.get("action_items_th", [])

        # Parse per-article ticker sentiments
        # LLM may return: {"TICKER": "SPY: negative"} or {"TICKER": "SPY", "positive/negative": "negative"}
        # or {"TICKER": "SPY", "impact": "negative"}
        self._ticker_sentiments = {}
        for article in analysis.get("articles", []):
            for impact in article.get("ticker_impact", []):
                ticker = ""
                sentiment = "neutral"

                if isinstance(impact, dict):
                    raw_ticker = impact.get("TICKER", "")
                    # Check if ticker contains sentiment (e.g., "SPY: negative")
                    if ":" in raw_ticker:
                        parts = raw_ticker.split(":", 1)
                        ticker = parts[0].strip()
                        sentiment = parts[1].strip().lower()
                    else:
                        ticker = raw_ticker.strip()
                        # Handle different field names from LLM
                        sentiment = (
                            impact.get("positive/negative", "").lower() or impact.get("impact", "").lower() or "neutral"
                        )
                elif isinstance(impact, str):
                    # Handle string format "TICKER: sentiment"
                    parts = impact.split(":", 1)
                    ticker = parts[0].strip()
                    sentiment = parts[1].strip().lower() if len(parts) > 1 else "neutral"

                if ticker:
                    if ticker not in self._ticker_sentiments:
                        self._ticker_sentiments[ticker] = []
                    self._ticker_sentiments[ticker].append(
                        {
                            "sentiment": sentiment,
                            "source": article.get("source", ""),
                            "title": article.get("title", ""),
                            "relevance": article.get("relevance_to_market", "low"),
                            "key_facts": article.get("key_facts", []),
                        }
                    )

    def get_ticker_sentiment(self, ticker: str) -> dict:
        """
        Get aggregated sentiment for a specific ticker.
        Returns: {"sentiment": "positive|negative|neutral|mixed", "confidence": float, "sources": list}
        """
        records = self._ticker_sentiments.get(ticker, [])
        if not records:
            return {"sentiment": "neutral", "confidence": 0.0, "sources": []}

        # Count sentiments
        sentiments = [r["sentiment"] for r in records]
        pos = sentiments.count("positive")
        neg = sentiments.count("negative")
        total = len(sentiments)

        if pos > neg:
            overall = "positive"
        elif neg > pos:
            overall = "negative"
        elif pos == neg and pos > 0:
            overall = "mixed"
        else:
            overall = "neutral"

        confidence = max(pos, neg) / total if total > 0 else 0.0

        return {
            "sentiment": overall,
            "confidence": confidence,
            "sources": list(set(r["source"] for r in records)),
            "article_count": total,
        }

    def get_overall_sentiment(self) -> dict:
        """Get overall market sentiment from latest report."""
        return {
            "sentiment": self._overall_sentiment,
            "market_impact_th": self._market_impact_th,
            "action_items_th": self._action_items_th,
            "report_time": self._report_time.isoformat() if self._report_time else None,
        }

    def get_all_tickers(self) -> list[str]:
        """Get list of all tickers mentioned in latest report."""
        return list(self._ticker_sentiments.keys())

    def get_negative_tickers(self) -> list[str]:
        """Get tickers with negative sentiment (potential shorts or avoids)."""
        return [
            ticker
            for ticker, records in self._ticker_sentiments.items()
            if any(r["sentiment"] == "negative" for r in records)
        ]

    def get_positive_tickers(self) -> list[str]:
        """Get tickers with positive sentiment (potential longs)."""
        return [
            ticker
            for ticker, records in self._ticker_sentiments.items()
            if any(r["sentiment"] == "positive" for r in records)
        ]

    def is_report_fresh(self, max_age_hours: int = 4) -> bool:
        """Check if current report is fresh enough for trading decisions."""
        if not self._report_time:
            return False
        age = datetime.now() - self._report_time.replace(tzinfo=None)
        return age < timedelta(hours=max_age_hours)

    def get_summary(self) -> dict:
        """Get a summary suitable for strategy consumption."""
        return {
            "overall_sentiment": self._overall_sentiment,
            "ticker_count": len(self._ticker_sentiments),
            "positive_tickers": self.get_positive_tickers(),
            "negative_tickers": self.get_negative_tickers(),
            "market_impact_th": self._market_impact_th,
            "action_items_th": self._action_items_th,
            "report_fresh": self.is_report_fresh(),
            "report_time": self._report_time.isoformat() if self._report_time else None,
        }
