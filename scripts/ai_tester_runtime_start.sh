#!/usr/bin/env bash
# Phase 22.5 — AI Tester Safe Runtime Start
# Usage: bash scripts/ai_tester_runtime_start.sh [--dry-run] [--check-only]

DRY_RUN=false
CHECK_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --check-only) CHECK_ONLY=true ;;
  esac
done

echo "=== AI Tester Runtime Start ==="
echo "Mode: dry-run=$DRY_RUN check-only=$CHECK_ONLY"
echo ""

# Backend
BACKEND_CMD="cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning"
if $CHECK_ONLY; then
  echo "[CHECK] Backend command: $BACKEND_CMD"
  if command -v curl &> /dev/null; then
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null && echo " — Backend is running" || echo " — Backend is not running"
  else
    echo " — curl not available for health check"
  fi
elif $DRY_RUN; then
  echo "[DRY-RUN] Would execute: $BACKEND_CMD"
else
  echo "[START] Starting backend..."
  eval "$BACKEND_CMD &"
  echo "Backend PID: $!"
fi

# Frontend
FRONTEND_CMD="cd frontend && bun run dev --port 5173"
if $CHECK_ONLY; then
  echo "[CHECK] Frontend command: $FRONTEND_CMD"
  if command -v curl &> /dev/null; then
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173 2>/dev/null && echo " — Frontend is running" || echo " — Frontend is not running"
  else
    echo " — curl not available for health check"
  fi
elif $DRY_RUN; then
  echo "[DRY-RUN] Would execute: $FRONTEND_CMD"
else
  echo "[START] Starting frontend..."
  cd frontend && bun run dev --port 5173 &
  echo "Frontend PID: $!"
fi

echo ""
echo "=== Done ==="
