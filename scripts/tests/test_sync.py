#!/usr/bin/env python3
"""Quick test for SkillsMP sync"""
import asyncio
import sys
sys.path.insert(0, 'backend')

from app.integrations.skillsmp_client import SkillsMPClient, SkillsMPConfig
from app.config import settings

async def test():
    print(f"API Key: {settings.SKILLSMP_API_KEY[:20]}...")
    print(f"Base URL: {settings.SKILLSMP_BASE_URL}")
    
    config = SkillsMPConfig(
        api_key=settings.SKILLSMP_API_KEY,
        base_url=settings.SKILLSMP_BASE_URL
    )
    
    async with SkillsMPClient(config) as client:
        print("\n🔍 Testing search...")
        skills, pagination = await client.search_skills("python", page=1, limit=5)
        print(f"✅ Found {len(skills)} skills (total: {pagination.total})")
        
        if skills:
            skill = skills[0]
            print(f"\n📌 First skill:")
            print(f"   ID: {skill.id}")
            print(f"   Name: {skill.name}")
            print(f"   Type: {skill.skill_type}")
            print(f"   Author: {skill.author}")
            print(f"   Stars: {skill.stars}")
        
        print("\n🔄 Testing fetch_all_skills (limited)...")
        all_skills = await client.fetch_all_skills(max_pages=1, per_page=10)
        print(f"✅ Fetched {len(all_skills)} unique skills")
        
        # Group by type
        by_type = {}
        for s in all_skills:
            t = s.skill_type or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
        
        print("\n📊 By type:")
        for t, c in sorted(by_type.items(), key=lambda x: -x[1])[:5]:
            print(f"   {t}: {c}")

if __name__ == "__main__":
    asyncio.run(test())
