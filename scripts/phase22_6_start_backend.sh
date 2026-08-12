#!/bin/bash
# Phase 22.6 — Safe backend runtime starter
# Starts uvicorn with inline env overrides (no .env)

set -e

cd "$(dirname "$0")/../backend"

export SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f"
export ENCRYPTION_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
export POSTGRES_PASSWORD="a1b2c3d4e5f6g7h8"
export DATABASE_URL="sqlite+aiosqlite:///./test_runtime.db"
export APP_ENV="development"
export ALLOW_LIVE_STRIPE="false"
export ALLOW_REAL_EMAIL_SEND="false"
export ALLOW_REAL_GOOGLE_MUTATION="false"
export ALLOW_REAL_LLM_CALLS="false"
export ALLOW_PRODUCTION_DB="false"
export NO_LIVE_PAYMENT_MODE="true"
export KILL_SWITCH_ALL_EXTERNAL_BETA="true"
export BETA_ENABLED="false"
export PRODUCTION_READY="false"
export REDIS_URL="redis://localhost:6379/0"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/2"

echo "Starting backend with safe runtime profile..."
echo "Database: sqlite+aiosqlite:///./test_runtime.db"
echo "Port: 8000"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
