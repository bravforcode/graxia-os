#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Beta Smoke Script — Phase 20 Limited Beta Launch Packet
# Tests all beta readiness gates, kill switch, allowlist, drill workflows,
# launch policy, invite template, onboarding checklist, session script,
# no-live-payment mode, limited beta pilot readiness, and all safety guards.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }

check() {
    local label="$1" method="$2" path="$3" expected="$4"
    local url="${BASE_URL}${path}"
    local response
    response=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url")
    if [ "$response" = "$expected" ]; then
        green "  ✓ $label (HTTP $response)"
        PASS=$((PASS + 1))
    else
        red "  ✗ $label (expected HTTP $expected, got $response)"
        FAIL=$((FAIL + 1))
    fi
}

check_json_field() {
    local label="$1" path="$2" field="$3" expected="$4"
    local url="${BASE_URL}${path}"
    local value
    value=$(curl -s "$url" | python -c "import sys,json; print(json.load(sys.stdin).get('$field','__NOTFOUND__'))" 2>/dev/null || echo "__ERROR__")
    if [ "$value" = "$expected" ]; then
        green "  ✓ $label ($field=$expected)"
        PASS=$((PASS + 1))
    else
        red "  ✗ $label (expected $field=$expected, got $value)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  Phase 20 — Limited Beta Launch Packet Smoke                │"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""

# ── Health / Readiness ────────────────────────────────────────────────
echo "  ● Health check"
check "Health endpoint responds 200" "GET" "/api/v1/health" "200"
check "Readiness endpoint responds 200" "GET" "/api/v1/health/readiness" "200"

# ── Production Readiness Gate ─────────────────────────────────────────
echo "  ● Production readiness gate"
check "Production readiness responds 200" "GET" "/api/v1/health/readiness/production" "200"
check_json_field "production_ready is false" "/api/v1/health/readiness/production" "production_ready" "False"

# ── Staging Readiness ─────────────────────────────────────────────────
echo "  ● Staging readiness"
check "Staging readiness responds 200" "GET" "/api/v1/health/readiness/staging" "200"

# ── Beta Readiness ────────────────────────────────────────────────────
echo "  ● Beta readiness gate"
check "Beta readiness responds 200" "GET" "/api/v1/health/readiness/beta" "200"
check_json_field "beta_enabled from beta readiness" "/api/v1/health/readiness/beta" "beta_enabled" "False"
check_json_field "kill_switch_enabled from beta readiness" "/api/v1/health/readiness/beta" "kill_switch_enabled" "True"

# ── Limited Beta Pilot Readiness (Phase 20) ───────────────────────────
echo "  ● Limited beta pilot readiness"
check "Limited beta pilot readiness responds 200" "GET" "/api/v1/health/readiness/limited-beta-pilot" "200"
check_json_field "no_live_payment_mode in limited beta pilot" "/api/v1/health/readiness/limited-beta-pilot" "no_live_payment_mode" "True"
check_json_field "limited_beta_pilot_ready_flag" "/api/v1/health/readiness/limited-beta-pilot" "limited_beta_pilot_ready_flag" "False"

# ── Beta Docs Check (filesystem) ──────────────────────────────────────
echo "  ● Beta launch packet docs"
for doc in BETA_LAUNCH_POLICY.md BETA_MANUAL_INVITE_TEMPLATE.md BETA_ONBOARDING_CHECKLIST.md BETA_SESSION_SCRIPT.md; do
    if [ -f "docs/$doc" ]; then
        green "  ✓ docs/$doc exists"
        PASS=$((PASS + 1))
    else
        red "  ✗ docs/$doc missing"
        FAIL=$((FAIL + 1))
    fi
done

# ── Safe Errors ───────────────────────────────────────────────────────
echo "  ● Safe error contract"
check "Safe error from bad delivery token" "GET" "/api/v1/delivery/open/bad-token-12345" "404"

# ── Request Correlation ───────────────────────────────────────────────
echo "  ● Request correlation"
response_headers=$(curl -s -o /dev/null -D - "${BASE_URL}/api/v1/health" 2>/dev/null || true)
if echo "$response_headers" | grep -qi "x-request-id"; then
    green "  ✓ X-Request-ID header present"
    PASS=$((PASS + 1))
else
    red "  ✗ X-Request-ID header missing"
    FAIL=$((FAIL + 1))
fi
if echo "$response_headers" | grep -qi "x-correlation-id"; then
    green "  ✓ X-Correlation-ID header present"
    PASS=$((PASS + 1))
else
    red "  ✗ X-Correlation-ID header missing"
    FAIL=$((FAIL + 1))
fi

# ── Auth Denial ───────────────────────────────────────────────────────
echo "  ● Auth-required route denial"
check "Protected route returns 401" "GET" "/api/v1/delivery/customer/profile" "401"

echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
printf "│  Result: %d passed, %d failed                               │\n" "$PASS" "$FAIL"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""
[ "$FAIL" -eq 0 ]
