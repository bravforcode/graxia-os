"""
Graxia Research Agent — News Gathering + Analysis (v2 RSS)
===========================================================
Fetches financial news via RSS feeds → sends to local LLM (Ollama)
for structured extraction → saves to reports/

Usage:
    python research_agent.py                          # default: Thai finance
    python research_agent.py --query "Fed rate" --max 5
    python research_agent.py --model qwen3.5:9b
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

sys.stdout.reconfigure(encoding="utf-8")

# --- Config ---
DEFAULT_MODEL = "qwen3.5:9b"
OLLAMA_URL = "http://localhost:11434/api/chat"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Financial RSS feeds (free, no API key, no rate limit)
# Reuters feeds are down (DNS resolution fails) — replaced with working sources
RSS_FEEDS = {
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "cnbc_world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "bbc_business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
    "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
}


# --- RSS Fetch ---
def fetch_rss(feed_url: str, feed_name: str, max_items: int = 10) -> list[dict]:
    """Fetch and parse an RSS feed."""
    import requests

    items = []
    try:
        r = requests.get(
            feed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GraxiaBot/1.0"}
        )
        r.raise_for_status()
        root = ElementTree.fromstring(r.content)

        # Handle both RSS and Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries[:max_items]:
            title = entry.findtext("title") or entry.findtext("atom:title", namespaces=ns) or ""
            link = (
                entry.findtext("link")
                or (
                    entry.find("atom:link", ns).attrib.get("href", "")
                    if entry.find("atom:link", ns) is not None
                    else ""
                )
                or ""
            )
            desc = entry.findtext("description") or entry.findtext("atom:summary", namespaces=ns) or ""
            pub_date = entry.findtext("pubDate") or entry.findtext("atom:published", namespaces=ns) or ""

            # Strip HTML tags from description
            import re

            desc_clean = re.sub(r"<[^>]+>", "", desc).strip()

            items.append(
                {
                    "title": title.strip(),
                    "url": link.strip(),
                    "source": feed_name,
                    "date": pub_date.strip(),
                    "body": desc_clean[:500],
                }
            )
    except Exception as e:
        print(f"  WARN: {feed_name} failed: {e}")

    return items


def search_all_feeds(query: str, max_per_feed: int = 5) -> list[dict]:
    """Search all RSS feeds and return relevant articles."""
    all_items = []
    for name, url in RSS_FEEDS.items():
        print(f"  Fetching {name}...")
        items = fetch_rss(url, name, max_per_feed)
        all_items.extend(items)
        print(f"    Got {len(items)} items")

    # Filter by query keywords (simple relevance)
    query_words = query.lower().split()
    scored = []
    for item in all_items:
        text = (item["title"] + " " + item["body"]).lower()
        score = sum(1 for w in query_words if w in text)
        scored.append((score, item))

    # Sort by relevance, return top items
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[: max_per_feed * 3]]


# --- LLM ---
def analyze_with_llm(
    articles: list[dict],
    model: str = DEFAULT_MODEL,
    query: str = "",
) -> dict:
    """Send articles to Ollama for structured analysis."""

    articles_text = "\n\n".join(
        f"--- ARTICLE {i+1} [{a['source']}] ---\n"
        f"Title: {a['title']}\n"
        f"Date: {a['date']}\n"
        f"Summary: {a['body'][:400]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Analyze these financial news articles about "{query}".
Respond ONLY in valid JSON, no thinking tags, no explanation:
{{
  "query": "{query}",
  "analysis_date": "{datetime.now().strftime('%Y-%m-%d %H:%M')}",
  "articles_count": {len(articles)},
  "articles": [
    {{
      "title": "...",
      "source": "...",
      "sentiment": "positive|negative|neutral",
      "key_facts": ["fact1", "fact2"],
      "relevance_to_market": "high|medium|low",
      "ticker_impact": ["TICKER: positive/negative"]
    }}
  ],
  "overall_sentiment": "positive|negative|neutral|mixed",
  "market_impact_th": "...(Thai 2-3 sentences about market impact)",
  "action_items_th": ["...(Thai: what quant_os should monitor)"]
}}
Articles:
{articles_text}"""

    import requests

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Do not use thinking tags. Output JSON directly.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
            "num_gpu": 22,
            "num_ctx": 2048,
            "num_batch": 256,
        },
    }

    t0 = time.time()
    r = requests.post(OLLAMA_URL, json=body, timeout=300)
    elapsed = time.time() - t0
    data = r.json()

    resp = data.get("message", {}).get("content", "")
    eval_count = data.get("eval_count", 0)
    rate = eval_count / max(data.get("eval_duration", 1) / 1e9, 0.01)

    print(f"  LLM: {eval_count} tok, {rate:.1f} tok/s, {elapsed:.1f}s wall")

    # Parse JSON
    try:
        start = resp.find("{")
        end = resp.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(resp[start:end])
    except json.JSONDecodeError:
        pass

    return {"raw_response": resp, "parse_error": True}


# --- Report ---
def save_report(analysis: dict, query: str) -> Path:
    """Save analysis report to reports/."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_query = "".join(c if c.isalnum() else "_" for c in query)[:30]
    filename = f"research_{safe_query}_{ts}.json"
    filepath = REPORTS_DIR / filename

    report = {
        "generated_at": datetime.now().isoformat(),
        "query": query,
        "model": analysis.get("model", DEFAULT_MODEL),
        "analysis": analysis,
    }

    filepath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {filepath}")
    return filepath


# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Graxia Research Agent v2")
    parser.add_argument("--query", default="stock market financial news", help="Search focus")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model")
    parser.add_argument("--max", type=int, default=5, help="Max articles per feed")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("GRAXIA RESEARCH AGENT v2 (RSS)")
    print(f"Query: {args.query}")
    print(f"Model: {args.model}")
    print(f"Feeds: {len(RSS_FEEDS)} RSS sources")
    print(f"{'='*60}\n")

    # Step 1: Fetch from RSS feeds
    print("[1/3] Fetching financial news via RSS...")
    articles = search_all_feeds(args.query, max_per_feed=args.max)
    print(f"\n  Total relevant articles: {len(articles)}")

    if not articles:
        print("  No articles found. Check network / feeds.")
        return

    # Show top results
    print("\n  Top articles:")
    for i, a in enumerate(articles[:10]):
        print(f"  {i+1}. [{a['source']}] {a['title'][:70]}")

    # Step 2: Analyze with LLM
    print(f"\n[2/3] Analyzing with {args.model}...")
    analysis = analyze_with_llm(articles[:10], model=args.model, query=args.query)

    if analysis.get("parse_error"):
        print("  WARNING: JSON parse failed.")
        print(f"  Raw: {analysis.get('raw_response', '')[:200]}")
    else:
        print(f"  Overall sentiment: {analysis.get('overall_sentiment', '?')}")
        print(f"  Articles: {analysis.get('articles_count', '?')}")

    # Step 3: Save
    print("\n[3/3] Saving report...")
    filepath = save_report(analysis, args.query)

    print(f"\n{'='*60}")
    print(f"DONE — {filepath}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
