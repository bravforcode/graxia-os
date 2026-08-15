"""
Real-Time Global News Daemon — Continuous 24/7 Operation
=========================================================
Runs forever, fetches news from 64 global sources, analyzes with LLM, stores in DuckDB.

Cycle:
1. Fetch RSS (asyncio + aiohttp — all feeds in parallel)
2. Deduplicate (skip already-seen URLs)
3. Analyze with qwen3.5:9b (single-headline mode for reliable ticker extraction)
4. Store in DuckDB
5. Sleep until next cycle

Usage:
    python realtime_daemon.py                  # Run in foreground
    python realtime_daemon.py --background     # Run as background process
    python realtime_daemon.py --cycle 300      # Custom cycle interval (seconds)
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import argparse
import asyncio
import hashlib
import json
import re
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import aiohttp
import requests

# === Config ===
BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
STATE_DIR = BASE_DIR / "state"
DB_PATH = BASE_DIR / "data_pipeline" / "storage" / "quant_os.duckdb"
SEEN_FILE = STATE_DIR / "seen_urls.json"
DAEMON_STATE = STATE_DIR / "daemon_state.json"
LATEST_SENTIMENT = STATE_DIR / "latest_sentiment.json"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"
DEFAULT_CYCLE = 300  # 5 minutes

# Graceful shutdown
_shutdown = False


def _signal_handler(sig, frame):
    global _shutdown
    print(f"\n[{_ts()}] Shutdown signal received...")
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def load_seen() -> set:
    """Load seen URLs."""
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_seen(seen: set):
    """Save seen URLs (keep last 10000) with atomic write."""
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    recent = list(seen)[-10000:]
    tmp_file = SEEN_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(recent), encoding="utf-8")
    tmp_file.replace(SEEN_FILE)  # Atomic rename


def load_daemon_state() -> dict:
    if DAEMON_STATE.exists():
        try:
            return json.loads(DAEMON_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"cycles": 0, "articles_total": 0, "errors": 0, "last_cycle": None}


def save_daemon_state(state: dict):
    """Save daemon state with atomic write."""
    DAEMON_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = DAEMON_STATE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp_file.replace(DAEMON_STATE)  # Atomic rename


# === RSS Fetcher (async) ===
async def async_fetch_rss(session: aiohttp.ClientSession, feed_url: str, feed_name: str, max_items: int = 5) -> list:
    """Fetch and parse RSS feed asynchronously."""
    items = []
    try:
        async with session.get(
            feed_url,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GraxiaDaemon/2.0"},
        ) as resp:
            if resp.status != 200:
                return []
            content = await resp.read()
            root = ElementTree.fromstring(content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

            for entry in entries[:max_items]:
                title = entry.findtext("title") or ""
                link = entry.findtext("link") or ""
                desc = entry.findtext("description") or ""
                pub_date = entry.findtext("pubDate") or ""
                desc_clean = re.sub(r"<[^>]+>", "", desc).strip()

                url_hash = hashlib.md5(link.encode()).hexdigest()[:12]
                items.append(
                    {
                        "title": title.strip(),
                        "url": link.strip(),
                        "source": feed_name,
                        "date": pub_date.strip(),
                        "body": desc_clean[:400],
                        "hash": url_hash,
                    }
                )
    except Exception:
        pass  # Silent fail for background daemon
    return items


async def async_fetch_all_feeds(feeds: dict, seen: set, max_per_feed: int = 3) -> list:
    """Fetch all feeds concurrently using asyncio.gather."""
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [async_fetch_rss(session, url, name, max_per_feed) for name, url in feeds.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    new_items = []
    for result in results:
        if isinstance(result, Exception):
            continue
        for item in result:
            if item["hash"] not in seen:
                new_items.append(item)
                seen.add(item["hash"])
    return new_items


# === LLM Analysis (single-headline, no thinking) ===
SINGLE_PROMPT = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker or empty", "c":"one sentence summary"}}

k: stock ticker. Use general knowledge for well-known companies. If unsure, leave empty.
Common: Shell->SHEL, BP->BP, Apple->AAPL, Nvidia->NVDA, Tesla->TSLA, Microsoft->MSFT, Meta->META, Amazon->AMZN, Google->GOOGL, JPMorgan->JPM, Goldman->GS, Blackstone->BX, Bitcoin->BTC-USD, Gold->GC=F, Oil->CL=F, S&P500->SPX"""


