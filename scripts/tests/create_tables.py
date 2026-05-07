import sys
sys.path.insert(0, 'backend')
import asyncio
from app.database import engine
from app.models.base import Base
from app.models.skillsmp_skill import SkillsMPSkill, SkillLearningLog, SkillInvocation

async def main():
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created!")

if __name__ == "__main__":
    asyncio.run(main())
