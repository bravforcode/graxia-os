#!/usr/bin/env python3
"""
Scraper Recovery & Testing Scripts
Enterprise-grade recovery tools for scraper management
"""
import asyncio
import argparse
import sys
from datetime import datetime, timezone
from typing import List

# Add parent to path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.models.scraper_health import ScraperHealth
from sqlalchemy import select
from app.scrapers.smart_base import unmute_scraper, get_scraper_health
from app.telegram_bot.bot import send_message


ALL_SCRAPERS = [
    "linkedin",
    "upwork", 
    "fiverr",
    "fastwork",
    "devpost",
    "eventpop",
    "serpapi",
    "rss_reader"
]


async def list_scraper_status():
    """List all scrapers and their health status."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ScraperHealth))
        health_records = result.scalars().all()
        
        print("\n" + "="*80)
        print("SCRAPER HEALTH STATUS")
        print("="*80)
        print(f"{'Source':<20} {'Muted':<8} {'Failures':<10} {'Success%':<10} {'Last Error':<30}")
        print("-"*80)
        
        for health in health_records:
            muted = "YES" if health.is_muted else "no"
            failures = health.consecutive_failures or 0
            success_rate = f"{health.success_rate:.1%}" if health.success_rate else "N/A"
            last_error = (health.last_error or "")[:27] + "..." if health.last_error and len(health.last_error) > 30 else (health.last_error or "")
            
            print(f"{health.source_name:<20} {muted:<8} {failures:<10} {success_rate:<10} {last_error:<30}")
        
        print("="*80)
        
        muted_count = sum(1 for h in health_records if h.is_muted)
        print(f"\nTotal: {len(health_records)} scrapers | Muted: {muted_count}")
        
        return health_records


async def unmute_scraper_manual(source_name: str, notify: bool = True) -> bool:
    """Manually unmute a scraper."""
    success = await unmute_scraper(source_name)
    
    if success:
        msg = f"✅ Scraper '{source_name}' has been manually unmuted."
        print(msg)
        if notify:
            try:
                await send_message(msg, parse_mode=None)
            except Exception as e:
                print(f"Failed to send notification: {e}")
        return True
    else:
        print(f"⚠️ Scraper '{source_name}' was not muted or not found.")
        return False


async def unmute_all_scrapers(notify: bool = True) -> int:
    """Unmute all muted scrapers."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScraperHealth).where(ScraperHealth.is_muted == True)
        )
        muted = result.scalars().all()
        
        if not muted:
            print("No scrapers are currently muted.")
            return 0
        
        unmuted_count = 0
        for scraper in muted:
            if await unmute_scraper_manual(scraper.source_name, notify=False):
                unmuted_count += 1
        
        msg = f"✅ Unmuted {unmuted_count} scraper(s)"
        print(msg)
        if notify and unmuted_count > 0:
            try:
                await send_message(msg, parse_mode=None)
            except:
                pass
        
        return unmuted_count


async def test_scraper(source_name: str) -> dict:
    """Test a scraper and return health status."""
    print(f"\nTesting scraper: {source_name}...")
    
    health = await get_scraper_health(source_name)
    
    if not health:
        print(f"  ❌ Scraper '{source_name}' not found in database")
        return {"source": source_name, "found": False}
    
    print("  Found: ✓")
    print(f"  Muted: {'YES' if health['is_muted'] else 'no'}")
    print(f"  Weighted Failures: {health['consecutive_failures']}")
    print(f"  Success Rate: {health['success_rate']:.1%}" if health['success_rate'] else "  Success Rate: N/A")
    
    if health['is_muted']:
        print(f"  ⚠️  Scraper is muted until: {health['muted_until']}")
    
    return {
        "source": source_name,
        "found": True,
        **health
    }


