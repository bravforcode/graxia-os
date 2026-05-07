# Check Docker Status
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== CHECKING DOCKER ===" -ForegroundColor Cyan
Write-Host ""

# Check 1: Docker Version
Write-Host "[1] Docker Version:" -ForegroundColor Yellow
try {
    $ver = docker version --format "{{.Server.Version}}" 2>&1
    if ($ver) {
        Write-Host "    OK - Docker v$ver" -ForegroundColor Green
    } else {
        Write-Host "    FAIL - Cannot get version" -ForegroundColor Red
    }
} catch {
    Write-Host "    ERROR - $_" -ForegroundColor Red
}

# Check 2: Docker Info
Write-Host "`n[2] Docker Info:" -ForegroundColor Yellow
try {
    $info = docker info --format "{{.Name}}" 2>&1
    if ($info) {
        Write-Host "    OK - Docker daemon on $info" -ForegroundColor Green
    } else {
        Write-Host "    FAIL - Cannot connect to daemon" -ForegroundColor Red
    }
} catch {
    Write-Host "    ERROR - $_" -ForegroundColor Red
}

# Check 3: Docker PS
Write-Host "`n[3] Running Containers:" -ForegroundColor Yellow
try {
    $containers = docker ps --format "{{.Names}}" 2>&1
    $count = ($containers | Measure-Object).Count
    Write-Host "    Found $count containers" -ForegroundColor Cyan
    if ($count -gt 0) {
        $containers | Select-Object -First 10 | ForEach-Object { Write-Host "    - $_" -ForegroundColor Gray }
    }
} catch {
    Write-Host "    ERROR - $_" -ForegroundColor Red
}

# Check 4: Port Tests
Write-Host "`n[4] Port Tests:" -ForegroundColor Yellow
$ports = @(6379, 6380, 6381, 6382, 8123, 8200, 9090, 3001, 8000)
foreach ($port in $ports) {
    try {
        $result = Test-NetConnection -ComputerName localhost -Port $port -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            Write-Host "    Port $port : OPEN" -ForegroundColor Green
        } else {
            Write-Host "    Port $port : closed" -ForegroundColor Gray
        }
    } catch {
        Write-Host "    Port $port : error" -ForegroundColor Red
    }
}

Write-Host "`n=== DONE ===" -ForegroundColor Cyan
