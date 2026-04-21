#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Chaos Engineering Test Runner for Staging
.DESCRIPTION
    Comprehensive chaos testing with circuit breaker monitoring and predictive alert verification
.EXAMPLE
    .\run-chaos-tests.ps1
    .\run-chaos-tests.ps1 -Continuous
    .\run-chaos-tests.ps1 -Scenario RedisFailure
#>
[CmdletBinding()]
param(
    [switch]$Continuous,
    [int]$Duration = 300,  # 5 minutes default
    [ValidateSet("All", "RedisFailure", "CircuitBreaker", "CorrelatedFailure", "RateLimit", "NetworkPartition")]
    [string]$Scenario = "All",
    [string]$ReportPath = "chaos-results"
)

$ErrorActionPreference = "Stop"

# Colors
$Red = "`e[31m"
$Green = "`e[32m"
$Yellow = "`e[33m"
$Blue = "`e[34m"
$Reset = "`e[0m"

function Write-ChaosLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "SUCCESS" { $Green }
        "ERROR" { $Red }
        "WARN" { $Yellow }
        "CHAOS" { $Red }
        default { $Blue }
    }
    Write-Host "$color[$timestamp] [$Level]$Reset $Message"
    
    # Also log to file
    $logFile = "$ReportPath/chaos-$(Get-Date -Format 'yyyyMMdd').log"
    "[$timestamp] [$Level] $Message" | Out-File $logFile -Append
}

function Initialize-ChaosEnvironment {
    if (-not (Test-Path $ReportPath)) {
        New-Item -ItemType Directory -Path $ReportPath -Force | Out-Null
    }
    
    Write-ChaosLog "Chaos Test Environment Initialized" "INFO"
    Write-ChaosLog "Report Path: $ReportPath" "INFO"
    Write-ChaosLog "Target API: http://localhost:8001" "INFO"
}

function Get-SystemHealth {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8001/health/detailed" -Method GET -TimeoutSec 5
        return $response
    }
    catch {
        Write-ChaosLog "Failed to get health status: $_" "ERROR"
        return $null
    }
}

function Test-RedisFailure {
    Write-ChaosLog "=== SCENARIO: Redis Failure ===" "CHAOS"
    Write-ChaosLog "Stopping Redis container..." "CHAOS"
    
    # Record pre-chaos state
    $before = Get-SystemHealth
    Write-ChaosLog "Pre-chaos circuit state: $($before.redis.circuit_state)" "INFO"
    
    # Inject failure
    docker-compose -f docker-compose.staging.yml stop redis 2>&1 | Out-Null
    
    # Wait and monitor
    for ($i = 1; $i -le 5; $i++) {
        Start-Sleep -Seconds 2
        $during = Get-SystemHealth
        
        if ($during) {
            Write-ChaosLog "Attempt $i - Circuit state: $($during.redis.circuit_state)" "INFO"
        }
        else {
            Write-ChaosLog "Attempt $i - API unavailable (expected)" "WARN"
        }
    }
    
    # Recovery
    Write-ChaosLog "Restarting Redis..." "INFO"
    docker-compose -f docker-compose.staging.yml start redis 2>&1 | Out-Null
    Start-Sleep -Seconds 10
    
    $after = Get-SystemHealth
    Write-ChaosLog "Post-recovery circuit state: $($after.redis.circuit_state)" "INFO"
    
    if ($after.redis.circuit_state -eq "CLOSED") {
        Write-ChaosLog "✅ Redis failure test PASSED - Circuit breaker recovered" "SUCCESS"
        return $true
    }
    else {
        Write-ChaosLog "⚠️ Circuit breaker state: $($after.redis.circuit_state)" "WARN"
        return $false
    }
}

