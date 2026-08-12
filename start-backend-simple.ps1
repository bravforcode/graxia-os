#!/usr/bin/env pwsh
# Simple Graxia Backend Starter (Fixes redirect issues)

$ErrorActionPreference = "Stop"

$root = "C:\graxia os"
if (-not (Test-Path $root)) {
    $root = "C:\Users\menum\graxia os"
}

$logsDir = Join-Path $root "logs"
$null = New-Item -ItemType Directory -Force -Path $logsDir

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Starting Graxia Backend (Simple Mode)                        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# Set environment variables
$env:OLLAMA_PAY_API_KEY = "sk-dbeee8e2e35c4635939848280521f6aa"
$env:OLLAMA_PAY_BASE_URL = "https://ollama-pay.thaigqsoft.com/api/v1"
$env:PYTHONPATH = "$root\backend"

Write-Host "`n🔧 Environment configured" -ForegroundColor Green
Write-Host "   OLLAMA_PAY_API_KEY: $($env:OLLAMA_PAY_API_KEY.Substring(0, 20))..." -ForegroundColor Gray
Write-Host "   PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Gray

# Check if already running
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -TimeoutSec 2
    Write-Host "`n⚠️  Backend already running!" -ForegroundColor Yellow
    Write-Host "   API: http://localhost:8000" -ForegroundColor Cyan
    exit 0
} catch {
    Write-Host "`n🚀 Starting backend..." -ForegroundColor Yellow
}

# Start Redis
Write-Host "`n[1/2] Starting Redis..." -ForegroundColor Cyan
try {
    $pong = (redis-cli ping 2>$null)
    if ($pong -eq "PONG") {
        Write-Host "   ✅ Redis already running" -ForegroundColor Green
    } else {
        Start-Process "redis-server" -ArgumentList "--port 6379" -WindowStyle Hidden
        Start-Sleep -Seconds 2
        Write-Host "   ✅ Redis started" -ForegroundColor Green
    }
} catch {
    Write-Host "   ⚠️  Redis not available (optional)" -ForegroundColor Yellow
}

# Start Backend
Write-Host "`n[2/2] Starting Backend API..." -ForegroundColor Cyan
$uvicorn = Join-Path $root "backend\venv\Scripts\uvicorn.exe"

if (-not (Test-Path $uvicorn)) {
    Write-Error "uvicorn not found at: $uvicorn"
    Write-Host "   Run: cd '$root\backend'; python -m venv venv; .\venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Use different log files for stdout and stderr to avoid the redirect error
$stdoutLog = Join-Path $logsDir "backend-out.log"
$stderrLog = Join-Path $logsDir "backend-err.log"

# Start process without redirect (let it use console for now)
$backendJob = Start-Process -FilePath $uvicorn -ArgumentList @(
    "app.main:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--workers", "1"
) -WorkingDirectory "$root\backend" -PassThru -WindowStyle Hidden

Write-Host "   ✅ Backend starting (PID: $($backendJob.Id))" -ForegroundColor Green

# Wait for API to be ready
Write-Host "`n⏳ Waiting for API to be ready..." -ForegroundColor Yellow
$maxAttempts = 15
for ($i = 1; $i -le $maxAttempts; $i++) {
    Write-Host "   Attempt $i/$maxAttempts..." -ForegroundColor Gray
    Start-Sleep -Seconds 2
    
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
        Write-Host "║  ✅ Graxia Backend is running!                                ║" -ForegroundColor Green
        Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Green
        Write-Host "║  API:     http://localhost:8000                              ║" -ForegroundColor Green
        Write-Host "║  Health:  /api/system/health                                  ║" -ForegroundColor Green
        Write-Host "║  Docs:    http://localhost:8000/docs                         ║" -ForegroundColor Green
        Write-Host "║  PID:     $($backendJob.Id)" -ForegroundColor Green
        Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
        
        # Save PID for later
        $backendJob.Id | Set-Content (Join-Path $root ".graxia-backend.pid")
        
        exit 0
    } catch {
        # Keep waiting
    }
}

Write-Error "Backend failed to start within 30 seconds"
Write-Host "   Check logs at: $logsDir\backend-*.log" -ForegroundColor Yellow
exit 1
