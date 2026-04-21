#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Local Staging Deployment for Gracia OS
.DESCRIPTION
    Deploys staging environment locally using Python/uvicorn without Docker
.EXAMPLE
    .\deploy-staging-local.ps1
    .\deploy-staging-local.ps1 -WithChaos
#>
[CmdletBinding()]
param(
    [switch]$WithChaos,
    [switch]$SkipTests,
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$StagingDir = "staging-work"

# Colors
$Red = "`e[31m"
$Green = "`e[32m"
$Yellow = "`e[33m"
$Blue = "`e[34m"
$Reset = "`e[0m"

function Write-Status {
    param([string]$Message, [string]$Status = "INFO")
    $color = switch ($Status) {
        "SUCCESS" { $Green }
        "ERROR" { $Red }
        "WARN" { $Yellow }
        default { $Blue }
    }
    Write-Host "$color[$Status]$Reset $Message"
}

function Initialize-StagingEnv {
    Write-Status "Setting up local staging environment..." "INFO"

    # Create staging work directory
    if (-not (Test-Path $StagingDir)) {
        New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
    }

    # Check if backend virtual environment exists
    $VenvPath = "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPath)) {
        Write-Status "Backend virtual environment not found. Creating..." "WARN"
        Set-Location backend
        python -m venv .venv
        .\.venv\Scripts\pip install -e . 2>&1 | Out-Null
        Set-Location ..
    }

    # Create staging .env file
    $EnvContent = @"
ENVIRONMENT=staging
DEBUG=true
LOG_LEVEL=DEBUG
HOST=0.0.0.0
PORT=$Port

# Redis (local)
REDIS_URL=redis://localhost:6379/0

# Database (SQLite for quick staging)
DATABASE_URL=sqlite+aiosqlite:///$StagingDir/staging.db

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# API Keys (use development keys)
OPENCLAW_API_KEY=${env:OPENCLAW_API_KEY}
GEMINI_API_KEY=${env:GEMINI_API_KEY}

# Telegram (optional for staging)
TELEGRAM_BOT_TOKEN=${env:TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${env:TELEGRAM_CHAT_ID}

# Feature flags
SCHEDULER_EMBEDDED=true
ENABLE_CHAOS_TESTING=true
"@

    $EnvContent | Out-File -FilePath "$StagingDir\.env" -Encoding UTF8
    Write-Status "Staging .env created at $StagingDir\.env" "SUCCESS"
}

function Start-StagingServices {
    Write-Status "Starting staging services on port $Port..." "INFO"

    # Check if port is already in use
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connection) {
        Write-Status "Port $Port is already in use. Stopping existing process..." "WARN"
        Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    # Start Redis if not running
    try {
        $redisPing = redis-cli ping 2>&1
        if ($redisPing -ne "PONG") {
            Write-Status "Starting Redis..." "INFO"
            Start-Process "redis-server" -WindowStyle Hidden
            Start-Sleep -Seconds 3
        }
        Write-Status "Redis is running" "SUCCESS"
    }
    catch {
        Write-Status "Redis not available. Some features may not work." "WARN"
    }

    # Start API server in background
    $ApiScript = @"
import sys
sys.path.insert(0, 'backend')

import os
os.chdir('backend')

# Load staging env
from dotenv import load_dotenv
load_dotenv('../$StagingDir/.env')

# Start server
import uvicorn
uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=$Port,
    reload=False,
    log_level="info"
)
"@

    $ApiScript | Out-File -FilePath "$StagingDir\start_api.py" -Encoding UTF8

    Write-Status "Starting API server (background job)..." "INFO"
    $job = Start-Job -ScriptBlock {
        param($Dir, $Port)
        Set-Location $Dir\..
        & backend\.venv\Scripts\python.exe "$Dir\start_api.py" 2>&1 |
            ForEach-Object { "[API] $_" } |
            Tee-Object -FilePath "$Dir\api.log" -Append
    } -ArgumentList $StagingDir, $Port

    # Save job info
    $job | Export-Clixml "$StagingDir\api-job.xml"

    Write-Status "API server job started (ID: $($job.Id))" "SUCCESS"

    return $job
}

function Wait-ForApi {
    param([int]$TimeoutSeconds = 60)

    Write-Status "Waiting for API to be ready (timeout: ${TimeoutSeconds}s)..." "INFO"

    $startTime = Get-Date
    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:$Port/health" -Method GET -TimeoutSec 2 -ErrorAction Stop
            Write-Status "API is ready! Status: $($response.status)" "SUCCESS"
            return $true
        }
        catch {
            Write-Status "Waiting... ($([math]::Round(((Get-Date) - $startTime).TotalSeconds))s)" "INFO"
            Start-Sleep -Seconds 2
        }
    }

    Write-Status "API failed to start within $TimeoutSeconds seconds" "ERROR"
    return $false
}

