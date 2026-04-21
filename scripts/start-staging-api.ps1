#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Quick-start staging API server locally
.DESCRIPTION
    Starts the Gracia OS API in staging mode on port 8001
#>
param(
    [int]$Port = 8001,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

Write-Host "`e[34m[INFO]`e[0m Starting Gracia OS Staging API on port $Port..." -ForegroundColor Cyan

# Check Python environment
$PythonPath = "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonPath)) {
    Write-Host "`e[31m[ERROR]`e[0m Python virtual environment not found at $PythonPath" -ForegroundColor Red
    Write-Host "`e[33m[WARN]`e[0m Run: cd backend && python -m venv .venv && .venv\Scripts\pip install -e ." -ForegroundColor Yellow
    exit 1
}

# Create staging environment file
$StagingDir = "staging-run"
if (-not (Test-Path $StagingDir)) {
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
}

# Generate staging .env
$EnvContent = @"
ENVIRONMENT=staging
DEBUG=true
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=$Port

# Redis
REDIS_URL=redis://localhost:6379/0

# Database (SQLite for quick staging)
DATABASE_URL=sqlite+aiosqlite:///$StagingDir/staging.db

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Use existing API keys from parent .env
OPENCLAW_API_KEY=${env:OPENCLAW_API_KEY}
GEMINI_API_KEY=${env:GEMINI_API_KEY}
TELEGRAM_BOT_TOKEN=${env:TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${env:TELEGRAM_CHAT_ID}

# Feature flags
SCHEDULER_EMBEDDED=true
"@

$EnvContent | Out-File -FilePath "$StagingDir\.env" -Encoding UTF8
Write-Host "`e[32m[OK]`e[0m Staging environment configured" -ForegroundColor Green

# Check Redis
Write-Host "`e[34m[INFO]`e[0m Checking Redis..." -ForegroundColor Cyan
try {
    $redisPing = redis-cli ping 2>&1
    if ($redisPing -eq "PONG") {
        Write-Host "`e[32m[OK]`e[0m Redis is running" -ForegroundColor Green
    }
    else {
        Write-Host "`e[33m[WARN]`e[0m Redis not responding - some features may be limited" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "`e[33m[WARN]`e[0m Redis not available - circuit breaker will use in-memory fallback" -ForegroundColor Yellow
}

# Start API
Write-Host "`e[34m[INFO]`e[0m Starting API server..." -ForegroundColor Cyan
Write-Host "`e[34m[INFO]`e[0m This will take 10-20 seconds to initialize..." -ForegroundColor Cyan

Set-Location backend

$env:ENVIRONMENT = "staging"
$env:DEBUG = "true"
$env:LOG_LEVEL = "INFO"
$env:HOST = "0.0.0.0"
$env:PORT = "$Port"
$env:DATABASE_URL = "sqlite+aiosqlite:///../$StagingDir/staging.db"
$env:REDIS_URL = "redis://localhost:6379/0"

try {
    & .venv\Scripts\python.exe -c "
import asyncio
import sys

# Quick health check
async def wait_for_api():
    import httpx
    for i in range(30):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get('http://localhost:$Port/health', timeout=2)
                if r.status_code == 200:
                    print('[READY] API is live!')
                    return True
        except:
            pass
        await asyncio.sleep(1)
        print(f'[WAIT] Starting... ({i+1}s)')
    return False

result = asyncio.run(wait_for_api())
sys.exit(0 if result else 1)
" 2>&1 | ForEach-Object { Write-Host $_ -ForegroundColor Gray } &
    
    # Start the actual server
    & .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port $Port --reload
}
finally {
    Set-Location ..
}
