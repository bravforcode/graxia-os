import asyncio
import asyncpg

async def clear_data():
    url = "postgresql://postgres.kxundnceeuyjfittlgvo:wqc3465768iyguhmEEW3254@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
    try:
        conn = await asyncpg.connect(url)
        print("🔗 Connected to Supabase for cleanup.")
        
        # List of tables to clear
        tables = [
            'contacts',
            'job_postings',
            'agent_messages',
            'agent_collaboration_messages',
            'audit_log',
            'knowledge_items',
            'content_drafts'
        ]
        
        for table in tables:
            try:
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
                print(f"🧹 Cleared table: {table}")
            except Exception as e:
                print(f"⚠️ Could not clear {table}: {e}")
        
        await conn.close()
        print("✅ Cleanup complete.")
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")

if __name__ == "__main__":
    asyncio.run(clear_data())
