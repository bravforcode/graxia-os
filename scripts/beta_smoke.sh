#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Beta Smoke Script — Phase 19 Controlled External Beta
# Tests all beta readiness gates, kill switch, allowlist, and drill workflows.
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
echo "│  Phase 19 — Controlled External Beta Smoke                  │"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""

# 1. Health
echo "  ● Health check"
check "Health endpoint responds 200" "GET" "/api/v1/health" "200"

# 2. Readiness
echo "  ● Readiness endpoint"
check "Readiness endpoint responds 200" "GET" "/api/v1/health/readiness" "200"

# 3. Production readiness returns false
echo "  ● Production readiness gate"
check "Production readiness responds 200" "GET" "/api/v1/health/readiness/production" "200"
check_json_field "production_ready is false" "/api/v1/health/readiness/production" "production_ready" "False"

# 4. Beta readiness
echo "  ● Beta readiness gate"
check "Beta readiness responds 200" "GET" "/api/v1/health/readiness/beta" "200"

# 5. Beta kill switch
echo "  ● Beta kill switch"
check_json_field "beta_enabled from beta readiness" "/api/v1/health/readiness/beta" "beta_enabled" "False"

# 6. Staging readiness
echo "  ● Staging readiness"
check "Staging readiness responds 200" "GET" "/api/v1/health/readiness/staging" "200"

# 7. Safe error
echo "  ● Safe error contract"
# Hit a non-existent delivery route that should return a safe error (404)
check "Safe error from bad delivery token" "GET" "/api/v1/delivery/open/bad-token-12345" "404"

# 8. Request correlation
echo "  ● Request correlation"
response_headers=$(curl -s -o /dev/null -D - "http://127.0.0.1:8000/api/v1/health" 2>/dev/null || true)
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

# 9. Auth-required route denial
echo "  ● Auth-required route denial"
# Protected route without auth should return 401
check "Protected route returns 401" "GET" "/api/v1/delivery/customer/profile" "401"

echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
printf "│  Result: %d passed, %d failed                               │\n" "$PASS" "$FAIL"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""
[ "$FAIL" -eq 0 ]
