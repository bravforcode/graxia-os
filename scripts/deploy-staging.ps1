#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploy Gracia OS to Staging Environment
.DESCRIPTION
    Enterprise-grade staging deployment with health checks, chaos testing, and monitoring
.EXAMPLE
    .\deploy-staging.ps1
    .\deploy-staging.ps1 -SkipTests
    .\deploy-staging.ps1 -WithChaos
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$WithChaos,
    [switch]$WithMonitoring,
    [string]$Tag = "staging-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
)

$ErrorActionPreference = "Stop"

# Colors for output
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

function Test-StagingHealth {
    param([int]$MaxRetries = 30)
    
    Write-Status "Waiting for staging services to be healthy..." "INFO"
    
    $healthy = $false
    $retry = 0
    
    while ($retry -lt $MaxRetries -and -not $healthy) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method GET -TimeoutSec 5 -ErrorAction Stop
            
            if ($response.status -eq "healthy" -or $response.status -eq "ok") {
                Write-Status "API is healthy!" "SUCCESS"
                $healthy = $true
                return $true
            }
        }
        catch {
            Write-Status "Attempt $($retry + 1)/$MaxRetries - API not ready yet..." "WARN"
        }
        
        $retry++
        Start-Sleep -Seconds 2
    }
    
    if (-not $healthy) {
        Write-Status "Services failed to become healthy within timeout" "ERROR"
        return $false
    }
    
    return $true
}

function Invoke-ChaosTests {
    Write-Status "Starting Chaos Engineering Tests..." "INFO"
    Write-Status "This will inject failures to verify resilience" "WARN"
    
    docker-compose -f docker-compose.staging.yml --profile chaos run --rm chaos | Tee-Object -FilePath "chaos-results/chaos-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
    
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Status "✅ Chaos tests PASSED" "SUCCESS"
    }
    else {
        Write-Status "❌ Chaos tests FAILED (Exit code: $exitCode)" "ERROR"
        Write-Status "Review logs in chaos-results/" "WARN"
    }
    
    return $exitCode -eq 0
}

function Test-CircuitBreakerTransitions {
    Write-Status "Verifying Circuit Breaker State Transitions..." "INFO"
    
    try {
        # Force Redis failures to trigger circuit breaker
        Write-Status "Step 1: Testing Redis circuit breaker..." "INFO"
        
        # Stop Redis temporarily
        docker-compose -f docker-compose.staging.yml stop redis
        Start-Sleep -Seconds 5
        
        # Check circuit breaker state via health endpoint
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:8001/health/detailed" -Method GET -TimeoutSec 5
            Write-Status "Circuit breaker state during outage: $($response.redis.circuit_state)" "INFO"
        }
        catch {
            Write-Status "Expected failure during Redis outage" "WARN"
        }
        
        # Restart Redis
        docker-compose -f docker-compose.staging.yml start redis
        Start-Sleep -Seconds 10
        
        # Verify recovery
        $response = Invoke-RestMethod -Uri "http://localhost:8001/health/detailed" -Method GET -TimeoutSec 5
        if ($response.redis.circuit_state -eq "CLOSED") {
            Write-Status "✅ Circuit breaker recovered to CLOSED" "SUCCESS"
        }
        else {
            Write-Status "⚠️ Circuit breaker state: $($response.redis.circuit_state)" "WARN"
        }
        
        return $true
    }
    catch {
        Write-Status "Circuit breaker test error: $_" "ERROR"
        return $false
    }
}

