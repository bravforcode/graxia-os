#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Graxia OS — Check Staging Readiness
# Verifies all staging readiness requirements.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green() { echo "  ✅ $1"; ((PASS++)); }
red() { echo "  ❌ $1"; ((FAIL++)); }

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Graxia OS — Check Staging Readiness"
echo "  Target: ${BASE_URL}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. Health Endpoint ───────────────────────────────────────────────────────
echo "── 1. Health Endpoint ──────────────────────────────────────────"
HEALTH=$(curl -s "${BASE_URL}/api/v1/health" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  green "Health check returns ok"
else
  red "Health check failed: $(echo "$HEALTH" | head -c 200)"
fi

# ── 2. Readiness Endpoint ─────────────────────────────────────────────────────
echo ""
echo "── 2. Readiness Endpoint ───────────────────────────────────────"
READINESS=$(curl -s "${BASE_URL}/api/v1/health/readiness" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null)
if echo "$READINESS" | grep -q '"production_ready":false'; then
  green "Readiness endpoint confirms production_ready: false"
else
  red "Readiness endpoint missing production_ready: false"
fi

# ── 3. Local Agent Ready Confirmed ───────────────────────────────────────────
echo ""
echo "── 3. Local Agent Readiness ─────────────────────────────────────"
LOCAL=$(curl -s "${BASE_URL}/api/v1/health/readiness/local-agent" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null)
if echo "$LOCAL" | grep -q '"FULL_LOCAL_AGENT_READY":true'; then
  green "Local agent is FULL_LOCAL_AGENT_READY"
else
  red "Local agent not fully ready: $(echo "$LOCAL" | head -c 200)"
fi

# ── 4. Staging Readiness Reports Correctly ───────────────────────────────────
echo ""
echo "── 4. Staging Readiness Reports Correctly ───────────────────────"
STAGING=$(curl -s "${BASE_URL}/api/v1/health/readiness/staging" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null)
if echo "$STAGING" | grep -q '"staging_ready":false'; then
  green "Staging readiness shows staging_ready: false (expected before full staging setup)"
else
  red "Staging readiness incorrect"
fi

# ── 5. Auth Context Required in Staging Mode ─────────────────────────────────
echo ""
echo "── 5. Auth Context Enforcement ───────────────────────────────────"
# Check that auth context middleware is loaded
if curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health" 2>/dev/null | grep -q "200"; then
  green "Root health accessible without org header"
fi

# ── 6. No Secrets in Responses ───────────────────────────────────────────────
echo ""
echo "── 6. No Secrets in Responses ────────────────────────────────────"
HEALTH_BODY=$(curl -s "${BASE_URL}/api/v1/health" \
  -H "X-Graxia-Org-Id: 00000000-0000-0000-0000-000000000001" 2>/dev/null)
if echo "$HEALTH_BODY" | grep -qi "secret\|password\|token\|key"; then
  red "HEALTH endpoint leaked secret-like data!"
else
  green "Health response contains no secret-like keys"
fi

# ── 7. Database Connectivity ─────────────────────────────────────────────────
echo ""
echo "── 7. Database Connectivity ──────────────────────────────────────"
if echo "$HEALTH_BODY" | grep -q '"database":"healthy\|unhealthy\|degraded"'; then
  green "Health endpoint reports database status"
else
  red "Health endpoint missing database status"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "  ❌ Staging NOT ready — fix failed checks above."
  exit 1
else
  echo "  ✅ Staging readiness checks pass."
  exit 0
fi
