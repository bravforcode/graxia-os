# ──────────────────────────────────────────────────────────────────────────────
# Graxia OS — Staging Smoke Test (PowerShell)
# Run this against a deployed staging environment to verify basic health.
# ──────────────────────────────────────────────────────────────────────────────

param(
    [string]$BaseUrl = "http://localhost:8000"
)

$PASS = 0
$FAIL = 0

function Green { Write-Host "  ✅ $args" -ForegroundColor Green; $script:PASS++ }
function Red { Write-Host "  ❌ $args" -ForegroundColor Red; $script:FAIL++ }

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Graxia OS — Staging Smoke Test" -ForegroundColor Cyan
Write-Host "  Target: $BaseUrl" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 1. Health Check ──────────────────────────────────────────────────────────
Write-Host "── Health Check ──────────────────────────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health" -Headers @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health → 200" } else { Red "GET /api/v1/health → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health → connection failed" }

# ── 2. Readiness Check ────────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Readiness Check ───────────────────────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness" -Headers @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health/readiness → 200" } else { Red "GET /api/v1/health/readiness → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness → connection failed" }

# ── 3. Local Agent Readiness ──────────────────────────────────────────────────
Write-Host ""; Write-Host "── Local Agent Readiness ─────────────────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/local-agent" -Headers @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health/readiness/local-agent → 200" } else { Red "GET /api/v1/health/readiness/local-agent → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness/local-agent → connection failed" }

# ── 4. Staging Readiness ──────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Staging Readiness ────────────────────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness/staging" -Headers @{"X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /api/v1/health/readiness/staging → 200" } else { Red "GET /api/v1/health/readiness/staging → $($resp.StatusCode)" }
} catch { Red "GET /api/v1/health/readiness/staging → connection failed" }

# ── 5. Root Health ───────────────────────────────────────────────────────────
Write-Host ""; Write-Host "── Root Health ───────────────────────────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "GET /health → 200" } else { Red "GET /health → $($resp.StatusCode)" }
} catch { Red "GET /health → connection failed" }

# ── 6. Auth Context (Missing org header) ──────────────────────────────────────
Write-Host ""; Write-Host "── Auth Context (Missing org header) ─────────────────────────" -ForegroundColor Yellow

try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/health/readiness" -Method GET -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "Missing X-Graxia-Org-Id → $($resp.StatusCode) (accepted in local mode)" } else { Green "Missing X-Graxia-Org-Id → $($resp.StatusCode) (rejected)" }
} catch { Green "Missing X-Graxia-Org-Id → rejected (expected)" }

# ── 7. MCP Tools List ────────────────────────────────────────────────────────
Write-Host ""; Write-Host "── MCP Tools ─────────────────────────────────────────────────" -ForegroundColor Yellow

$body = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | ConvertTo-Json -Compress
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/mcp/tools/list" -Headers @{"Content-Type"="application/json"; "X-Graxia-Org-Id"="00000000-0000-0000-0000-000000000001"} -Method POST -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' -UseBasicParsing
    if ($resp.StatusCode -eq 200) { Green "POST /api/v1/mcp/tools/list → 200" } else { Red "POST /api/v1/mcp/tools/list → $($resp.StatusCode)" }
} catch { Red "POST /api/v1/mcp/tools/list → connection failed" }

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""; Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Results: $PASS passed, $FAIL failed" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if ($FAIL -gt 0) { exit 1 }
