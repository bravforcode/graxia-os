import sys
sys.path.insert(0, 'backend')
import asyncio
from app.integrations.skillsmp_client import SkillsMPClient, SkillsMPConfig
from app.config import settings

async def main():
    print(f"API Key: {settings.SKILLSMP_API_KEY[:25]}...")
    print(f"Base URL: {settings.SKILLSMP_BASE_URL}")
    
    config = SkillsMPConfig(api_key=settings.SKILLSMP_API_KEY)
    
    async with SkillsMPClient(config) as client:
        print("\n🔍 Searching 'python'...")
        skills, pag = await client.search_skills("python", limit=3)
        print(f"✅ Found {len(skills)} skills (total: {pag.total})")
        for s in skills[:2]:
            print(f"  - {s.name} ({s.skill_type})")

if __name__ == "__main__":
    asyncio.run(main())
