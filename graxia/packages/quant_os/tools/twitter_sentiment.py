"""
Twitter/X Sentiment Scraper — Real-time social media sentiment
Uses Nitter (open source Twitter frontend) for scraping
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from datetime import datetime
from pathlib import Path

import requests

# Nitter instances (public, no API key needed)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.cz",
]

# Financial Twitter accounts to track
FINANCE_ACCOUNTS = [
    "zaborhedge",  # Zerohedge
    "markets",  # Bloomberg Markets
    "business",  # Bloomberg Business
    "CNBC",  # CNBC
    "Reuters",  # Reuters
    "FT",  # Financial Times
    "WSJ",  # Wall Street Journal
    "DeItaone",  # Breaking market news
    "unusual_whales",  # Unusual options activity
    "tier1alpha",  # Market data
    "FirstSquawk",  # Breaking news
    "ForexLive",  # Forex news
    "GoldTelegraph_",  # Gold/commodities
    "BitcoinMagazine",  # Bitcoin news
    "coindesk",  # Crypto news
]

# Keywords to track
TRACKED_KEYWORDS = [
    "fed",
    "interest rate",
    "inflation",
    "recession",
    "earnings",
    "stock market",
    "S&P 500",
    "nasdaq",
    "dow jones",
    "bitcoin",
    "ethereum",
    "crypto",
    "oil",
    "gold",
    "commodities",
    "forex",
    "dollar",
    "euro",
    "yen",
    "breaking",
    "just in",
    "urgent",
]

STATE_DIR = Path(__file__).parent.parent / "state"
TWITTER_STATE = STATE_DIR / "twitter_sentiment.json"


def fetch_nitter_tweets(account: str, instance: str = None, limit: int = 10) -> list:
    """Fetch tweets from Nitter instance."""
    if instance is None:
        instance = NITTER_INSTANCES[0]

    items = []
    try:
        url = f"{instance}/{account}"
        r = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GraxiaDaemon/1.0"}
        )
        if r.status_code == 200:
            # Simple HTML parsing for tweets
            import re

            tweets = re.findall(r'class="tweet-content[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL)
            for tweet in tweets[:limit]:
                clean = re.sub(r"<[^>]+>", "", tweet).strip()
                if clean:
                    tweet_hash = hashlib.md5(clean.encode()).hexdigest()[:12]
                    items.append(
                        {
                            "text": clean[:500],
                            "account": account,
                            "source": f"twitter_{account}",
                            "hash": tweet_hash,
                            "fetched_at": datetime.now().isoformat(),
                        }
                    )
    except Exception:
        pass
    return items


def fetch_all_twitter(accounts: list | None = None, seen: set | None = None, limit: int = 5) -> list:
    """Fetch from all tracked Twitter accounts."""
    if accounts is None:
        accounts = FINANCE_ACCOUNTS
    if seen is None:
        seen = set()

    all_tweets = []
    for account in accounts:
        tweets = fetch_nitter_tweets(account, limit=limit)
        for tweet in tweets:
            if tweet["hash"] not in seen:
                all_tweets.append(tweet)
                seen.add(tweet["hash"])

    return all_tweets


def analyze_twitter_sentiment(tweets: list, llm_url: str = "http://localhost:11434/api/chat") -> list:
    """Analyze tweet sentiment with LLM."""
    if not tweets:
        return []

    results = []
    batch_size = 10

    for i in range(0, len(tweets), batch_size):
        batch = tweets[i : i + batch_size]

        tweets_text = "\n".join(f"[{j+1}] @{t['account']}: {t['text'][:200]}" for j, t in enumerate(batch))

        prompt = f"""Analyze these financial tweets. Return JSON array:
[{{"t":"number","s":"positive/negative/neutral","i":"high/medium/low","k":"tickers","c":"summary"}}]
Extract tickers from cashtags ($AAPL) and company mentions. JSON only.

Tweets:
{tweets_text}"""

        body = {
            "model": "qwen3.5:9b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "keep_alive": -1,
            "options": {
                "temperature": 0.05,
                "num_predict": 1500,
                "num_gpu": 22,
                "num_ctx": 2048,
                "num_batch": 512,
            },
        }

        try:
            r = requests.post(llm_url, json=body, timeout=180)
            d = r.json()
            resp = d.get("message", {}).get("content", "")

            start = resp.find("[")
            end = resp.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(resp[start:end])
                for j, p in enumerate(parsed):
                    if j < len(batch):
                        results.append(
                            {
                                **batch[j],
                                "sentiment": p.get("s", "neutral"),
                                "impact": p.get("i", "low"),
                                "tickers": p.get("k", ""),
                                "summary": p.get("c", ""),
                            }
                        )
        except Exception:
            pass

        time.sleep(1)

    return results


def save_twitter_state(state: dict):
    """Save Twitter sentiment state."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TWITTER_STATE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def load_twitter_state() -> dict:
    """Load Twitter sentiment state."""
    if TWITTER_STATE.exists():
        try:
            return json.loads(TWITTER_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tweets_analyzed": 0, "last_fetch": None, "sentiment_counts": {}}


if __name__ == "__main__":
    import time

    print("=== Twitter Sentiment Test ===")
    tweets = fetch_all_twitter(limit=3)
    print(f"Fetched {len(tweets)} tweets")
    for t in tweets[:3]:
        print(f"  @{t['account']}: {t['text'][:80]}...")
