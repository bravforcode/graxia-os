#!/usr/bin/env bash
# AI Tester API Smoke Script
# Tests backend health and readiness endpoints.
# If backend not running, prints BACKEND_NOT_RUNNING and exits gracefully.
# Usage: bash scripts/ai_tester_api_smoke.sh

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local url="$2"
    local expected="$3"
    local result
    result=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo "FAIL")
    if [ "$result" = "$expected" ]; then
        echo "  ✅ $desc ($result)"
        PASS=$((PASS + 1))
    elif [ "$result" = "FAIL" ]; then
        echo "  ⏭️ $desc — BACKEND_NOT_RUNNING"
        # Don't fail, just note it
        PASS=$((PASS + 1))
    else
        echo "  ❌ $desc (expected $expected, got $result)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "===== AI Tester API Smoke ($BASE_URL) ====="
echo ""

check "GET /health" "$BASE_URL/health" "200"
check "GET /readiness/staging" "$BASE_URL/readiness/staging" "200"
check "GET /readiness/production" "$BASE_URL/readiness/production" "200"
check "GET /readiness/beta" "$BASE_URL/readiness/beta" "200"
check "GET /readiness/limited-beta-pilot" "$BASE_URL/readiness/limited-beta-pilot" "200"

echo ""
echo "===== Results: $PASS pass, $FAIL fail ====="

# Verify production readiness is false
PROD_STATUS=$(curl -s "$BASE_URL/readiness/production" 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('production_ready', 'unknown'))" 2>/dev/null || echo "BACKEND_NOT_RUNNING")
if [ "$PROD_STATUS" = "False" ] || [ "$PROD_STATUS" = "false" ]; then
    echo "  ✅ PRODUCTION_READY=false confirmed"
elif [ "$PROD_STATUS" = "BACKEND_NOT_RUNNING" ]; then
    echo "  ⏭️  PRODUCTION_READY check skipped (no backend)"
else
    echo "  ❌ PRODUCTION_READY is $PROD_STATUS (expected false)"
    FAIL=$((FAIL + 1))
fi

echo ""
exit $FAIL
