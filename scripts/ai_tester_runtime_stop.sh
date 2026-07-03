#!/usr/bin/env bash
# Phase 22.5 — AI Tester Safe Runtime Stop
# Usage: bash scripts/ai_tester_runtime_stop.sh [--dry-run]

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in --dry-run) DRY_RUN=true ;; esac
done

echo "=== AI Tester Runtime Stop ==="

# Find and kill backend
BACKEND_PID=$(pgrep -f "uvicorn app.main:app" 2>/dev/null || true)
if [ -n "$BACKEND_PID" ]; then
  if $DRY_RUN; then
    echo "[DRY-RUN] Would kill backend PID: $BACKEND_PID"
  else
    echo "[STOP] Stopping backend (PID: $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
    echo "Backend stopped."
  fi
else
  echo "[INFO] Backend not running."
fi

# Find and kill frontend
FRONTEND_PID=$(pgrep -f "bun run dev" 2>/dev/null || true)
if [ -n "$FRONTEND_PID" ]; then
  if $DRY_RUN; then
    echo "[DRY-RUN] Would kill frontend PID: $FRONTEND_PID"
  else
    echo "[STOP] Stopping frontend (PID: $FRONTEND_PID)..."
    kill "$FRONTEND_PID" 2>/dev/null || true
    echo "Frontend stopped."
  fi
else
  echo "[INFO] Frontend not running."
fi

echo "=== Done ==="
