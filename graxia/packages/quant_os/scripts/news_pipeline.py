"""
Real-Time News Pipeline
========================
Fetches financial news from multiple sources, sends to SentimentAgent,
writes results to MacroRegimeCache + Obsidian vault.

Sources:
  - RSS feeds (ForexFactory, Investing.com, CoinDesk)
  - NewsAPI (if configured)
  - Custom webhooks

Output:
  - MacroRegimeCache: Written directly by SentimentAgent (WARM PATH)
  - Obsidian: quant_os/news/{date}.md (daily digest)
  - Telegram: via CentaurTelegramAgent (if subscribed)

Usage:
  python scripts/news_pipeline.py                  # one-shot
  python scripts/news_pipeline.py --loop           # continuous (every 5 min)
  python scripts/news_pipeline.py --vault PATH     # custom vault path
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
import structlog

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agents.centaur_telegram import CentaurTelegramAgent
from core.agents.health_monitor import HealthMonitor
from core.agents.risk_agent import RiskAgent
from core.agents.sentiment_agent import SentimentAgent
from core.event_bus import EventBus
from core.events import NewsEvent
from core.news_blackout import NewsBlackout
from core.metrics import PipelineMetrics

logger = structlog.get_logger(__name__)

# ─── Load .env ─────────────────────────────────────────────────────────────


def load_env():
    """Load .env file into os.environ."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# Load env on import
load_env()

# ─── Configuration ─────────────────────────────────────────────────────────

VAULT_PATH = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        r"C:\Users\menum\quant\quant bot",
    )
)

NEWS_DIR = VAULT_PATH / "quant_os" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

# RSS Feed URLs
RSS_FEEDS = {
    # ── Tier 1: Premium Financial ──
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "bloomberg_economics": "https://feeds.bloomberg.com/economics/news.rss",
    "bloomberg_technology": "https://feeds.bloomberg.com/technology/news.rss",
    "cnbc_top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "cnbc_world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "marketwatch_top": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "marketwatch_pulse": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    # ── Tier 2: Forex & Crypto ──
    "fx_street": "https://www.fxstreet.com/rss",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # ── Tier 3: wire services ──
    "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
}

# High-impact keywords (triggers CRISIS/HIGH_UNCERTAINTY)
CRISIS_KEYWORDS = [
    "war",
    "invasion",
    "attack",
    "nuclear",
    "crash",
    "collapse",
    "default",
    "bankrupt",
    "crisis",
    "emergency",
    "sanctions",
    "blockade",
    "escalation",
    "tensions",
    "conflict",
    "military",
    "bombing",
    "missile",
]

HIGH_IMPACT_KEYWORDS = [
    "fed",
    "fomc",
    "interest rate",
    "inflation",
    "gdp",
    "unemployment",
    "non-farm",
    "nfp",
    "cpi",
    "ppi",
    "retail sales",
    "earnings",
    "dividend",
    "split",
    "merger",
    "acquisition",
    "ipo",
]


@dataclass
class NewsItem:
    """Single news item from RSS or API."""

    title: str
    link: str
    published: str
    source: str
    summary: str = ""
    sentiment: Any = None  # SentimentResult | None


@dataclass
class DailyDigest:
    """Aggregated daily news digest for Obsidian."""

    date: str
    items: list[NewsItem] = field(default_factory=list)
    avg_sentiment: float = 0.0
    regime: str = "NORMAL"
    position_multiplier: float = 1.0
    provider_stats: dict[str, int] = field(default_factory=dict)


# ─── RSS Fetcher ───────────────────────────────────────────────────────────


async def fetch_rss_feed(client: httpx.AsyncClient, name: str, url: str) -> list[NewsItem]:
    """Fetch and parse an RSS feed."""
    items = []
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code != 200:
            logger.warning("rss_fetch.failed", source=name, status=resp.status_code)
            return items

        root = ElementTree.fromstring(resp.text)
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()

            if title:
                items.append(
                    NewsItem(
                        title=title,
                        link=link,
                        published=pub_date,
                        source=name,
                        summary=description[:200],
                    )
                )

        logger.info("rss_fetch.success", source=name, count=len(items))
    except Exception as exc:
        logger.warning("rss_fetch.error", source=name, error=str(exc))

    return items


