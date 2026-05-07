#!/usr/bin/env python3
"""
Graxia OS — Unified Database Migration
Creates all tables for Revenue OS + Quant OS in single database
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Import all models
from graxia.database import Base
from graxia.packages.revenue_os.models import *  # noqa
from graxia.packages.quant_os.data.models import *  # noqa


async def migrate():
    """Run unified migration"""
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/graxia")
    
    print("=" * 70)
    print("Graxia OS — Unified Database Migration")
    print("=" * 70)
    print(f"Database: {db_url}")
    print()
    
    engine = create_async_engine(db_url, echo=False)
    
    async with engine.begin() as conn:
        # Create all tables
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("✓ Tables created")
        
        # Verify
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        
        print()
        print(f"Total tables: {len(tables)}")
        print()
        
        # Categorize
        revenue_tables = [t for t in tables if t.startswith('revenue')]
        quant_tables = [t for t in tables if t.startswith('quant')]
        other_tables = [t for t in tables if not t.startswith(('revenue', 'quant'))]
        
        if revenue_tables:
            print("Revenue OS tables:")
            for t in revenue_tables:
                print(f"  ✓ {t}")
            print()
        
        if quant_tables:
            print("Quant OS tables:")
            for t in quant_tables:
                print(f"  ✓ {t}")
            print()
        
        if other_tables:
            print("Other tables:")
            for t in other_tables:
                print(f"  ✓ {t}")
            print()
        
        print("=" * 70)
        print("Migration complete!")
        print("=" * 70)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
