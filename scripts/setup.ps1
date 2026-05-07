# Brav OS - Auto-Pilot Setup Script
$ErrorActionPreference = "Stop"

Write-Host "--- Starting Brav OS Setup ---" -ForegroundColor Cyan

# 1. Check Dependencies
Write-Host "[1/4] Checking dependencies..."
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found. Please install Docker Desktop."
}
if (!(Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    Write-Error "docker-compose not found."
}
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning "Python not found in PATH, but containerized version will be used."
}

# 2. Generate .env.template and .env
Write-Host "[2/4] Generating environment configuration..."
$envTemplate = @"
# API Configuration
PROJECT_NAME="Brav OS Intelligence"
API_V1_STR="/v1"

# Security
API_KEY="brav-os-secret-$(New-Guid)"
OPENAI_API_KEY="sk-..."

# Infrastructure
REDIS_URL="redis://redis-cache:6379/0"
QDRANT_HOST="qdrant"
QDRANT_PORT=6333

# Observability
LOG_LEVEL="INFO"
ENVIRONMENT="production"
"@

if (!(Test-Path "../.env.template")) {
    $envTemplate | Out-File -FilePath "../.env.template" -Encoding utf8
}

if (!(Test-Path "../.env")) {
    Write-Host "Creating .env from template. PLEASE UPDATE OPENAI_API_KEY in .env!" -ForegroundColor Yellow
    $envTemplate | Out-File -FilePath "../.env" -Encoding utf8
}

# 3. Pull and Start Stack
Write-Host "[3/4] Starting the engine room (Docker stack)..."
docker-compose -f "../docker-compose.yml" pull
docker-compose -f "../docker-compose.yml" up -d --build

# 4. Health Checks
Write-Host "[4/4] Running health checks..."
$maxRetries = 10
$retryCount = 0
$healthy = $false

while ($retryCount -lt $maxRetries) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -ErrorAction SilentlyContinue
        if ($response.status -eq "healthy") {
            $healthy = $true
            break
        }
    } catch {
        # Wait and retry
    }
    Write-Host "Waiting for API to be ready... ($($retryCount + 1)/$maxRetries)"
    Start-Sleep -Seconds 5
    $retryCount++
}

if ($healthy) {
    Write-Host "Brav OS is ONLINE and HEALTHY!" -ForegroundColor Green
    Write-Host "API: http://localhost:8000/v1/docs"
    Write-Host "RedisInsight: http://localhost:8001"
} else {
    Write-Error "Health check failed after $maxRetries retries."
}
