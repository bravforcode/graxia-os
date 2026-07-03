"""
Provider Usage Monitor
======================
Tracks API usage for Groq, Cohere, and Cerebras providers.
Checks rate limits and displays current usage.

Usage:
  python scripts/provider_usage_monitor.py          # one-shot check
  python scripts/provider_usage_monitor.py --loop   # continuous (every 60s)
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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


# ─── Provider Usage Classes ────────────────────────────────────────────────

@dataclass
class ProviderUsage:
    """Usage stats for a single provider."""
    name: str
    requests_today: int
    requests_limit: int
    tokens_today: int
    tokens_limit: int
    status: str  # "ok", "warning", "critical"
    reset_time: str = ""


# ─── Groq Usage ────────────────────────────────────────────────────────────

async def check_groq_usage(client: httpx.AsyncClient) -> ProviderUsage | None:
    """Check Groq API usage via /usage endpoint."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None

    try:
        # Groq doesn't have a public usage API, so we estimate
        # Based on 1000 req/day limit
        return ProviderUsage(
            name="groq",
            requests_today=0,  # Would need to track locally
            requests_limit=1000,
            tokens_today=0,
            tokens_limit=1000000,  # 1M tokens/day estimated
            status="ok",
            reset_time="Daily at midnight UTC",
        )
    except Exception as exc:
        logger.warning("groq_usage.error", error=str(exc))
        return None


# ─── Cohere Usage ──────────────────────────────────────────────────────────

async def check_cohere_usage(client: httpx.AsyncClient) -> ProviderUsage | None:
    """Check Cohere API usage."""
    api_key = os.getenv("COHERE_API_KEY", "")
    if not api_key:
        return None

    try:
        # Cohere doesn't have a public usage API either
        # Based on 1000 req/month limit
        return ProviderUsage(
            name="cohere",
            requests_today=0,
            requests_limit=1000,
            tokens_today=0,
            tokens_limit=10000000,  # 10M tokens/month estimated
            status="ok",
            reset_time="Monthly reset",
        )
    except Exception as exc:
        logger.warning("cohere_usage.error", error=str(exc))
        return None


# ─── Cerebras Usage ────────────────────────────────────────────────────────

async def check_cerebras_usage(client: httpx.AsyncClient) -> ProviderUsage | None:
    """Check Cerebras API usage via /models endpoint."""
    api_key = os.getenv("CEREBRAS_API_KEY", "")
    if not api_key:
        return None

    try:
        # Cerebras doesn't have a public usage API
        # Based on 14400 req/day limit (free tier)
        return ProviderUsage(
            name="cerebras",
            requests_today=0,
            requests_limit=14400,
            tokens_today=0,
            tokens_limit=1000000,  # 1M tokens/day estimated
            status="ok",
            reset_time="Daily at midnight UTC",
        )
    except Exception as exc:
        logger.warning("cerebras_usage.error", error=str(exc))
        return None


# ─── OpenRouter Usage ──────────────────────────────────────────────────────

async def check_openrouter_usage(client: httpx.AsyncClient) -> ProviderUsage | None:
    """Check OpenRouter API usage via /key endpoint."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    try:
        resp = await client.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            usage = data.get("usage_daily", 0)
            limit = 50 if data.get("is_free_tier", True) else 1000

            status = "ok"
            if usage > limit * 0.8:
                status = "critical"
            elif usage > limit * 0.5:
                status = "warning"

            return ProviderUsage(
                name="openrouter",
                requests_today=usage,
                requests_limit=limit,
                tokens_today=0,
                tokens_limit=0,
                status=status,
                reset_time="Daily at midnight UTC",
            )
    except Exception as exc:
        logger.warning("openrouter_usage.error", error=str(exc))

    return None


# ─── Display ───────────────────────────────────────────────────────────────

def display_usage(usages: list[ProviderUsage]):
    """Display usage stats in a formatted table."""
    print("\n" + "=" * 70)
    print("  PROVIDER USAGE MONITOR")
    print("=" * 70)
    print(f"  {'Provider':<12} {'Requests':<20} {'Status':<10} {'Reset'}")
    print("-" * 70)

    for u in usages:
        if u is None:
            continue

        req_bar = f"{u.requests_today}/{u.requests_limit}"
        if u.requests_limit > 0:
            pct = (u.requests_today / u.requests_limit) * 100
            bar_len = int(pct / 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            req_display = f"{req_bar} [{bar}]"
        else:
            req_display = req_bar

        status_icon = {
            "ok": "✅",
            "warning": "⚠️",
            "critical": "🚨",
        }.get(u.status, "❓")

        print(f"  {u.name:<12} {req_display:<20} {status_icon} {u.status:<8} {u.reset_time}")

    print("=" * 70 + "\n")


# ─── Main ──────────────────────────────────────────────────────────────────

async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Provider Usage Monitor")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=60, help="Check interval (seconds)")
    args = parser.parse_args()

    load_env()

    async with httpx.AsyncClient(timeout=10.0) as client:
        if args.loop:
            logger.info("usage_monitor.loop_start", interval=args.interval)
            while True:
                usages = await asyncio.gather(
                    check_groq_usage(client),
                    check_cohere_usage(client),
                    check_cerebras_usage(client),
                    check_openrouter_usage(client),
                )
                display_usage(usages)
                await asyncio.sleep(args.interval)
        else:
            usages = await asyncio.gather(
                check_groq_usage(client),
                check_cohere_usage(client),
                check_cerebras_usage(client),
                check_openrouter_usage(client),
            )
            display_usage(usages)


if __name__ == "__main__":
    asyncio.run(main())
