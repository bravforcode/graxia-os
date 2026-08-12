"""Fresh-DB bootstrap: stamp alembic head + create_all from models.

Secrets come from the environment (or .env.production via python-dotenv).
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env.production"))

REQUIRED = ("DATABASE_URL", "SECRET_KEY", "ENCRYPTION_KEY", "CSRF_SECRET", "POSTGRES_PASSWORD")
missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    print(f"Missing env vars: {missing} — set them or create .env.production")
    sys.exit(1)


async def main() -> None:
    from sqlalchemy import text

    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    os.chdir(backend_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # alembic env.py calls asyncio.run() — must run in a SEPARATE process.
    import subprocess

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    print(r.stdout[-500:])
    if r.returncode != 0:
        print("STAMP FAILED:", r.stderr[-500:])
        raise SystemExit(1)
    print("STAMPED at head")

    import app.models  # noqa: F401  (register all models)
    from app.database import engine
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("CREATE_ALL DONE")

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename LIKE 'funnel%'"
                )
            )
        ).scalars().all()
        print("funnel tables:", sorted(rows))


if __name__ == "__main__":
    asyncio.run(main())
