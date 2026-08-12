#!/usr/bin/env bash
# Phase 22.5 — AI Tester Safe Runtime Check
# Usage: bash scripts/ai_tester_runtime_check.sh

echo "=== AI Tester Runtime Check ==="
echo ""

# Backend health
if command -v curl &> /dev/null; then
  echo "[Backend] Checking http://127.0.0.1:8000/health..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "  Status: RUNNING (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" = "000" ]; then
    echo "  Status: NOT RUNNING"
  else
    echo "  Status: UNEXPECTED (HTTP $HTTP_CODE)"
  fi

  # Frontend check
  echo ""
  echo "[Frontend] Checking http://127.0.0.1:5173..."
  FE_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173 2>/dev/null || echo "000")
  if [ "$FE_CODE" = "200" ]; then
    echo "  Status: RUNNING (HTTP $FE_CODE)"
  elif [ "$FE_CODE" = "000" ]; then
    echo "  Status: NOT RUNNING"
  else
    echo "  Status: UNEXPECTED (HTTP $FE_CODE)"
  fi

  # Readiness production check
  echo ""
  echo "[Readiness] Checking production readiness..."
  RESPONSE=$(curl -s http://127.0.0.1:8000/readiness/production 2>/dev/null || echo "BACKEND_NOT_RUNNING")
  echo "  Response: $RESPONSE"
else
  echo "[INFO] curl not available. Cannot check runtime."
  echo "  Backend would be at: http://127.0.0.1:8000"
  echo "  Frontend would be at: http://127.0.0.1:5173"
fi

echo ""
echo "=== Check Complete ==="
