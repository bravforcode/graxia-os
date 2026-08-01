#Requires -Version 7.0
<#
.SYNOPSIS
    Start Quant OS for 24/7 live trading.

.DESCRIPTION
    Loads .env, ensures Supabase is running, starts the API server.
    Handles graceful shutdown on Ctrl+C.

.EXAMPLE
    .\start_live.ps1
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Quant OS — Live Trading Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Load .env ──────────────────────────────────────────────────────────
Write-Host "[1/5] Loading .env..." -ForegroundColor Yellow
$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "  OK" -ForegroundColor Green
} else {
    Write-Host "  .env not found!" -ForegroundColor Red
    exit 1
}

# ── Verify required env vars ───────────────────────────────────────────
Write-Host "[2/5] Verifying configuration..." -ForegroundColor Yellow
$required = @(
    "DATABASE_URL",
    "TRADING_MODE",
    "LIVE_TRADING_ENABLED",
    "JWT_SECRET_KEY",
    "WEBHOOK_HMAC_SECRET",
    "ADMIN_API_KEY"
)
$missing = @()
foreach ($key in $required) {
    if (-not [Environment]::GetEnvironmentVariable($key)) {
        $missing += $key
    }
}
if ($missing.Count -gt 0) {
    Write-Host "  Missing: $($missing -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "  TRADING_MODE: $env:TRADING_MODE" -ForegroundColor Green
Write-Host "  LIVE_TRADING_ENABLED: $env:LIVE_TRADING_ENABLED" -ForegroundColor Green
Write-Host "  WEBHOOK_HOST: $($env:WEBHOOK_HOST ?? '127.0.0.1')" -ForegroundColor Green
Write-Host "  WEBHOOK_PORT: $($env:WEBHOOK_PORT ?? '8000')" -ForegroundColor Green

# ── Ensure Supabase is running ────────────────────────────────────────
Write-Host "[3/5] Checking Supabase..." -ForegroundColor Yellow
$supabaseRunning = docker ps --filter "name=supabase_db_quant_os" --format "{{.Names}}" 2>$null
if ($supabaseRunning) {
    Write-Host "  Supabase already running" -ForegroundColor Green
} else {
    Write-Host "  Starting Supabase..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    supabase start 2>&1 | Out-Null
    Pop-Location
    Write-Host "  Supabase started" -ForegroundColor Green
}

# ── Set Python environment ─────────────────────────────────────────────
Write-Host "[4/5] Setting Python environment..." -ForegroundColor Yellow
$env:PYTHONPATH = $ProjectRoot
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"

$host = $env:WEBHOOK_HOST ?? "127.0.0.1"
$port = $env:WEBHOOK_PORT ?? "8000"

Write-Host "  PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Green
Write-Host "  PYTHONIOENCODING: $env:PYTHONIOENCODING" -ForegroundColor Green

# ── Start API server ──────────────────────────────────────────────────
Write-Host "[5/5] Starting Quant OS API..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Server: http://${host}:${port}" -ForegroundColor Cyan
Write-Host "  Mode:   $env:TRADING_MODE" -ForegroundColor Cyan
Write-Host "  Live:   $env:LIVE_TRADING_ENABLED" -ForegroundColor Cyan
Write-Host "  Ctrl+C to stop" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

try {
    python -m uvicorn graxia.packages.quant_os.api.main:app `
        --host $host `
        --port $port `
        --log-level info `
        --workers 1
} catch {
    Write-Host "Server stopped: $_" -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "Quant OS stopped." -ForegroundColor Yellow
}