function Test-CircuitBreakerTransitions {
    Write-ChaosLog "=== SCENARIO: Circuit Breaker State Transitions ===" "CHAOS"
    
    $states = @()
    
    # Step 1: Normal operation
    $health = Get-SystemHealth
    $states += @{ step = "initial"; state = $health.redis.circuit_state }
    Write-ChaosLog "Initial state: $($health.redis.circuit_state)" "INFO"
    
    # Step 2: Force failures (simulate by stopping Redis multiple times briefly)
    for ($i = 1; $i -le 3; $i++) {
        docker-compose -f docker-compose.staging.yml stop redis 2>&1 | Out-Null
        Start-Sleep -Milliseconds 500
        docker-compose -f docker-compose.staging.yml start redis 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        
        $health = Get-SystemHealth
        Write-ChaosLog "Failure $i - State: $($health.redis.circuit_state)" "INFO"
        $states += @{ step = "failure_$i"; state = $health.redis.circuit_state }
    }
    
    # Step 3: Wait for recovery
    Start-Sleep -Seconds 15
    $health = Get-SystemHealth
    $states += @{ step = "recovery"; state = $health.redis.circuit_state }
    
    # Verify we saw OPEN state
    $sawOpen = $states | Where-Object { $_.state -eq "OPEN" }
    $sawClosed = ($states | Select-Object -Last 1).state -eq "CLOSED"
    
    if ($sawOpen -and $sawClosed) {
        Write-ChaosLog "✅ Circuit breaker transitions test PASSED" "SUCCESS"
        Write-ChaosLog "   States observed: $($states.state -join ' → ')" "INFO"
        return $true
    }
    else {
        Write-ChaosLog "⚠️ Expected to see OPEN state during test" "WARN"
        return $false
    }
}

function Test-PredictiveAlerts {
    Write-ChaosLog "=== SCENARIO: Predictive Alert Verification ===" "CHAOS"
    
    # Send degrading metrics to trigger predictive alert
    $payload = @{
        service = "redis"
        metrics = @{
            latency_ms = @(10, 30, 80, 200, 500, 1200)  # Exponential degradation
            error_rate = @(0, 0.001, 0.01, 0.05, 0.2, 0.5)
        }
    } | ConvertTo-Json -Depth 3
    
    Write-ChaosLog "Injecting degrading metrics..." "CHAOS"
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8001/health/predictive-test" `
            -Method POST -Body $payload -ContentType "application/json" -TimeoutSec 10
        
        Write-ChaosLog "Response: $($response | ConvertTo-Json)" "INFO"
        
        if ($response.alert_sent -or $response.prediction -eq "degrading") {
            Write-ChaosLog "✅ Predictive alert system responding" "SUCCESS"
            return $true
        }
        else {
            Write-ChaosLog "⚠️ Predictive alert not triggered (may need tuning)" "WARN"
            return $false
        }
    }
    catch {
        Write-ChaosLog "Predictive alert test error: $_" "ERROR"
        return $false
    }
}

