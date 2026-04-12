#!/usr/bin/env python3
"""
System Verification Script

Comprehensive system health check and verification.
"""
import asyncio
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import AsyncSessionLocal
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
        
        required_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "OPENCLAW_API_KEY",
            "GEMINI_API_KEY",
        ]
        
        optional_vars = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REFRESH_TOKEN",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ]
        
        all_good = True
        
        for var in required_vars:
            value = getattr(settings, var, None)
            has_value = value is not None and value != ""
            self.check(f"ENV: {var}", has_value, "Required")
            all_good = all_good and has_value
        
        for var in optional_vars:
            value = getattr(settings, var, None)
            has_value = value is not None and value != ""
            self.check(f"ENV: {var}", has_value, "Optional (recommended)")
        
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
                result = await db.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """))
                table_count = result.scalar()
                self.check(
                    "Database Tables",
                    table_count >= 26,
                    f"{table_count} tables (expected 26+)"
                )
                
                # Check migrations
                result = await db.execute(text("""
                    SELECT version_num FROM alembic_version
                """))
                version = result.scalar()
                self.check(
                    "Database Migrations",
                    version is not None,
                    f"Version: {version}"
                )
                
                return True
        except Exception as e:
            self.check("Database Connection", False, str(e))
            return False
    
    async def verify_redis(self) -> bool:
        """Verify Redis connection."""
        logger.info("Checking Redis...")
        
        try:
            import redis.asyncio as aioredis
            
            redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True
            )
            
            await redis_client.ping()
            self.check("Redis Connection", True, "Connected")
            
            await redis_client.close()
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
                module = __import__(
                    f"app.agents.{agent_name}",
                    fromlist=[f"{agent_name}_agent"]
                )
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
                module = __import__(
                    f"app.scrapers.{scraper_name}",
                    fromlist=[f"{scraper_name.capitalize()}Scraper"]
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
        try:
            from app.core.google_workspace import google_workspace
            health = await google_workspace.health_check()
            self.check(
                "Google Workspace",
                health.get('credentials_valid', False),
                f"Gmail: {health.get('gmail', 'unknown')}"
            )
        except Exception as e:
            self.check("Google Workspace", False, str(e))
        
        # OpenClaw
        try:
            from app.core.openclaw import openclaw_client
            health = await openclaw_client.health_check()
            self.check(
                "OpenClaw",
                health.get('status') == 'healthy',
                f"Status: {health.get('status')}"
            )
        except Exception as e:
            self.check("OpenClaw", False, str(e))
        
        # Telegram
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
                module = __import__(
                    f"app.tasks.{task_name}",
                    fromlist=[f"run_{task_name}"]
                )
                self.check(f"Task: {task_name}", True, "Loaded")
            except Exception as e:
                self.check(f"Task: {task_name}", False, str(e))
                all_good = False
        
        return all_good
    
    async def verify_backup_scripts(self) -> bool:
        """Verify backup scripts exist."""
        logger.info("Checking backup scripts...")
        
        backup_script = Path("backend/scripts/backup_database.py")
        restore_script = Path("backend/scripts/restore_database.py")
        
        self.check(
            "Backup Script",
            backup_script.exists(),
            str(backup_script)
        )
        self.check(
            "Restore Script",
            restore_script.exists(),
            str(restore_script)
        )
        
        return backup_script.exists() and restore_script.exists()
    
    def print_results(self):
        """Print verification results."""
        print("\n" + "="*60)
        print("SYSTEM VERIFICATION RESULTS")
        print("="*60 + "\n")
        
        for result in self.results:
            print(result)
        
        print("\n" + "="*60)
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed")
        print("="*60 + "\n")
        
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
