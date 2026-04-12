# Troubleshooting

## Backend Import Hangs On Windows

The backend installs a Windows platform guard in `app/__init__.py` because Python 3.12 can route `platform.uname()` and `platform.machine()` through a slow WMI query during SQLAlchemy or asyncpg import.

Verify:

```bash
cd backend
python -c "from app.main import app; print(app.title)"
```

## Migrations

Verify the resettable baseline head:

```bash
cd backend
python scripts/alembic_safe.py heads
```

Expected head:

```text
001_enterprise_baseline (head)
```

## API Contract Tests

Run:

```bash
cd backend
python -m pytest tests -q
```

The active suite lives in `backend/tests/`. Legacy generated tests were preserved in `backend/tests_legacy/` and should be rewritten before being used as acceptance criteria.

## Frontend Build

Run:

```bash
cd frontend
bun run lint
bun run build
```

If API calls fail in Docker Compose, check `VITE_DEV_PROXY_TARGET`. In Compose it should point to `http://backend:8000`, not `localhost`.
