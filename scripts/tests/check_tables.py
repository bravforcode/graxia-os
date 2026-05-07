import sys
sys.path.insert(0, 'backend')
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result.fetchall()]
        print("Tables:", tables)
        
        if 'skillsmp_skills' in tables:
            result = await db.execute(text("SELECT COUNT(*) FROM skillsmp_skills"))
            count = result.scalar()
            print(f"Skills count: {count}")
        else:
            print("skillsmp_skills table NOT FOUND!")

if __name__ == "__main__":
    asyncio.run(main())
