import sys
sys.path.insert(0, 'backend')
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.skillsmp_skill import SkillsMPSkill

async def main():
    async with AsyncSessionLocal() as db:
        # Test query like the API does
        result = await db.execute(
            select(SkillsMPSkill)
            .where(SkillsMPSkill.is_deleted_at_source == False)
            .limit(3)
        )
        skills = result.scalars().all()
        print(f"Found {len(skills)} skills")
        for s in skills:
            print(f"  - {s.name} ({s.source_type})")

if __name__ == "__main__":
    asyncio.run(main())
