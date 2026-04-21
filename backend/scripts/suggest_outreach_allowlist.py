import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    from app.database import AsyncSessionLocal
    from app.models.contact import Contact
    from sqlalchemy import desc, select

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Contact)
                    .where(Contact.is_deleted.is_(False))
                    .where(Contact.email.is_not(None))
                    .where(Contact.email != "")
                    .order_by(desc(Contact.value_score), Contact.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )

    emails = []
    domains = set()
    for row in rows:
        email = (row.email or "").strip().lower()
        if not email or "@" not in email:
            continue
        emails.append(email)
        domains.add(email.split("@")[-1])

    print("OUTREACH_ALLOWED_EMAILS=" + ",".join(emails[:50]))
    print("OUTREACH_ALLOWED_DOMAINS=" + ",".join(sorted(domains)))


if __name__ == "__main__":
    asyncio.run(main())