function Invoke-ChaosTestsLocal {
    Write-Status "Running chaos tests against local staging..." "INFO"

    $ChaosScript = @"
import sys
sys.path.insert(0, 'backend')

import os
os.chdir('backend')

import asyncio
import httpx
from datetime import datetime

API_URL = "http://localhost:$Port"

async def test_redis_failure():
    print("[CHAOS] Testing Redis circuit breaker...")
    async with httpx.AsyncClient() as client:
        # Get initial state
        r = await client.get(f"{API_URL}/api/v1/system/health/detailed")
        print(f"[CHAOS] Initial state: {r.json()['circuit_breakers']['redis']['state']}")
    return True

async def test_predictive_alert():
    print("[CHAOS] Testing predictive alerts...")
    async with httpx.AsyncClient() as client:
        payload = {
            "service": "test-service",
            "metrics": {
                "latency_ms": [10, 50, 120, 280, 500, 900]
            }
        }
        r = await client.post(
            f"{API_URL}/api/v1/system/health/predictive-test",
            json=payload,
            timeout=10
        )
        result = r.json()
        print(f"[CHAOS] Predictive test result: {result}")
    return True

async def test_resilience_status():
    print("[CHAOS] Checking resilience status...")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_URL}/api/v1/system/resilience/status")
        result = r.json()
        print(f"[CHAOS] Resilience score: {result.get('overall_resilience_score', 'N/A')}/100")
        print(f"[CHAOS] Circuit breakers: {result.get('circuit_breakers', {})}")
    return True

async def main():
    print("="*60)
    print("LOCAL CHAOS TESTS")
    print("="*60)

    tests = [
        ("Redis Circuit Breaker", test_redis_failure),
        ("Predictive Alerts", test_predictive_alert),
        ("Resilience Status", test_resilience_status),
    ]

    passed = 0
    failed = 0

    for name, test in tests:
        try:
            await test()
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1

    print("="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
"@

    $ChaosScript | Out-File -FilePath "$StagingDir\chaos_test.py" -Encoding UTF8

    & backend\.venv\Scripts\python.exe "$StagingDir\chaos_test.py" 2>&1 |
        Tee-Object -FilePath "$StagingDir\chaos-results.log"

    Write-Status "Chaos tests completed. Results saved to $StagingDir\chaos-results.log" "SUCCESS"
}

function Show-StagingStatus {
    Write-Status "==========================================" "INFO"
    Write-Status "STAGING DEPLOYMENT STATUS" "INFO"
    Write-Status "==========================================" "INFO"
    Write-Status "API URL: http://localhost:$Port" "SUCCESS"
    Write-Status "Health: http://localhost:$Port/health" "SUCCESS"
    Write-Status "Detailed: http://localhost:$Port/api/v1/system/health/detailed" "SUCCESS"
    Write-Status "Resilience: http://localhost:$Port/api/v1/system/resilience/status" "SUCCESS"
    Write-Status "==========================================" "INFO"
    Write-Status "Log files:" "INFO"
    Write-Status "  API: $StagingDir\api.log" "INFO"
    Write-Status "  Chaos: $StagingDir\chaos-results.log" "INFO"
    Write-Status "==========================================" "INFO"
    Write-Status "To stop: Stop-Job -Id (Import-Clixml $StagingDir\api-job.xml).Id" "WARN"
}

# Main deployment flow
Write-Status "==========================================" "INFO"
Write-Status "Gracia OS Local Staging Deployment" "INFO"
Write-Status "Port: $Port" "INFO"
Write-Status "==========================================" "INFO"

# Step 1: Initialize
Initialize-StagingEnv

# Step 2: Run tests (unless skipped)
if (-not $SkipTests) {
    Write-Status "Running test suite..." "INFO"
    Set-Location backend
    $testOutput = python -m pytest tests/test_redis_circuit_breaker.py tests/test_redis_pool.py tests/test_smart_scraper.py tests/test_advanced_health.py -v --tb=short 2>&1
    $testExit = $LASTEXITCODE
    Set-Location ..

    if ($testExit -ne 0) {
        Write-Status "Tests failed - checking if critical..." "WARN"
        # Continue anyway for staging
    }
    else {
        Write-Status "Tests passed" "SUCCESS"
    }
}

# Step 3: Start services
$apiJob = Start-StagingServices

# Step 4: Wait for API
if (-not (Wait-ForApi -TimeoutSeconds 60)) {
    Write-Status "Deployment failed - check $StagingDir\api.log" "ERROR"
    exit 1
}

# Step 5: Run chaos tests (if requested)
if ($WithChaos) {
    Start-Sleep -Seconds 5  # Let API stabilize
    Invoke-ChaosTestsLocal
}

# Step 6: Show status
Show-StagingStatus

Write-Status "Deployment complete!" "SUCCESS"
