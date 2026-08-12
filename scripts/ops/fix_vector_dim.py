import asyncio
import asyncpg

async def fix():
    url = "postgresql://postgres.kxundnceeuyjfittlgvo:wqc3465768iyguhmEEW3254@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
    try:
        conn = await asyncpg.connect(url)
        print("🔗 Connected to Supabase.")
        
        print("🛠️ Resizing embedding column to 1536 dimensions...")
        # Postgres requires dropping the column or using a specific cast if we want to change vector size
        # Safest way for empty/new DB is to drop and recreate
        await conn.execute("ALTER TABLE knowledge_items DROP COLUMN IF EXISTS embedding")
        await conn.execute("ALTER TABLE knowledge_items ADD COLUMN embedding VECTOR(1536)")
        
        # Also check content_articles if it exists
        try:
            await conn.execute("ALTER TABLE content_articles DROP COLUMN IF EXISTS embedding")
            await conn.execute("ALTER TABLE content_articles ADD COLUMN embedding VECTOR(1536)")
        except:
            pass

        print("✅ Column resized successfully.")
        await conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(fix())
