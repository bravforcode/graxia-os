#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Personal OS & Thaolai — Production Smoke Test Suite
# Run this after every deploy to verify all critical paths are alive.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
  local name="$1"
  local result="$2"
  if [ "$result" = "0" ]; then
    echo -e "${GREEN}✓${NC} $name"
    ((PASS++))
  else
    echo -e "${RED}✗${NC} $name"
    ((FAIL++))
  fi
}

http_check() {
  local name="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$actual" = "$expected_status" ]; then
    check "$name [HTTP $actual]" "0"
  else
    check "$name [Expected $expected_status, Got $actual]" "1"
  fi
}

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Personal OS — Production Smoke Tests"
echo "═══════════════════════════════════════════════════════════"
echo ""

BRAVOS_HOST="${BRAVOS_HOST:-https://your-domain.com}"
THAOLAI_HOST="${THAOLAI_HOST:-https://thaolai.com}"

# ─── Personal OS Tests ───────────────────────────────────────────────────────
echo "--- Personal OS ($BRAVOS_HOST) ---"
http_check "Root health" "$BRAVOS_HOST/health" 200
http_check "API health" "$BRAVOS_HOST/api/v1/system/health" 200
http_check "Auth endpoint returns 422 (not 500)" "$BRAVOS_HOST/api/v1/auth/login" 422
http_check "Metrics endpoint (expect 401 or 200, not 500)" "$BRAVOS_HOST/metrics" 401
http_check "Frontend loads" "$BRAVOS_HOST/" 200

echo ""

# ─── Thaolai Tests ───────────────────────────────────────────────────────────
echo "--- Thaolai API ($THAOLAI_HOST) ---"
http_check "API version" "$THAOLAI_HOST/api/version" 200
http_check "Swagger docs" "$THAOLAI_HOST/service/api/docs" 200
http_check "Auth login returns 422 not 500" "$THAOLAI_HOST/service/api/v1/auth/login" 422
http_check "LINE webhook returns 400 (no signature = bad request not crash)" \
  "$THAOLAI_HOST/service/api/v1/line/webhook" 400

echo ""

# ─── Docker Container Health ─────────────────────────────────────────────────
if command -v docker &> /dev/null; then
  echo "--- Docker Container Health ---"

  for svc in backend worker-critical worker-default beat redis postgres; do
    status=$(docker compose -f docker-compose.prod.yml ps "$svc" 2>/dev/null | grep -o 'healthy\|running\|Up' | head -1 || echo "missing")
    if [ "$status" = "healthy" ] || [ "$status" = "Up" ] || [ "$status" = "running" ]; then
      check "Container: $svc ($status)" "0"
    else
      check "Container: $svc ($status)" "1"
    fi
  done
fi

echo ""

# ─── Env File Validation ─────────────────────────────────────────────────────
echo "--- Config Validation ---"

if grep -q "PASTE_" ".env.production" 2>/dev/null; then
  missing=$(grep "PASTE_" .env.production | wc -l)
  check "No PASTE_* placeholders in .env.production [$missing remaining]" "1"
else
  check "No PASTE_* placeholders in .env.production" "0"
fi

if grep -q "STRICT_BOOTSTRAP=true" ".env.production" 2>/dev/null; then
  check "STRICT_BOOTSTRAP=true is set" "0"
else
  check "STRICT_BOOTSTRAP=true is set" "1"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