function Test-CorrelatedFailures {
    Write-ChaosLog "=== SCENARIO: Correlated Failure Detection ===" "CHAOS"
    
    # Inject failures across multiple services
    $services = @(
        @{ name = "redis"; latency = @(50, 150, 400, 1000, 2500) }
        @{ name = "celery"; latency = @(50, 120, 350, 900, 2200) }
        @{ name = "postgres"; latency = @(20, 60, 180, 540, 1600) }
    )
    
    foreach ($svc in $services) {
        $payload = @{
            service = $svc.name
            metrics = @{ latency_ms = $svc.latency }
        } | ConvertTo-Json
        
        try {
            Invoke-RestMethod -Uri "http://localhost:8001/health/predictive-test" `
                -Method POST -Body $payload -ContentType "application/json" -TimeoutSec 5 | Out-Null
        }
        catch {
            # Expected to fail as endpoint may not exist yet
        }
    }
    
    Write-ChaosLog "Injected degrading metrics to multiple services" "CHAOS"
    Start-Sleep -Seconds 5
    
    # Check for correlated failure detection
    $health = Get-SystemHealth
    
    if ($health.system_wide -and $health.system_wide.correlated_failure_detected) {
        Write-ChaosLog "✅ Correlated failure detected!" "SUCCESS"
        return $true
    }
    else {
        Write-ChaosLog "ℹ️ Correlated failure detection result: $($health.system_wide | ConvertTo-Json)" "INFO"
        return $false
    }
}

function Test-RateLimiting {
    Write-ChaosLog "=== SCENARIO: Rate Limit Stress Test ===" "CHAOS"
    
    $jobs = @()
    $success = 0
    $rateLimited = 0
    
    # Fire 50 rapid requests
    for ($i = 1; $i -le 50; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($i)
            try {
                $r = Invoke-RestMethod -Uri "http://localhost:8001/health" -TimeoutSec 2
                return @{ id = $i; status = "success" }
            }
            catch {
                return @{ id = $i; status = "error"; error = $_.Exception.Message }
            }
        } -ArgumentList $i
    }
    
    Write-ChaosLog "Fired 50 concurrent requests..." "CHAOS"
    
    $results = $jobs | Wait-Job | Receive-Job
    $jobs | Remove-Job
    
    $success = ($results | Where-Object { $_.status -eq "success" }).Count
    $errors = ($results | Where-Object { $_.status -eq "error" }).Count
    
    Write-ChaosLog "Results: $success success, $errors errors" "INFO"
    
    if ($success -gt 0) {
        Write-ChaosLog "✅ API handled load test" "SUCCESS"
        return $true
    }
    else {
        Write-ChaosLog "⚠️ All requests failed - possible outage" "WARN"
        return $false
    }
}

function Start-ContinuousChaos {
    param([int]$DurationSeconds)
    
    Write-ChaosLog "Starting CONTINUOUS chaos mode for $DurationSeconds seconds" "CHAOS"
    
    $endTime = (Get-Date).AddSeconds($DurationSeconds)
    $iteration = 0
    $results = @()
    
    while ((Get-Date) -lt $endTime) {
        $iteration++
        Write-ChaosLog "=== ITERATION $iteration ===" "INFO"
        
        # Randomly select a scenario
        $scenarios = @("RedisFailure", "CircuitBreaker", "PredictiveAlerts", "RateLimit")
        $selected = $scenarios | Get-Random
        
        $result = switch ($selected) {
            "RedisFailure" { Test-RedisFailure }
            "CircuitBreaker" { Test-CircuitBreakerTransitions }
            "PredictiveAlerts" { Test-PredictiveAlerts }
            "RateLimit" { Test-RateLimiting }
        }
        
        $results += @{ iteration = $iteration; scenario = $selected; passed = $result }
        
        # Wait between iterations
        $wait = Get-Random -Minimum 10 -Maximum 30
        Write-ChaosLog "Waiting $wait seconds before next iteration..." "INFO"
        Start-Sleep -Seconds $wait
    }
    
    return $results
}

function Export-ChaosReport {
    param($Results)
    
    $report = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        duration = $Duration
        scenario = $Scenario
        results = $Results
        summary = @{
            total = $Results.Count
            passed = ($Results | Where-Object { $_.passed }).Count
            failed = ($Results | Where-Object { -not $_.passed }).Count
        }
    }
    
    $reportPath = "$ReportPath/chaos-report-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
    $report | ConvertTo-Json -Depth 5 | Out-File $reportPath
    
    Write-ChaosLog "Report saved to: $reportPath" "SUCCESS"
    
    # Summary
    Write-ChaosLog "==========================================" "INFO"
    Write-ChaosLog "CHAOS TEST SUMMARY" "INFO"
    Write-ChaosLog "==========================================" "INFO"
    Write-ChaosLog "Total Tests: $($report.summary.total)" "INFO"
    Write-ChaosLog "Passed: $($report.summary.passed)" "SUCCESS"
    Write-ChaosLog "Failed: $($report.summary.failed)" $(if ($report.summary.failed -gt 0) { "ERROR" } else { "INFO" })
    Write-ChaosLog "Success Rate: $([math]::Round(($report.summary.passed / $report.summary.total) * 100, 2))%" "INFO"
    Write-ChaosLog "==========================================" "INFO"
}

# Main Execution
Initialize-ChaosEnvironment

if ($Continuous) {
    $results = Start-ContinuousChaos -DurationSeconds $Duration
}
else {
    $results = switch ($Scenario) {
        "All" {
            @(
                @{ scenario = "RedisFailure"; passed = (Test-RedisFailure) }
                @{ scenario = "CircuitBreaker"; passed = (Test-CircuitBreakerTransitions) }
                @{ scenario = "PredictiveAlerts"; passed = (Test-PredictiveAlerts) }
                @{ scenario = "CorrelatedFailure"; passed = (Test-CorrelatedFailures) }
                @{ scenario = "RateLimit"; passed = (Test-RateLimiting) }
            )
        }
        "RedisFailure" { @(@{ scenario = "RedisFailure"; passed = (Test-RedisFailure) }) }
        "CircuitBreaker" { @(@{ scenario = "CircuitBreaker"; passed = (Test-CircuitBreakerTransitions) }) }
        "CorrelatedFailure" { @(@{ scenario = "CorrelatedFailure"; passed = (Test-CorrelatedFailures) }) }
        "RateLimit" { @(@{ scenario = "RateLimit"; passed = (Test-RateLimiting) }) }
    }
}

Export-ChaosReport -Results $results
