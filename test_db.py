import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test_db():
    load_dotenv('C:/Users/menum/graxia os/.env.production')
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FAIL: DATABASE_URL not found in .env.production")
        return

    # Normalize driver for asyncpg
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Testing DB: {db_url.split('@')[-1]}") # Print host only for security
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(f"SUCCESS: Ping result {result.scalar()}")
        await engine.dispose()
    except Exception as e:
        print(f"FAIL: {e}")

if __name__ == "__main__":
    asyncio.run(test_db())