async def test_all_scrapers() -> List[dict]:
    """Test all scrapers and return results."""
    print("\n" + "="*80)
    print("TESTING ALL SCRAPERS")
    print("="*80)
    
    results = []
    for source in ALL_SCRAPERS:
        result = await test_scraper(source)
        results.append(result)
    
    # Summary
    muted = sum(1 for r in results if r.get('is_muted'))
    healthy = sum(1 for r in results if r.get('found') and not r.get('is_muted'))
    not_found = sum(1 for r in results if not r.get('found'))
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Healthy: {healthy} | Muted: {muted} | Not Found: {not_found}")
    
    return results


async def reset_scraper_failures(source_name: str) -> bool:
    """Reset failure count for a scraper (use after fixing issues)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScraperHealth).where(ScraperHealth.source_name == source_name)
        )
        health = result.scalar_one_or_none()
        
        if not health:
            print(f"❌ Scraper '{source_name}' not found")
            return False
        
        old_failures = health.consecutive_failures
        health.consecutive_failures = 0
        await db.commit()
        
        msg = f"✅ Reset failure count for '{source_name}' ({old_failures} → 0)"
        print(msg)
        return True


async def emergency_recovery():
    """Emergency recovery: unmute all and reset failure counts."""
    print("\n" + "="*80)
    print("EMERGENCY SCRAPER RECOVERY")
    print("="*80)
    
    # Step 1: Unmute all
    print("\n[1/3] Unmuting all scrapers...")
    unmuted = await unmute_all_scrapers(notify=False)
    
    # Step 2: Reset all failure counts
    print("\n[2/3] Resetting failure counts...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ScraperHealth))
        all_scrapers = result.scalars().all()
        
        reset_count = 0
        for scraper in all_scrapers:
            if scraper.consecutive_failures > 0:
                scraper.consecutive_failures = 0
                reset_count += 1
        
        await db.commit()
        print(f"  Reset {reset_count} scraper(s)")
    
    # Step 3: Send notification
    print("\n[3/3] Sending notification...")
    msg = (
        f"🚨 Emergency Recovery Executed\n"
        f"• Unmuted: {unmuted} scraper(s)\n"
        f"• Reset failures: {reset_count} scraper(s)\n"
        f"• Time: {datetime.now(timezone.utc).isoformat()}"
    )
    print(msg)
    try:
        await send_message(msg, parse_mode=None)
    except Exception as e:
        print(f"  Failed to send notification: {e}")
    
    print("\n" + "="*80)
    print("Recovery complete!")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Scraper Recovery & Management Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.scraper_recovery list
  python -m scripts.scraper_recovery unmute upwork
  python -m scripts.scraper_recovery test
  python -m scripts.scraper_recovery emergency
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # List command
    subparsers.add_parser('list', help='List all scraper statuses')
    
    # Unmute command
    unmute_parser = subparsers.add_parser('unmute', help='Unmute scraper(s)')
    unmute_parser.add_argument('source', nargs='?', help='Scraper name (omit for all)')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test scraper(s)')
    test_parser.add_argument('source', nargs='?', help='Scraper name (omit for all)')
    
    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset failure count')
    reset_parser.add_argument('source', help='Scraper name')
    
    # Emergency command
    subparsers.add_parser('emergency', help='Emergency recovery (unmute all, reset all)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    async def run():
        if args.command == 'list':
            await list_scraper_status()
        
        elif args.command == 'unmute':
            if args.source:
                await unmute_scraper_manual(args.source)
            else:
                await unmute_all_scrapers()
        
        elif args.command == 'test':
            if args.source:
                await test_scraper(args.source)
            else:
                await test_all_scrapers()
        
        elif args.command == 'reset':
            await reset_scraper_failures(args.source)
        
        elif args.command == 'emergency':
            confirm = input("⚠️  This will unmute ALL scrapers and reset ALL failure counts. Continue? [y/N]: ")
            if confirm.lower() == 'y':
                await emergency_recovery()
            else:
                print("Cancelled.")
    
    asyncio.run(run())


if __name__ == '__main__':
    main()
