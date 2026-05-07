# Quick Diagnostic Test for Graxia OS
$ErrorActionPreference = "Continue"

Write-Host "=== GRAXIA OS QUICK DIAGNOSTIC ===" -ForegroundColor Cyan
Write-Host ""

# Test 1: Docker Version
Write-Host "[TEST 1] Docker Version..." -ForegroundColor Yellow
try {
    $version = docker version --format "{{.Server.Version}}" 2>&1
    if ($version) {
        Write-Host "  PASS: Docker v$version" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: Docker not responding" -ForegroundColor Red
    }
} catch {
    Write-Host "  FAIL: Docker error - $_" -ForegroundColor Red
}

# Test 2: Docker Info
Write-Host "`n[TEST 2] Docker Info..." -ForegroundColor Yellow
try {
    $info = docker info --format "{{.Name}}" 2>&1
    if ($info) {
        Write-Host "  PASS: Docker daemon running on $info" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: Docker daemon not accessible" -ForegroundColor Red
    }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# Test 3: Docker Containers
Write-Host "`n[TEST 3] Docker Containers..." -ForegroundColor Yellow
try {
    $containers = docker ps --format "{{.Names}}" 2>&1
    $count = ($containers | Measure-Object).Count
    Write-Host "  INFO: $count containers running" -ForegroundColor Cyan
    if ($count -gt 0) {
        $containers | Select-Object -First 5 | ForEach-Object { Write-Host "    - $_" -ForegroundColor Gray }
    }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# Test 4: Port Checks
Write-Host "`n[TEST 4] Port Availability..." -ForegroundColor Yellow
$ports = @(6379, 6380, 6381, 6382, 8123, 8200, 9002, 9090, 3001)
foreach ($port in $ports) {
    try {
        $result = Test-NetConnection -ComputerName localhost -Port $port -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            Write-Host "  Port $port : OPEN" -ForegroundColor Green
        } else {
            Write-Host "  Port $port : closed" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  Port $port : error" -ForegroundColor Red
    }
}

# Test 5: Compose File Validation
Write-Host "`n[TEST 5] Docker Compose Validation..." -ForegroundColor Yellow
try {
    $null = docker compose -f docker-compose.brutal.yml config 2>&1
    Write-Host "  PASS: docker-compose.brutal.yml is valid" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Compose file error - $_" -ForegroundColor Red
}

Write-Host "`n=== DIAGNOSTIC COMPLETE ===" -ForegroundColor Cyan
