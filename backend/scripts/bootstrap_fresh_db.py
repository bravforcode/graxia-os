"""Fresh-DB bootstrap: stamp alembic head + create_all from models."""
import asyncio
import os
import sys

os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://neondb_owner:npg_yFPCBGz9Dob4@ep-shiny-silence-a1xl2k6s-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require",
)
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("SECRET_KEY", "a1MZneLjJPD_LtsVFJE-a3Fb7nXbHHdKTEHJu98FvWPzb60duQof8AUxpv-lYjIM")
os.environ.setdefault("ENCRYPTION_KEY", "N6rEpXb5gCUHOTp8sX4puuR7JGu-Et-_DQUagdvQPQc")
os.environ.setdefault("CSRF_SECRET", "EpSCfpE6VXUEWbgHLRIUq1EL4CbH0fTpY1LITMBednY")
os.environ.setdefault("POSTGRES_PASSWORD", "a10a5ad8a831ca507aee2f928c03002baa8951e4324c5a0a")


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