async def fetch_all_feeds(client: httpx.AsyncClient) -> list[NewsItem]:
    """Fetch all RSS feeds in parallel."""
    tasks = [fetch_rss_feed(client, name, url) for name, url in RSS_FEEDS.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for r in results:
        if isinstance(r, list):
            all_items.extend(r)

    return all_items


# ─── Impact Classification ────────────────────────────────────────────────


def classify_impact(title: str, summary: str = "") -> str:
    """Classify news impact level based on keywords."""
    text = f"{title} {summary}".lower()

    for kw in CRISIS_KEYWORDS:
        if kw in text:
            return "CRISIS"

    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in text:
            return "HIGH"

    return "MEDIUM"


# ─── Obsidian Writer ──────────────────────────────────────────────────────


def write_to_obsidian(digest: DailyDigest) -> Path:
    """Write daily digest to Obsidian vault."""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = NEWS_DIR / f"{date_str}.md"

    # Build markdown
    lines = [
        f"# Quant OS News Digest — {date_str}",
        "",
        f"**Generated:** {datetime.now(UTC).isoformat()}",
        f"**Regime:** {digest.regime}",
        f"**Avg Sentiment:** {digest.avg_sentiment:.4f}",
        f"**Position Multiplier:** {digest.position_multiplier:.4f}",
        "",
        "## Sentiment Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Headlines Analyzed | {len(digest.items)} |",
        f"| Average Sentiment | {digest.avg_sentiment:.4f} |",
        f"| Regime | {digest.regime} |",
        f"| Position Multiplier | {digest.position_multiplier:.4f} |",
        "",
        "## Provider Breakdown",
        "",
    ]

    for provider, count in digest.provider_stats.items():
        lines.append(f"- **{provider}:** {count} headlines")

    lines.extend(
        [
            "",
            "## Headlines",
            "",
        ]
    )

    for item in digest.items:
        sentiment = item.sentiment
        if sentiment:
            emoji = "🟢" if sentiment.sentiment_score > 0.3 else "🔴" if sentiment.sentiment_score < -0.3 else "🟡"
            lines.extend(
                [
                    f"### {emoji} {item.title[:80]}",
                    f"- **Source:** {item.source}",
                    f"- **Sentiment:** {sentiment.sentiment_score:.2f} (conf: {sentiment.confidence:.2f})",
                    f"- **Regime:** {sentiment.regime_override}",
                    f"- **Position Mult:** {sentiment.position_multiplier:.2f}",
                    f"- **Reasoning:** {sentiment.reasoning[:100]}",
                    f"- **Link:** [{item.link[:50]}...]({item.link})",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"### ⚪ {item.title[:80]}",
                    f"- **Source:** {item.source}",
                    "- **Status:** Not analyzed",
                    f"- **Link:** [{item.link[:50]}...]({item.link})",
                    "",
                ]
            )

    # Write file
    file_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("obsidian_write.success", path=str(file_path), items=len(digest.items))

    return file_path


# ─── Main Pipeline ─────────────────────────────────────────────────────────


async def run_pipeline(
    sentiment_agent: SentimentAgent,
    event_bus: EventBus | None = None,
    centaur: CentaurTelegramAgent | None = None,
    vault_path: Path | None = None,
    news_blackout: NewsBlackout | None = None,
) -> DailyDigest:
    """
    Run the full news pipeline:
    1. Fetch RSS feeds
    2. Classify impact
    3. Send high/medium impact to SentimentAgent
    4. Write digest to Obsidian
    5. Publish to EventBus
    6. Notify via Telegram (if CentaurTelegramAgent provided)
    """
    metrics = PipelineMetrics()
    vault = vault_path or VAULT_PATH
    news_dir = vault / "quant_os" / "news"
    news_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Fetch all feeds
        logger.info("pipeline.fetch_start")
        items = await fetch_all_feeds(client)
        logger.info("pipeline.fetch_complete", total=len(items))

        if not items:
            logger.warning("pipeline.no_items")
            metrics.log_summary(logger)
            return DailyDigest(date=datetime.now(UTC).strftime("%Y-%m-%d"))

        metrics.headlines_processed = len(items)

        # 2. Classify and filter
        high_impact = [item for item in items if classify_impact(item.title, item.summary) in ("HIGH", "CRISIS")]
        logger.info("pipeline.impact_classified", high=len(high_impact), total=len(items))

        # 3. Send to SentimentAgent (top 10 headlines)
        headlines_to_analyze = high_impact[:10] if high_impact else items[:5]
        metrics.signals_generated = len(headlines_to_analyze)

        for item in headlines_to_analyze:
            event = NewsEvent(
                source="news_pipeline",
                headline=item.title,
                link=item.link,
                source_name=item.source,
                summary=item.summary,
                impact=classify_impact(item.title, item.summary),
            )
            sentiment_agent.observe(event)

        # 4. Run sentiment analysis (writes to MacroRegimeCache internally)
        payload = await sentiment_agent.act()

        # 4b. Trigger news blackout for high-impact regimes
        if news_blackout and payload:
            if payload.regime_label in ("HIGH_UNCERTAINTY", "CRISIS"):
                severity = payload.regime_label
                headline = payload.reasoning[:200] if payload.reasoning else "sentiment_analysis"
                news_blackout.trigger(severity, headline)
                logger.info(
                    "pipeline.blackout_triggered",
                    severity=severity,
                    remaining_seconds=round(news_blackout.remaining_seconds()),
                )

        # 5. Build digest from MacroRegimePayload
        digest = DailyDigest(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            items=headlines_to_analyze,
            avg_sentiment=payload.confidence if payload else 0.0,
            regime=payload.regime_label if payload else "NORMAL",
            position_multiplier=payload.position_multiplier if payload else 1.0,
            provider_stats={"source": 1} if payload else {},
        )

        metrics.current_regime = digest.regime
        metrics.current_position_mult = digest.position_multiplier

        # 6. Write to Obsidian
        file_path = write_to_obsidian(digest)

        # 7. Publish to EventBus (typed MacroRegimePayload)
        if event_bus and payload:
            await event_bus.publish("news.analyzed", payload)
            logger.info("pipeline.event_published")

        # 8. Notify via Telegram (high-impact news only)
        if centaur and payload:
            if payload.regime_label in ("HIGH_UNCERTAINTY", "CRISIS"):
                msg = (
                    f"📰 *NEWS ALERT*\n\n"
                    f"Regime: `{payload.regime_label}`\n"
                    f"Confidence: `{payload.confidence:.2f}`\n"
                    f"Position Mult: `{payload.position_multiplier:.2f}`\n"
                    f"Headlines: {len(headlines_to_analyze)}\n"
                    f"Source: `{payload.source_provider}`\n\n"
                    f"```{payload.reasoning[:200]}```"
                )
                tg_client = await centaur._ensure_client()
                token = centaur._token
                chat_id = centaur._chat_id
                if tg_client and token and chat_id:
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        resp = await tg_client.post(
                            url,
                            json={
                                "chat_id": chat_id,
                                "text": msg,
                                "parse_mode": "Markdown",
                            },
                        )
                        if resp.status_code == 200:
                            logger.info("pipeline.telegram_sent", regime=payload.regime_label)
                        else:
                            logger.warning("pipeline.telegram_failed", status=resp.status_code)
                    except Exception as exc:
                        logger.warning("pipeline.telegram_error", error=str(exc))
                else:
                    logger.warning("pipeline.telegram_no_config")

        metrics.log_summary(logger)
        return digest


# ─── CLI ───────────────────────────────────────────────────────────────────


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Real-Time News Pipeline")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval (seconds)")
    parser.add_argument("--vault", type=str, help="Obsidian vault path")
    parser.add_argument("--telegram", action="store_true", help="Enable Telegram notifications")
    args = parser.parse_args()

    vault = Path(args.vault) if args.vault else VAULT_PATH

    # Create sentiment agent (writes to MacroRegimeCache internally)
    sentiment = SentimentAgent()

    # Create risk agent (logs regime-based position sizing)
    risk = RiskAgent()

    # Create news blackout gate
    blackout = NewsBlackout()

    # Create event bus and subscribe risk agent
    bus = EventBus()
    bus.subscribe("news.analyzed", risk.observe)

    # Optionally create CentaurTelegramAgent
    centaur = CentaurTelegramAgent() if args.telegram else None

    # Health monitor tracks pipeline liveness
    health = HealthMonitor(stale_threshold_seconds=args.interval * 3)
    previous_regime = "NORMAL"

    try:
        if args.loop:
            logger.info("pipeline.loop_start", interval=args.interval)
            while True:
                try:
                    digest = await run_pipeline(sentiment, event_bus=bus, centaur=centaur, vault_path=vault, news_blackout=blackout)
                    health.record_success()
                    logger.info(
                        "pipeline.cycle_complete",
                        sentiment=digest.avg_sentiment,
                        regime=digest.regime,
                    )

                    # Send daily summary on regime change
                    if centaur and digest.regime != previous_regime and previous_regime != "NORMAL":
                        try:
                            tg_client = await centaur._ensure_client()
                            token = centaur._token
                            chat_id = centaur._chat_id
                            if tg_client and token and chat_id:
                                summary_msg = (
                                    f"📊 *PIPELINE SUMMARY*\n\n"
                                    f"Regime: `{previous_regime}` → `{digest.regime}`\n"
                                    f"Sentiment: `{digest.avg_sentiment:.4f}`\n"
                                    f"Position Mult: `{digest.position_multiplier:.2f}`\n"
                                    f"Headlines: `{len(digest.items)}`"
                                )
                                url = f"https://api.telegram.org/bot{token}/sendMessage"
                                resp = await tg_client.post(url, json={"chat_id": chat_id, "text": summary_msg, "parse_mode": "Markdown"})
                                if resp.status_code == 200:
                                    logger.info("pipeline.daily_summary_sent", regime=digest.regime)
                                else:
                                    logger.warning("pipeline.daily_summary_failed", status=resp.status_code)
                        except Exception as exc:
                            logger.warning("pipeline.daily_summary_error", error=str(exc))
                    previous_regime = digest.regime

                except Exception as exc:
                    health.record_failure()
                    logger.exception("pipeline.cycle_error", error=str(exc))

                if health.is_stale():
                    status = health.get_status()
                    logger.warning("pipeline.stale", **status)

                await asyncio.sleep(args.interval)
        else:
            digest = await run_pipeline(sentiment, event_bus=bus, centaur=centaur, vault_path=vault, news_blackout=blackout)
            print(f"\n{'='*60}")
            print("  Pipeline Complete")
            print(f"  Headlines: {len(digest.items)}")
            print(f"  Sentiment: {digest.avg_sentiment:.4f}")
            print(f"  Regime: {digest.regime}")
            print(f"  Position Mult: {digest.position_multiplier:.4f}")
            print(f"{'='*60}\n")
    finally:
        await sentiment.shutdown()
        if centaur:
            await centaur.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
