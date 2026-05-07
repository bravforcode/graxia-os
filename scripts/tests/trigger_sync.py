#!/usr/bin/env python3
"""Trigger SkillsMP sync manually"""
import asyncio
import sys
sys.path.insert(0, 'backend')

from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.jobs.skillsmp_sync import run_hourly_sync
from app.config import settings

async def main():
    print(f"SKILLSMP_API_KEY: {'✅ Set' if settings.SKILLSMP_API_KEY else '❌ Not set'}")
    print(f"API Key: {settings.SKILLSMP_API_KEY[:20]}..." if settings.SKILLSMP_API_KEY else "")
    
    async with AsyncSessionLocal() as db:
        print("\n🔄 Running SkillsMP sync...")
        result = await run_hourly_sync(db, settings.SKILLSMP_API_KEY)
        
        if result.get("status") == "success":
            stats = result.get("stats", {})
            print(f"\n✅ Sync completed!")
            print(f"   Total processed: {stats.get('total_processed', 0)}")
            print(f"   Added: {stats.get('total_added', 0)}")
            print(f"   Updated: {stats.get('total_updated', 0)}")
            print(f"   Errors: {stats.get('errors', 0)}")
        else:
            print(f"\n❌ Sync failed: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
