"""
sources/news_sentiment.py — News & Sentiment Sources (NewsAPI, VADER, TextBlob)
"""
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NEWS_API_KEY, NEWS_QUERIES, RETRY_MAX, RETRY_DELAY

_vader = None
_textblob_cls = None


def _get_vader():
    global _vader
    if _vader is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
    return _vader


def _get_textblob(text: str):
    from textblob import TextBlob
    return TextBlob(text)


def fetch_newsapi(queries: list[str]) -> pd.DataFrame:
    """Fetch news from NewsAPI with retry"""
    from newsapi import NewsApiClient
    newsapi = NewsApiClient(api_key=NEWS_API_KEY)
    seen_titles = set()
    seen_urls = set()
    results = []
    for query in queries:
        for attempt in range(RETRY_MAX):
            try:
                articles = newsapi.get_everything(q=query, language="en", sort_by="publishedAt", page_size=20)
                for a in articles.get("articles", []):
                    title = a.get("title", "")
                    url = a.get("url", "")
                    if not title or title in seen_titles or url in seen_urls:
                        continue
                    seen_titles.add(title)
                    seen_urls.add(url)
                    results.append({
                        "title": title,
                        "description": a.get("description", ""),
                        "source": a.get("source", {}).get("name", ""),
                        "url": url,
                        "published_at": a.get("publishedAt", ""),
                        "query": query,
                        "fetched_at": datetime.now(),
                    })
                break
            except Exception as e:
                if attempt < RETRY_MAX - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  NewsAPI error {query}: {e}")
    df = pd.DataFrame(results)
    print(f"  NewsAPI: {len(df)} articles (deduped)")
    return df


def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment using VADER + TextBlob"""
    vader = _get_vader()
    blob = _get_textblob(text)
    v_scores = vader.polarity_scores(text)
    return {
        "vader_compound": v_scores["compound"],
        "vader_pos": v_scores["pos"],
        "vader_neg": v_scores["neg"],
        "textblob_polarity": blob.sentiment.polarity,
        "textblob_subjectivity": blob.sentiment.subjectivity,
    }


def fetch_news_with_sentiment() -> pd.DataFrame:
    print("=== Fetching News + Sentiment ===")
    df = fetch_newsapi(NEWS_QUERIES)
    if len(df) > 0:
        print("  Analyzing sentiment...")
        text_col = df["title"].fillna("") + " " + df["description"].fillna("")
        scores = text_col.apply(lambda x: pd.Series(analyze_sentiment(str(x))))
        df = pd.concat([df, scores], axis=1)
        print(f"  Total: {len(df)} articles with sentiment")
    return df
