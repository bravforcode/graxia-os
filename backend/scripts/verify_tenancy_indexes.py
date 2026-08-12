import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

TENANT_TABLES = [
    "users", "usage_logs", "contacts", "opportunities", "content_drafts",
    "approval_requests", "automation_runs", "job_postings", "submissions",
    "email_threads", "agents", "agent_teams", "audit_logs", "openclaw_usage",
    "workflows"
]

async def verify_indexes():
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    engine = create_async_engine(db_url)
    
    query = """
    SELECT indexname 
    FROM pg_indexes 
    WHERE tablename = :table_name;
    """
    
    missing = []
    
    async with engine.connect() as conn:
        for table in TENANT_TABLES:
            result = await conn.execute(text(query), {"table_name": table})
            indexes = [row[0] for row in result.fetchall()]
            
            # Check for (org_id, id)
            if f"ix_{table}_org_id_id" not in indexes:
                missing.append(f"ix_{table}_org_id_id")
            
            # Check for (org_id, ts)
            ts_col = "found_at" if table == "opportunities" else "created_at"
            if f"ix_{table}_org_id_{ts_col}" not in indexes:
                missing.append(f"ix_{table}_org_id_{ts_col}")
                
    await engine.dispose()
    
    if missing:
        print(f"FAILED: Missing {len(missing)} tenancy indexes:")
        for m in missing:
            print(f" - {m}")
        return False
    else:
        print("SUCCESS: All 30 tenancy performance indexes verified.")
        return True

if __name__ == "__main__":
    if asyncio.run(verify_indexes()):
        sys.exit(0)
    else:
        sys.exit(1)
