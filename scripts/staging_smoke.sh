#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Graxia OS — Staging Smoke Test (Phase 17)
# Run this against a deployed staging environment to verify basic health,
# security boundaries, MCP, and readiness gates.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green() { echo "  ✅ $1"; ((PASS++)); }
red() { echo "  ❌ $1"; ((FAIL++)); }

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Graxia OS — Staging Smoke Test (Phase 17)"
echo "  Target: ${BASE_URL}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. Health Check ──────────────────────────────────────────────────────────
echo "── Health Check ──────────────────────────────────────────────"

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
  green "GET /api/v1/health → 200"
else
  red "GET /api/v1/health → ${HEALTH} (expected 200)"
fi

# ── 2. Readiness Check ────────────────────────────────────────────────────────
echo ""
echo "── Readiness Check ───────────────────────────────────────────"

READINESS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health/readiness" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$READINESS" = "200" ]; then
  green "GET /api/v1/health/readiness → 200"
else
  red "GET /api/v1/health/readiness → ${READINESS} (expected 200)"
fi

# ── 3. Local Agent Readiness ──────────────────────────────────────────────────
echo ""
echo "── Local Agent Readiness ─────────────────────────────────────"

LOCAL_AGENT=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health/readiness/local-agent" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$LOCAL_AGENT" = "200" ]; then
  green "GET /api/v1/health/readiness/local-agent → 200"
else
  red "GET /api/v1/health/readiness/local-agent → ${LOCAL_AGENT} (expected 200)"
fi

# ── 4. Staging Readiness ──────────────────────────────────────────────────────
echo ""
echo "── Staging Readiness ────────────────────────────────────────"

STAGING=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health/readiness/staging" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$STAGING" = "200" ]; then
  green "GET /api/v1/health/readiness/staging → 200"
  STAGING_BODY=$(curl -s "${BASE_URL}/api/v1/health/readiness/staging" \
    -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "{}")
  if echo "$STAGING_BODY" | grep -q '"production_live_providers_disabled":true'; then
    green "  └─ production_live_providers_disabled = true"
  else
    red "  └─ production_live_providers_disabled = true (expected true)"
  fi
  if echo "$STAGING_BODY" | grep -q '"staging_ready":false'; then
    green "  └─ staging_ready = false (expected in test env)"
  else
    red "  └─ staging_ready = false (expected false)"
  fi
else
  red "GET /api/v1/health/readiness/staging → ${STAGING} (expected 200)"
fi

# ── 5. Production Readiness ───────────────────────────────────────────────────
echo ""
echo "── Production Readiness ─────────────────────────────────────"

PROD=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health/readiness/production" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$PROD" = "200" ]; then
  green "GET /api/v1/health/readiness/production → 200"
  PROD_BODY=$(curl -s "${BASE_URL}/api/v1/health/readiness/production" \
    -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "{}")
  if echo "$PROD_BODY" | grep -q '"production_ready":false'; then
    green "  └─ production_ready = false (gate closed)"
  else
    red "  └─ production_ready = false (expected false)"
  fi
else
  red "GET /api/v1/health/readiness/production → ${PROD} (expected 200)"
fi

# ── 6. Root Health ───────────────────────────────────────────────────────────
echo ""
echo "── Root Health ───────────────────────────────────────────────"

ROOT=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health" 2>/dev/null || echo "000")
if [ "$ROOT" = "200" ]; then
  green "GET /health → 200"
else
  red "GET /health → ${ROOT} (expected 200)"
fi

# ── 7. Auth Context (Missing org header) ──────────────────────────────────────
echo ""
echo "── Auth Context (Missing org header) ─────────────────────────"

NO_ORG=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/health/readiness" 2>/dev/null || echo "000")
if [ "$NO_ORG" = "401" ] || [ "$NO_ORG" = "403" ]; then
  green "Missing X-Graxia-Org-Id → ${NO_ORG} (rejected, expected)"
else
  red "Missing X-Graxia-Org-Id → ${NO_ORG} (expected 401 or 403)"
fi

# ── 8. Auth-Required Route Denies Anonymous ──────────────────────────────────
echo ""
echo "── Auth-Required Route (anonymous) ───────────────────────────"

AUTH_REQUIRED=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/contacts" 2>/dev/null || echo "000")
if [ "$AUTH_REQUIRED" = "401" ] || [ "$AUTH_REQUIRED" = "403" ]; then
  green "GET /api/v1/contacts (anonymous) → ${AUTH_REQUIRED} (rejected, expected)"
else
  red "GET /api/v1/contacts (anonymous) → ${AUTH_REQUIRED} (expected 401 or 403)"
fi

# ── 9. Safe Error Contract (404) ──────────────────────────────────────────────
echo ""
echo "── Safe Error Contract ───────────────────────────────────────"

NOT_FOUND_BODY=$(curl -s "${BASE_URL}/api/v1/nonexistent-route" 2>/dev/null || echo "{}")
if echo "$NOT_FOUND_BODY" | grep -q '"code"'; then
  green "  └─ 404 returns error envelope"
  if echo "$NOT_FOUND_BODY" | grep -q 'stack'; then
    red "  └─ ERROR: stack trace leaked in 404 response"
  else
    green "  └─ No stack trace in 404 response"
  fi
  if echo "$NOT_FOUND_BODY" | grep -q '"request_id"'; then
    green "  └─ request_id present in error envelope"
  else
    red "  └─ request_id missing in error envelope"
  fi
else
  red "404 response missing error envelope"
fi

# ── 10. MCP Tools List ───────────────────────────────────────────────────────
echo ""
echo "── MCP Tools ─────────────────────────────────────────────────"

MCP_TOOLS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/mcp/tools/list" \
  -H "Content-Type: application/json" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null || echo "000")
if [ "$MCP_TOOLS" = "200" ]; then
  green "POST /api/v1/mcp/tools/list → 200"
else
  red "POST /api/v1/mcp/tools/list → ${MCP_TOOLS} (expected 200)"
fi

# ── 11. MCP System Status ────────────────────────────────────────────────────
echo ""
echo "── MCP System Status ────────────────────────────────────────"

SYS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/mcp/tools/call" \
  -H "Content-Type: application/json" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_system_status","arguments":{}}}' 2>/dev/null || echo "000")
if [ "$SYS_STATUS" = "200" ]; then
  green "POST /api/v1/mcp/tools/call (get_system_status) → 200"
else
  red "POST /api/v1/mcp/tools/call (get_system_status) → ${SYS_STATUS} (expected 200)"
fi

# ── 12. Funnel Analytics ─────────────────────────────────────────────────────
echo ""
echo "── Funnel Analytics ──────────────────────────────────────────"

ANALYTICS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/funnel/analytics/summary" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null || echo "000")
if [ "$ANALYTICS" = "200" ]; then
  green "GET /api/v1/funnel/analytics/summary → 200"
else
  red "GET /api/v1/funnel/analytics/summary → ${ANALYTICS} (expected 200)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
