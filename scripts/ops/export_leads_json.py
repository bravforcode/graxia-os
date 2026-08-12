import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import asyncio

    out_path = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) >= 2
        else Path("data/leads_export.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def run() -> list[dict]:
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from sqlalchemy import desc, select

        async with AsyncSessionLocal() as db:
            rows = list(
                (
                    await db.execute(
                        select(Contact)
                        .where(Contact.is_deleted.is_(False))
                        .where(Contact.contact_type == "lead")
                        .where(Contact.email.is_not(None))
                        .where(Contact.email != "")
                        .order_by(desc(Contact.value_score), Contact.created_at.desc())
                        .limit(5000)
                    )
                )
                .scalars()
                .all()
            )
        items = []
        for row in rows:
            items.append(
                {
                    "name": row.name,
                    "email": row.email,
                    "company": row.company,
                    "role": row.role,
                    "source": "contacts",
                    "value_score": row.value_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return items

    items = asyncio.run(run())
    payload = {"generated_at": datetime.now(UTC).isoformat(), "items": items}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
