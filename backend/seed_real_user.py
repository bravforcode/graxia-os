import asyncio
import os
from uuid import uuid4
from datetime import datetime, UTC
from sqlalchemy import select

# Fix path
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from app.models.user import User
from app.models.organization import Organization
from app.core.auth import get_password_hash
from app.database import AsyncSessionLocal

async def seed():
    email = "real-test@graxia.io"
    password = "RealPassword123!"
    
    print(f"🚀 Seeding real user: {email}...")
    
    async with AsyncSessionLocal() as db:
        # Check if user exists
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print("✅ User already exists.")
            return

        # Ensure an organization exists
        org_result = await db.execute(select(Organization).limit(1))
        org = org_result.scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid4(),
                name="Testing Org",
                slug="testing-org",
                status="active"
            )
            db.add(org)
            await db.flush()

        user = User(
            id=uuid4(),
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Real Tester",
            role="admin",
            is_active=True,
            organization_id=org.id,
            created_at=datetime.now(UTC)
        )
        db.add(user)
        await db.commit()
        print("✅ Real User Created Successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
