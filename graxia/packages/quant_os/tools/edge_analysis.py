"""
Edge Analysis Pipeline — Extract Trading Edges from News
=========================================================
1. Fetch RSS news
2. Analyze with qwen3.5:9b (optimized prompt)
3. Extract trading edges (momentum, mean reversion, event-driven)
4. Output actionable signals for quant_os
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import requests

# === Config ===
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"
REPORTS_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\reports")
REPORTS_DIR.mkdir(exist_ok=True)

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


def fetch_rss(feed_url: str, feed_name: str, max_items: int = 10) -> list:
    """Fetch and parse an RSS feed."""
    import re

    items = []
    try:
        r = requests.get(
            feed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GraxiaBot/1.0"}
        )
        r.raise_for_status()
        root = ElementTree.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries[:max_items]:
            title = entry.findtext("title") or entry.findtext("atom:title", namespaces=ns) or ""
            link = entry.findtext("link") or ""
            desc = entry.findtext("description") or entry.findtext("atom:summary", namespaces=ns) or ""
            pub_date = entry.findtext("pubDate") or entry.findtext("atom:published", namespaces=ns) or ""
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


def fetch_all_news(max_per_feed: int = 3) -> list:
    """Fetch from all RSS feeds."""
    print("[1/4] Fetching news from RSS feeds...")
    all_items = []
    for name, url in RSS_FEEDS.items():
        items = fetch_rss(url, name, max_per_feed)
        all_items.extend(items)
        print(f"  {name}: {len(items)} items")
    print(f"  Total: {len(all_items)} articles")
    return all_items


def analyze_news(articles: list) -> dict:
    """Analyze news with qwen3.5:9b — extract edges."""
    print(f"\n[2/4] Analyzing {len(articles)} articles with {MODEL}...")

    # Build compact article summary
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']}: {a['title']}\n    {a['body'][:200]}" for i, a in enumerate(articles[:10])
    )

    prompt = f"""You are a quantitative trading analyst. Analyze these news articles and extract TRADING EDGES.

Output ONLY this JSON format (no thinking tags, no explanation):
{{
  "market_overview": "2-3 sentence summary of current market conditions",
  "edges": [
    {{
      "type": "momentum|mean_reversion|event_driven|sector_rotation|volatility",
      "ticker": "SPY",
      "direction": "long|short",
      "confidence": 0.7,
      "reasoning": "brief reason",
      "timeframe": "intraday|swing|positional",
      "entry_signal": "what to watch for",
      "risk": "main risk"
    }}
  ],
  "sectors_to_watch": ["sector1", "sector2"],
  "key_levels": {{"SPY": "support/resistance"}},
  "risk_events": ["event1", "event2"]
}}

News articles:
{articles_text}"""

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Output valid JSON only. No thinking tags. No markdown."},
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
    wall = time.time() - t0
    d = r.json()

    resp = d.get("message", {}).get("content", "")
    tokens = d.get("eval_count", 0)
    rate = tokens / max(d.get("eval_duration", 1) / 1e9, 0.01)
    print(f"  LLM: {tokens} tok, {rate:.1f} tok/s, {wall:.1f}s wall")

    # Parse JSON
    try:
        start = resp.find("{")
        end = resp.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(resp[start:end])
            print(f"  Parsed: {len(result.get('edges', []))} edges found")
            return result
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")

    return {"raw_response": resp, "parse_error": True}


def save_report(analysis: dict, articles: list) -> Path:
    """Save analysis report."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = REPORTS_DIR / f"edge_analysis_{ts}.json"

    report = {
        "generated_at": datetime.now().isoformat(),
        "model": MODEL,
        "articles_count": len(articles),
        "analysis": analysis,
        "articles": [{"title": a["title"], "source": a["source"]} for a in articles[:10]],
    }

    filepath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[3/4] Saved: {filepath}")
    return filepath


def feed_duckdb(analysis: dict):
    """Feed results into DuckDB."""
    print("\n[4/4] Writing to DuckDB...")
    try:
        sys.path.insert(0, r"C:\Users\menum\graxia os\graxia\packages\quant_os")
        from data_pipeline.storage.duckdb_store import DuckDBStore

        duck = DuckDBStore()

        # Create articles from edges
        articles = []
        for edge in analysis.get("edges", []):
            articles.append(
                {
                    "title": f"{edge.get('type', '')} {edge.get('ticker', '')} {edge.get('direction', '')}",
                    "source": "edge_analysis",
                    "sentiment": "positive" if edge.get("direction") == "long" else "negative",
                    "key_facts": [edge.get("reasoning", "")],
                    "ticker_impact": [f"{edge.get('ticker', '')}: {edge.get('direction', 'neutral')}"],
                    "relevance_to_market": edge.get("confidence", "medium"),
                }
            )

        overall = {
            "overall_sentiment": "mixed",
            "market_impact_th": analysis.get("market_overview", ""),
            "action_items_th": analysis.get("sectors_to_watch", []),
        }

        if articles:
            duck.upsert_llm_news_sentiment(articles, overall, "edge_analysis")
            print(f"  DuckDB: {len(articles)} edge rows inserted")

        # Query back
        recent = duck.query_llm_sentiment(hours=1)
        print(f"  Query: {len(recent)} rows from last 1h")

        duck.close()
    except Exception as e:
        print(f"  DuckDB error: {e}")


def main():
    print("=" * 60)
    print("EDGE ANALYSIS PIPELINE")
    print(f"Model: {MODEL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Step 1: Fetch news
    articles = fetch_all_news(max_per_feed=3)
    if not articles:
        print("No articles found!")
        return

    # Step 2: Analyze
    analysis = analyze_news(articles)

    if analysis.get("parse_error"):
        print("\n[WARN] JSON parse failed, using raw response")
        print(f"  Raw: {analysis.get('raw_response', '')[:500]}")
    else:
        # Display edges
        print("\n=== TRADING EDGES ===")
        for edge in analysis.get("edges", []):
            print(f"\n  {edge.get('ticker', '?')} | {edge.get('direction', '?').upper()}")
            print(f"    Type: {edge.get('type', '?')}")
            print(f"    Confidence: {edge.get('confidence', '?')}")
            print(f"    Reasoning: {edge.get('reasoning', '?')[:80]}")
            print(f"    Timeframe: {edge.get('timeframe', '?')}")
            print(f"    Entry: {edge.get('entry_signal', '?')[:60]}")
            print(f"    Risk: {edge.get('risk', '?')[:60]}")

        print("\n=== MARKET OVERVIEW ===")
        print(f"  {analysis.get('market_overview', 'N/A')}")

        print("\n=== SECTORS TO WATCH ===")
        for s in analysis.get("sectors_to_watch", []):
            print(f"  - {s}")

        print("\n=== KEY LEVELS ===")
        for ticker, level in analysis.get("key_levels", {}).items():
            print(f"  {ticker}: {level}")

        print("\n=== RISK EVENTS ===")
        for event in analysis.get("risk_events", []):
            print(f"  - {event}")

    # Step 3: Save report
    filepath = save_report(analysis, articles)

    # Step 4: Feed DuckDB
    if not analysis.get("parse_error"):
        feed_duckdb(analysis)

    print(f"\n{'='*60}")
    print("DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
