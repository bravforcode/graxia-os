import sys
sys.path.insert(0, 'backend')
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM skillsmp_skills"))
        count = result.scalar()
        print(f"Total skills in database: {count}")
        
        result = await db.execute(text("SELECT source_type, COUNT(*) FROM skillsmp_skills GROUP BY source_type"))
        rows = result.fetchall()
        print("\nBy type:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")

if __name__ == "__main__":
    asyncio.run(main())
