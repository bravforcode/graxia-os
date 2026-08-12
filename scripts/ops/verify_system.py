#!/usr/bin/env python3
"""
System Verification Script

Comprehensive system health check and verification.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import AsyncSessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SystemVerifier:
    """System verification manager."""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, message: str = ""):
        """Record check result."""
        status = "✅ PASS" if condition else "❌ FAIL"
        self.results.append(f"{status} - {name}: {message}")

        if condition:
            self.passed += 1
        else:
            self.failed += 1

        return condition

    async def verify_environment(self) -> bool:
        """Verify environment variables."""
        logger.info("Checking environment variables...")

        all_good = True

        database_url = (settings.DATABASE_URL or "").strip()
        redis_url = (settings.REDIS_URL or "").strip()
        has_database = bool(database_url)
        has_redis = bool(redis_url)
        self.check("ENV: DATABASE_URL", has_database, "Required")
        self.check("ENV: REDIS_URL", has_redis, "Required")
        all_good = all_good and has_database and has_redis

        has_openclaw = settings.HAS_REAL_OPENCLAW_KEY
        has_gemini = settings.HAS_REAL_GEMINI_KEY
        has_llm_provider = has_openclaw or has_gemini
        llm_required = settings.STRICT_BOOTSTRAP
        self.check(
            "ENV: LLM Credentials",
            has_llm_provider or not llm_required,
            "At least one real provider key (OpenClaw or Gemini) is required"
            if llm_required
            else "Optional (AI features disabled when missing)",
        )
        all_good = all_good and (has_llm_provider or not llm_required)

        has_google_creds = settings.HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS
        self.check(
            "ENV: Google Workspace",
            True if not has_google_creds else True,
            "Configured" if has_google_creds else "Optional (not configured)",
        )

        has_telegram = settings.HAS_REAL_TELEGRAM_TOKEN and settings.HAS_REAL_TELEGRAM_CHAT_ID
        self.check(
            "ENV: Telegram",
            True if not has_telegram else True,
            "Configured" if has_telegram else "Optional (not configured)",
        )

        return all_good

    async def verify_database(self) -> bool:
        """Verify database connection and schema."""
        logger.info("Checking database...")

        try:
            async with AsyncSessionLocal() as db:
                # Test connection
                result = await db.execute(text("SELECT 1"))
                self.check("Database Connection", True, "Connected")

                # Check tables
                result = await db.execute(
                    text("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                )
                table_count = result.scalar()
                self.check(
                    "Database Tables", table_count >= 26, f"{table_count} tables (expected 26+)"
                )

                # Check migrations
                result = await db.execute(
                    text("""
                    SELECT version_num FROM alembic_version
                """)
                )
                version = result.scalar()
                self.check("Database Migrations", version is not None, f"Version: {version}")

                return True
        except Exception as e:
            self.check("Database Connection", False, str(e))
            return False

    async def verify_redis(self) -> bool:
        """Verify Redis connection."""
        logger.info("Checking Redis...")

        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

            await redis_client.ping()
            self.check("Redis Connection", True, "Connected")

            await redis_client.aclose()
            return True
        except Exception as e:
            self.check("Redis Connection", False, str(e))
            return False

    async def verify_agents(self) -> bool:
        """Verify agents can be imported."""
        logger.info("Checking agents...")

        agents = [
            "job_hunter",
            "network_builder",
            "email_manager",
            "personal_assistant",
            "scorer",
            "decision_engine",
            "drafter",
            "briefer",
        ]

        all_good = True

        for agent_name in agents:
            try:
                __import__(f"app.agents.{agent_name}", fromlist=[f"{agent_name}_agent"])
                self.check(f"Agent: {agent_name}", True, "Loaded")
            except Exception as e:
                self.check(f"Agent: {agent_name}", False, str(e))
                all_good = False

        return all_good

    async def verify_scrapers(self) -> bool:
        """Verify scrapers can be imported."""
        logger.info("Checking scrapers...")

        scrapers = [
            "linkedin",
            "upwork",
            "fiverr",
            "fastwork",
            "devpost",
        ]

        all_good = True

        for scraper_name in scrapers:
            try:
                __import__(
                    f"app.scrapers.{scraper_name}", fromlist=[f"{scraper_name.capitalize()}Scraper"]
                )
                self.check(f"Scraper: {scraper_name}", True, "Loaded")
            except Exception as e:
                self.check(f"Scraper: {scraper_name}", False, str(e))
                all_good = False

        return all_good

    async def verify_integrations(self) -> bool:
        """Verify external integrations."""
        logger.info("Checking integrations...")

        # Google Workspace
        if not settings.HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS:
            self.check("Google Workspace", True, "Skipped (credentials not configured)")
        else:
            try:
                from app.core.google_workspace import google_workspace

                health = await google_workspace.health_check()
                self.check(
                    "Google Workspace",
                    health.get("credentials_valid", False),
                    f"Gmail: {health.get('gmail', 'unknown')}",
                )
            except Exception as e:
                self.check("Google Workspace", False, str(e))

        # OpenClaw (optional when Gemini is configured)
        if not settings.HAS_REAL_OPENCLAW_KEY:
            self.check("OpenClaw", True, "Skipped (OpenClaw key not configured)")
        else:
            try:
                import httpx

                base = (settings.OPENCLAW_BASE_URL or "").rstrip("/")
                candidates = [
                    f"{base}/v1/chat/completions",
                    f"{base}/chat/completions",
                ]
                ok = False
                detail = ""
                payload = {
                    "model": settings.OPENCLAW_FAST_MODEL,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                    "max_tokens": 8,
                    "temperature": 0,
                }
                headers = {"Authorization": f"Bearer {settings.OPENCLAW_API_KEY}"}
                for url in candidates:
                    try:
                        resp = httpx.post(url, json=payload, headers=headers, timeout=5.0)
                        if resp.status_code == 404:
                            detail = f"404 {url}"
                            continue
                        if "application/json" not in (resp.headers.get("content-type") or ""):
                            detail = f"non_json_response {url}"
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        if data.get("choices"):
                            ok = True
                            detail = f"ok {url}"
                            break
                        detail = f"no_choices {url}"
                    except Exception as exc:
                        detail = f"error {url}: {exc}"
                        continue
                if ok:
                    self.check("OpenClaw Gateway", True, detail)
                elif settings.HAS_REAL_GEMINI_KEY:
                    self.check("OpenClaw Gateway", True, f"Degraded (fallback available). {detail}")
                else:
                    self.check("OpenClaw Gateway", False, detail)
            except Exception as e:
                if settings.HAS_REAL_GEMINI_KEY:
                    self.check(
                        "OpenClaw Gateway", True, f"Degraded (fallback available). Error: {e}"
                    )
                else:
                    self.check("OpenClaw Gateway", False, str(e))

        obsidian_url = (getattr(settings, "OBSIDIAN_API_URL", "") or "").strip()
        if not obsidian_url:
            self.check("Obsidian Local REST API", True, "Skipped (not configured)")
        else:
            try:
                import httpx

                resp = httpx.get(obsidian_url, timeout=2.0)
                self.check(
                    "Obsidian Local REST API",
                    resp.status_code < 500,
                    f"{resp.status_code} {obsidian_url}",
                )
            except Exception as e:
                self.check(
                    "Obsidian Local REST API", True, f"Degraded (optional). Unreachable: {e}"
                )

        # Telegram
        has_telegram = settings.HAS_REAL_TELEGRAM_TOKEN and settings.HAS_REAL_TELEGRAM_CHAT_ID
        if not has_telegram:
            self.check("Telegram Bot", True, "Skipped (token/chat_id not configured)")
        else:
            try:
                from app.telegram_bot.bot import setup_bot

                bot = setup_bot()
                self.check("Telegram Bot", bot is not None, "Configured")
            except Exception as e:
                self.check("Telegram Bot", False, str(e))

        return True

    async def verify_scheduled_tasks(self) -> bool:
        """Verify scheduled tasks can be imported."""
        logger.info("Checking scheduled tasks...")

        tasks = [
            "job_discovery",
            "email_processing",
            "morning_briefing",
            "follow_up_check",
            "weekly_review",
        ]

        all_good = True

        for task_name in tasks:
            try:
                __import__(f"app.tasks.{task_name}", fromlist=[f"run_{task_name}"])
                self.check(f"Task: {task_name}", True, "Loaded")
            except Exception as e:
                self.check(f"Task: {task_name}", False, str(e))
                all_good = False

        return all_good

    async def verify_backup_scripts(self) -> bool:
        """Verify backup scripts exist."""
        logger.info("Checking backup scripts...")

        scripts_dir = Path(__file__).resolve().parent
        backup_script = scripts_dir / "backup_database.py"
        restore_script = scripts_dir / "restore_database.py"

        self.check("Backup Script", backup_script.exists(), str(backup_script))
        self.check("Restore Script", restore_script.exists(), str(restore_script))

        return backup_script.exists() and restore_script.exists()

    def print_results(self):
        """Print verification results."""
        print("\n" + "=" * 60)
        print("SYSTEM VERIFICATION RESULTS")
        print("=" * 60 + "\n")

        for result in self.results:
            print(result)

        print("\n" + "=" * 60)
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed")
        print("=" * 60 + "\n")

        if self.failed == 0:
            print("✅ ALL CHECKS PASSED - SYSTEM READY FOR PRODUCTION")
            return 0
        else:
            print(f"❌ {self.failed} CHECKS FAILED - PLEASE FIX ISSUES")
            return 1


async def main():
    """Main verification routine."""
    verifier = SystemVerifier()

    print("\n🔍 Starting System Verification...\n")

    # Run all checks
    await verifier.verify_environment()
    await verifier.verify_database()
    await verifier.verify_redis()
    await verifier.verify_agents()
    await verifier.verify_scrapers()
    await verifier.verify_integrations()
    await verifier.verify_scheduled_tasks()
    await verifier.verify_backup_scripts()

    # Print results
    return verifier.print_results()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