def analyze_one(article: dict) -> dict:
    """Analyze a single headline — clean JSON, no thinking tokens."""
    prompt = SINGLE_PROMPT.format(source=article["source"], title=article["title"])
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.05,
            "num_predict": 150,
            "num_ctx": 1024,
        },
    }
    try:
        r = requests.post(OLLAMA_URL, json=body, timeout=120)
        d = r.json()
        resp = d.get("message", {}).get("content", "")
        tokens = d.get("eval_count", 0)

        # Parse JSON object
        start = resp.find("{")
        end = resp.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(resp[start:end])
                ticker = parsed.get("k", "")
                # Ensure ticker is always a string (model sometimes returns list)
                if isinstance(ticker, list):
                    ticker = ",".join(str(t) for t in ticker) if ticker else ""
                return {
                    **article,
                    "llm_sentiment": parsed.get("s", "neutral"),
                    "llm_ticker": ticker,
                    "llm_impact": parsed.get("i", "low"),
                    "llm_summary_en": parsed.get("c", ""),
                    "llm_sector": "",
                    "llm_confidence": "medium",
                }
            except json.JSONDecodeError:
                pass
        # Fallback
        return {**article, "llm_sentiment": "neutral", "llm_ticker": ""}
    except Exception:
        return {**article, "llm_sentiment": "neutral", "llm_ticker": ""}


OLLAMA_MAX_PARALLEL = 2  # must match OLLAMA_NUM_PARALLEL in setup_ollama_env.py


def analyze_batch(articles: list) -> list:
    """Analyze headlines one-per-request (reliable ticker extraction), OLLAMA_MAX_PARALLEL at a time."""
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=OLLAMA_MAX_PARALLEL) as pool:
        results = list(pool.map(analyze_one, articles))

    elapsed = time.time() - t0
    print(f"  [{_ts()}] Analyzed {len(articles)} headlines in {elapsed:.0f}s")
    return results


# === DuckDB Writer ===
def write_to_duckdb(articles: list):
    """Write analyzed articles to DuckDB."""
    duck = None
    try:
        sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
        from storage.duckdb_store import DuckDBStore

        duck = DuckDBStore()

        llm_articles = []
        for a in articles:
            llm_articles.append(
                {
                    "url": a.get("url", ""),
                    "title": a.get("title", "")[:200],
                    "source": a.get("source", ""),
                    "published_at": None,
                    "analyzed_at": datetime.now().isoformat(),
                    "model": MODEL,
                    "tickers": a.get("llm_ticker", ""),
                    "sentiment": a.get("llm_sentiment", "neutral"),
                    "impact": a.get("llm_impact", "low"),
                    "categories": a.get("llm_sector", ""),
                    "entities": json.dumps(a.get("entities", [])) if a.get("entities") else "[]",
                    "summary": a.get("llm_summary_en", "")[:500],
                }
            )

        written = duck.upsert_llm_news_sentiment(llm_articles)
        return written
    except Exception as e:
        print(f"  [{_ts()}] DuckDB error: {e}")
        return 0
    finally:
        if duck:
            duck.close()


# === Sentiment Snapshot ===
def update_sentiment_snapshot(articles: list):
    """Update latest_sentiment.json for strategy consumption."""
    # Count sentiments
    sentiments = [a.get("llm_sentiment", "neutral") for a in articles]
    positive = sentiments.count("positive")
    negative = sentiments.count("negative")
    neutral = sentiments.count("neutral")

    # Ticker aggregation
    ticker_sentiments = {}
    for a in articles:
        ticker = a.get("llm_ticker", "")
        # Handle list returns (model sometimes returns ["AAPL"] instead of "AAPL")
        if isinstance(ticker, list):
            ticker = ",".join(str(t) for t in ticker) if ticker else ""
        if ticker:
            if ticker not in ticker_sentiments:
                ticker_sentiments[ticker] = {"positive": 0, "negative": 0, "neutral": 0}
            ticker_sentiments[ticker][a.get("llm_sentiment", "neutral")] += 1

    # Build summary
    positive_tickers = [t for t, s in ticker_sentiments.items() if s["positive"] > s["negative"]]
    negative_tickers = [t for t, s in ticker_sentiments.items() if s["negative"] > s["positive"]]

    if positive > negative:
        overall = "positive"
    elif negative > positive:
        overall = "negative"
    else:
        overall = "mixed"

    summary = {
        "overall_sentiment": overall,
        "ticker_count": len(ticker_sentiments),
        "positive_tickers": positive_tickers,
        "negative_tickers": negative_tickers,
        "articles_analyzed": len(articles),
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "report_time": datetime.now().isoformat(),
        "report_fresh": True,
        "query": "realtime_global",
    }

    LATEST_SENTIMENT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_SENTIMENT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