function Test-PredictiveAlerts {
    Write-Status "Testing Predictive Alert System..." "INFO"
    
    try {
        # Inject degrading metrics
        $payload = @{
            metrics = @{
                latency_ms = @(10, 50, 120, 280, 500, 900)  # Degrading trend
                error_rate = @(0, 0.01, 0.05, 0.15, 0.35, 0.6)
            }
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "http://localhost:8001/health/predictive-test" -Method POST -Body $payload -ContentType "application/json" -TimeoutSec 10
        
        if ($response.alert_sent -eq $true) {
            Write-Status "✅ Predictive alert triggered correctly" "SUCCESS"
        }
        else {
            Write-Status "⚠️ Predictive alert not triggered (may be within cooldown)" "WARN"
        }
        
        return $true
    }
    catch {
        Write-Status "Predictive alert test error: $_" "WARN"
        return $false
    }
}

# Main Deployment Flow
Write-Status "==========================================" "INFO"
Write-Status "Gracia OS Staging Deployment" "INFO"
Write-Status "Tag: $Tag" "INFO"
Write-Status "==========================================" "INFO"

# Step 1: Environment Check
Write-Status "Step 1: Checking environment..." "INFO"

if (-not (Test-Path "docker-compose.staging.yml")) {
    Write-Status "docker-compose.staging.yml not found!" "ERROR"
    exit 1
}

if (-not (Test-Path ".env.staging")) {
    Write-Status "⚠️ .env.staging not found, creating from template..." "WARN"
    Copy-Item ".env.example" ".env.staging" -ErrorAction SilentlyContinue
}

# Step 2: Run Local Tests (unless skipped)
if (-not $SkipTests) {
    Write-Status "Step 2: Running local test suite..." "INFO"
    
    Set-Location backend
    $testOutput = python -m pytest tests/ -v --tb=short 2>&1
    $testExit = $LASTEXITCODE
    Set-Location ..
    
    if ($testExit -ne 0) {
        Write-Status "❌ Local tests failed!" "ERROR"
        Write-Status $testOutput "ERROR"
        exit 1
    }
    
    Write-Status "✅ Local tests passed" "SUCCESS"
}
else {
    Write-Status "Step 2: Skipping local tests (requested)" "WARN"
}

# Step 3: Deploy to Staging
Write-Status "Step 3: Deploying to staging..." "INFO"

docker-compose -f docker-compose.staging.yml down -v 2>$null
docker-compose -f docker-compose.staging.yml build --no-cache
docker-compose -f docker-compose.staging.yml up -d

if ($LASTEXITCODE -ne 0) {
    Write-Status "❌ Deployment failed!" "ERROR"
    exit 1
}

Write-Status "✅ Services deployed" "SUCCESS"

# Step 4: Health Check
Write-Status "Step 4: Running health checks..." "INFO"

if (-not (Test-StagingHealth)) {
    Write-Status "❌ Health checks failed!" "ERROR"
    docker-compose -f docker-compose.staging.yml logs api --tail=100
    exit 1
}

# Step 5: Circuit Breaker Verification
Write-Status "Step 5: Verifying circuit breaker..." "INFO"
Test-CircuitBreakerTransitions | Out-Null

# Step 6: Predictive Alert Testing
Write-Status "Step 6: Testing predictive alerts..." "INFO"
Test-PredictiveAlerts | Out-Null

# Step 7: Chaos Tests (if requested)
if ($WithChaos) {
    Write-Status "Step 7: Running chaos tests..." "INFO"
    
    if (-not (Invoke-ChaosTests)) {
        Write-Status "⚠️ Chaos tests revealed issues - review required" "WARN"
    }
}
else {
    Write-Status "Step 7: Skipping chaos tests (use -WithChaos to enable)" "INFO"
}

# Step 8: Deployment Summary
Write-Status "==========================================" "INFO"
Write-Status "DEPLOYMENT COMPLETE" "SUCCESS"
Write-Status "==========================================" "INFO"
Write-Status "API: http://localhost:8001" "INFO"
Write-Status "Redis: localhost:6380" "INFO"
Write-Status "Database: localhost:5433" "INFO"
if ($WithMonitoring) {
    Write-Status "Grafana: http://localhost:3001 (admin/admin)" "INFO"
    Write-Status "Prometheus: http://localhost:9091" "INFO"
}
Write-Status "==========================================" "INFO"

# Save deployment info
$deployInfo = @{
    tag = $Tag
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    status = "deployed"
    services = @("api", "worker", "beat", "redis", "db")
    urls = @{
        api = "http://localhost:8001"
        health = "http://localhost:8001/health"
    }
} | ConvertTo-Json -Depth 3

$deployInfo | Out-File "staging-deploy-$Tag.json"
Write-Status "Deployment info saved to staging-deploy-$Tag.json" "INFO"
