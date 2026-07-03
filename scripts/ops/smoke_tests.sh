#!/usr/bin/env bash
# Smoke Tests
# Quick tests to verify the currently running stack is healthy after deployment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
BASE_URL="${BASE_URL:-http://localhost:8000}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-3}"
CURL_MAX_TIME="${CURL_MAX_TIME:-5}"
FAILED=0

check_http() {
    local label="$1"
    local path="$2"
    local url="${BASE_URL}${path}"
    printf "%s... " "$label"
    local response
    response="$(
        curl \
            --connect-timeout "$CURL_CONNECT_TIMEOUT" \
            --max-time "$CURL_MAX_TIME" \
            -sS \
            -o /dev/null \
            -w "%{http_code}" \
            "$url" || true
    )"
    if [[ "$response" == "200" ]]; then
        echo "PASS"
    else
        echo "FAIL (HTTP ${response:-000})"
        FAILED=$((FAILED + 1))
    fi
}

check_compose_service() {
    local label="$1"
    local service="$2"
    local command="$3"
    printf "%s... " "$label"

    if ! command -v docker >/dev/null 2>&1; then
        echo "SKIP (docker unavailable)"
        return
    fi

    if ! docker compose -f "$COMPOSE_FILE" ps --status running "$service" >/dev/null 2>&1; then
        echo "SKIP (${service} not running)"
        return
    fi

    if docker compose -f "$COMPOSE_FILE" exec -T "$service" bash -lc "$command" >/dev/null 2>&1; then
        echo "PASS"
    else
        echo "FAIL"
        FAILED=$((FAILED + 1))
    fi
}

echo "Running smoke tests against ${BASE_URL}"

check_http "Test 1: Root health" "/health"
check_http "Test 2: Jobs stats" "/api/v1/jobs/stats"
check_http "Test 3: Contacts list" "/api/v1/contacts"
check_http "Test 4: Costs summary" "/api/v1/costs/summary"
check_http "Test 5: System health" "/api/v1/system/health"
check_http "Test 6: Prometheus metrics" "/metrics"

check_compose_service "Test 7: Database connectivity" "postgres" \
    "psql -U \"\${POSTGRES_USER:-personal_os}\" -d \"\${POSTGRES_DB:-personal_os}\" -c 'SELECT 1;'"
check_compose_service "Test 8: Redis connectivity" "redis" "redis-cli ping"

echo
echo "========================================="
if [[ "$FAILED" -eq 0 ]]; then
    echo "All smoke tests passed"
    exit 0
fi

echo "${FAILED} smoke test(s) failed"
exit 1
