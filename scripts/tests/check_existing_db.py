import sys
sys.path.insert(0, 'backend')
import asyncio
import aiosqlite

async def check_db(path, name):
    try:
        async with aiosqlite.connect(path) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in await cursor.fetchall()]
            
            if 'skillsmp_skills' in tables:
                cursor = await db.execute("SELECT COUNT(*) FROM skillsmp_skills")
                count = (await cursor.fetchone())[0]
                print(f"{name}: ✅ {count} skills")
                return True, count
            else:
                print(f"{name}: ❌ no skillsmp_skills table")
                return False, 0
    except Exception as e:
        print(f"{name}: ❌ error - {e}")
        return False, 0

async def main():
    dbs = [
        ("backend/personal_os_local.db", "personal_os_local.db"),
        ("backend/graxia_os_production.db", "graxia_os_production.db"),
        ("graxia_dev.db", "graxia_dev.db"),
    ]
    
    for path, name in dbs:
        await check_db(path, name)

if __name__ == "__main__":
    asyncio.run(main())
