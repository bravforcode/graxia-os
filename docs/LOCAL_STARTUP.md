# Local Startup

## Prerequisites

- Python 3.11+ or 3.12.
- Bun.
- Docker Compose for PostgreSQL and Redis.

## Environment

```bash
cp .env.example .env
```

Set local development values:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/personal_os
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-32-byte-compatible-key
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
APP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
```

## Start

```bash
make infra-up
make migrate-local
make run-local
```

In another terminal:

```bash
make frontend-dev
```

Open `http://localhost:5173` for the React UI and `http://localhost:8000/docs` for API docs.

## Verify

```bash
cd backend
python -c "from app.main import app; print(app.title)"
python scripts/alembic_safe.py heads
python -m pytest tests -q
```

```bash
cd frontend
bun run lint
bun run build
```
