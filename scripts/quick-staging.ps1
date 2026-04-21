# Quick Staging API Starter
param([int]$Port = 8001)

Write-Host "[INFO] Starting Gracia OS Staging API on port $Port..." -ForegroundColor Cyan

$StagingDir = "staging-run"
New-Item -ItemType Directory -Path $StagingDir -Force -ErrorAction SilentlyContinue | Out-Null

# Set environment variables
$env:ENVIRONMENT = "staging"
$env:DEBUG = "true"
$env:LOG_LEVEL = "INFO"
$env:HOST = "0.0.0.0"
$env:PORT = "$Port"
$env:DATABASE_URL = "sqlite+aiosqlite:///../$StagingDir/staging.db"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL = "redis://localhost:6379/1"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/2"

# Check Python
if (-not (Test-Path "backend\.venv\Scripts\python.exe")) {
    Write-Host "[ERROR] Virtual environment not found. Run setup first." -ForegroundColor Red
    exit 1
}

# Test Redis
Write-Host "[INFO] Checking Redis..." -ForegroundColor Yellow
try {
    $redis = redis-cli ping 2>&1
    if ($redis -eq "PONG") {
        Write-Host "[OK] Redis connected" -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Redis not available - using fallback" -ForegroundColor Yellow
}

Write-Host "`nAPI Endpoints:" -ForegroundColor Cyan
Write-Host "   Health:      http://localhost:$Port/health" -ForegroundColor White
Write-Host "   Detailed:    http://localhost:$Port/api/v1/system/health/detailed" -ForegroundColor White
Write-Host "   Resilience:  http://localhost:$Port/api/v1/system/resilience/status" -ForegroundColor White
Write-Host "   Scraper:     http://localhost:$Port/api/v1/system/scraper-health" -ForegroundColor White
Write-Host ""

Write-Host "Test Commands:" -ForegroundColor Cyan
Write-Host "   curl http://localhost:$Port/api/v1/system/health/detailed" -ForegroundColor Gray
Write-Host "   curl http://localhost:$Port/api/v1/system/resilience/status" -ForegroundColor Gray
Write-Host ""

Write-Host "[INFO] Starting server (wait 10-20s for init)..." -ForegroundColor Yellow
Write-Host "[INFO] Press Ctrl+C to stop" -ForegroundColor Magenta

Set-Location backend
& .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port $Port --reload
