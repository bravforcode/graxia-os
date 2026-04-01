import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


async def _send_telegram(msg: str) -> None:
    try:
        from app.telegram_bot.bot import send_message
        await send_message(msg)
    except Exception:
        pass


async def check_system_ready() -> tuple[bool, str, list[str]]:
    issues: list[str] = []
    warnings: list[str] = []

    # ── 1. Profile completeness ──────────────────────────
    profile_path = Path(settings.IDENTITY_PATH)
    if not profile_path.exists():
        profile_path = Path("identity/profile.yaml")
    try:
        with open(profile_path) as f:
            profile = yaml.safe_load(f)
        name = profile.get("personal", {}).get("name", "")
        if "[YOUR" in name:
            issues.append("Profile: personal.name not filled in")
        north_star = profile.get("goals", {}).get("north_star", "")
        if "[" in north_star:
            issues.append("Profile: goals.north_star not filled in")
        projects = profile.get("projects", [])
        if not projects:
            issues.append("Profile: no projects defined")
        sample_msg = profile.get("voice_and_tone", {}).get("sample_english_message", "")
        if "[PASTE" in sample_msg:
            issues.append("Profile: voice sample not filled in")
    except Exception as e:
        issues.append(f"Profile: cannot load profile.yaml — {e}")

    # ── 2. API keys ──────────────────────────────────────
    if not settings.GEMINI_API_KEY:
        issues.append("API: GEMINI_API_KEY not set")
    if not settings.TELEGRAM_BOT_TOKEN:
        issues.append("API: TELEGRAM_BOT_TOKEN not set")
    if not settings.TELEGRAM_CHAT_ID:
        issues.append("API: TELEGRAM_CHAT_ID not set")

    # ── 3. Database ──────────────────────────────────────
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        issues.append(f"Database: cannot connect — {e}")

    # ── 4. Degraded checks (warnings only) ───────────────
    if not settings.SERPAPI_KEY:
        warnings.append("SerpAPI not set — search limited to direct scraping")

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
    except Exception:
        warnings.append("Redis unavailable — caching and Celery tasks disabled")

    try:
        import chromadb
        chromadb.Client()
    except Exception:
        warnings.append("ChromaDB unavailable — vector features disabled")

    if issues:
        mode = "blocked"
        msg = "🚫 Personal OS BLOCKED — resolve these issues:\n" + "\n".join(f"• {i}" for i in issues)
        await _send_telegram(msg)
        return False, mode, issues

    if warnings:
        mode = "degraded"
        msg = f"⚠️ Personal OS running in degraded mode:\n" + "\n".join(f"• {w}" for w in warnings) + "\nCore features active."
        await _send_telegram(msg)
    else:
        mode = "full"
        await _send_telegram("✅ Personal OS v3 online. Ready to find your next win.")

    return True, mode, warnings