# === Main Loop ===
def fetch_twitter_sentiment(seen: set) -> list:
    """Fetch and analyze Twitter sentiment (every 3rd cycle)."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from twitter_sentiment import fetch_all_twitter

        tweets = fetch_all_twitter(seen=seen)
        if not tweets:
            return []

        # Analyze with LLM (single-headline for reliability)
        analyzed = []
        for tweet in tweets[:10]:  # Limit to 10 per cycle
            result = analyze_one(
                {
                    "title": tweet["text"][:200],
                    "url": f"https://twitter.com/{tweet['account']}",
                    "source": f"twitter_{tweet['account']}",
                    "body": tweet["text"][:400],
                    "hash": tweet["hash"],
                }
            )
            analyzed.append(result)

        return analyzed
    except Exception as e:
        print(f"  [{_ts()}] Twitter error: {e}")
        return []


def run_cycle(cycle_num: int, seen: set, feeds: dict) -> dict:
    """Run one fetch-analyze-store cycle."""
    print(f"\n{'='*60}")
    print(f"[{_ts()}] CYCLE {cycle_num}")
    print(f"{'='*60}")

    # Fetch new articles from RSS (async — all feeds in parallel)
    t0 = time.time()
    articles = asyncio.run(async_fetch_all_feeds(feeds, seen, max_per_feed=3))
    fetch_elapsed = time.time() - t0
    print(f"[{_ts()}] New RSS articles: {len(articles)} (fetched in {fetch_elapsed:.1f}s)")

    # Fetch Twitter sentiment every 3rd cycle
    twitter_articles = []
    if cycle_num % 3 == 0:
        print(f"[{_ts()}] Fetching Twitter sentiment...")
        twitter_articles = fetch_twitter_sentiment(seen)
        print(f"[{_ts()}] Twitter articles: {len(twitter_articles)}")

    all_articles = articles + twitter_articles

    if not all_articles:
        print(f"[{_ts()}] No new articles, sleeping...")
        return {"articles": 0, "analyzed": 0}

    # Show top articles
    for a in all_articles[:5]:
        print(f"  [{a['source']}] {a['title'][:60]}")

    # Analyze with LLM
    print(f"\n[{_ts()}] Analyzing {len(all_articles)} headlines with {MODEL}...")
    analyzed = analyze_batch(all_articles)

    # Write to DuckDB
    written = write_to_duckdb(analyzed)
    print(f"[{_ts()}] DuckDB: {written} rows written")

    # Update sentiment snapshot
    update_sentiment_snapshot(analyzed)
    print(f"[{_ts()}] Sentiment snapshot updated")

    # Save seen URLs
    save_seen(seen)

    # Backup DuckDB every 100 cycles
    if cycle_num % 100 == 0:
        duck = None
        try:
            sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
            from storage.duckdb_store import DuckDBStore

            duck = DuckDBStore()
            duck.backup()
        except Exception as e:
            print(f"  [{_ts()}] Backup error: {e}")
        finally:
            if duck:
                duck.close()

    return {"articles": len(all_articles), "analyzed": len(analyzed), "written": written}


def main():
    parser = argparse.ArgumentParser(description="Real-Time Global News Daemon")
    parser.add_argument("--cycle", type=int, default=DEFAULT_CYCLE, help="Seconds between cycles")
    parser.add_argument("--background", action="store_true", help="Run as background process")
    parser.add_argument("--once", action="store_true", help="Run single cycle then exit")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("REAL-TIME GLOBAL NEWS DAEMON")
    print(f"Model: {MODEL}")
    print(f"Cycle: {args.cycle}s ({args.cycle//60}min)")
    print("Sources: 64 feeds worldwide (async parallel fetch)")
    print(f"Time: {datetime.now().isoformat()}")
    print("Press Ctrl+C to stop")
    print(f"{'='*60}")

    # Import feeds
    sys.path.insert(0, str(Path(__file__).parent))
    from global_feeds import get_feeds

    # Start with tier 1, expand over time
    cycle_count = 0
    seen = load_seen()
    state = load_daemon_state()

    print(f"\n[{_ts()}] Loaded {len(seen)} seen URLs")

    while not _shutdown:
        cycle_count += 1

        # Rotate feed tiers based on cycle
        if cycle_count % 4 == 0:
            feeds = get_feeds(3)  # All feeds
            print(f"[{_ts()}] Feed tier: ALL ({len(feeds)} feeds)")
        elif cycle_count % 2 == 0:
            feeds = get_feeds(2)  # Tier 1+2
            print(f"[{_ts()}] Feed tier: T1+T2 ({len(feeds)} feeds)")
        else:
            feeds = get_feeds(1)  # Tier 1 only
            print(f"[{_ts()}] Feed tier: T1 ({len(feeds)} feeds)")

        # Run cycle
        try:
            result = run_cycle(cycle_count, seen, feeds)
            state["cycles"] = cycle_count
            state["articles_total"] = state.get("articles_total", 0) + result.get("articles", 0)
            state["last_cycle"] = datetime.now().isoformat()
            save_daemon_state(state)
        except Exception as e:
            print(f"[{_ts()}] Cycle error: {e}")
            state["errors"] = state.get("errors", 0) + 1
            save_daemon_state(state)

        if args.once:
            print(f"\n[{_ts()}] Single cycle complete, exiting.")
            break

        # Sleep with shutdown check
        print(f"\n[{_ts()}] Sleeping {args.cycle}s until next cycle...")
        for _ in range(args.cycle):
            if _shutdown:
                break
            time.sleep(1)

    print(f"\n[{_ts()}] Daemon stopped. Total cycles: {cycle_count}")
    save_daemon_state(state)


if __name__ == "__main__":
    main()
