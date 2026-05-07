import sys
sys.path.insert(0, 'backend')
import asyncio
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models.skillsmp_skill import SkillsMPSkill
from app.schemas.skillsmp import SkillsMPSkillOut
from decimal import Decimal

async def main():
    async with AsyncSessionLocal() as db:
        # Query like the API does
        query = select(SkillsMPSkill).where(SkillsMPSkill.is_deleted_at_source == False)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)
        print(f"Total: {total}")
        
        # Get skills
        query = query.limit(2)
        result = await db.execute(query)
        skills = result.scalars().all()
        print(f"Skills count: {len(skills)}")
        
        # Try converting to schema
        for skill in skills:
            print(f"\nSkill: {skill.name}")
            try:
                out = SkillsMPSkillOut.from_orm(skill)
                print(f"  Converted OK: {out.name}")
            except Exception as e:
                print(f"  Error: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
