@echo off
echo Starting Gracia OS Staging API...

set ENVIRONMENT=staging
set DEBUG=true
set LOG_LEVEL=INFO
set HOST=0.0.0.0
set PORT=8001
set DATABASE_URL=sqlite+aiosqlite:///../staging-run/staging.db
set REDIS_URL=redis://localhost:6379/0
set CELERY_BROKER_URL=redis://localhost:6379/1
set CELERY_RESULT_BACKEND=redis://localhost:6379/2

cd backend
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8001 --reload
