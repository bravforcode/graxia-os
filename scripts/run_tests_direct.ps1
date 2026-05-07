# Direct Test Runner (No Docker)
# Installs minimal dependencies and runs tests

Write-Host "=== Graxia OS Test Runner ===" -ForegroundColor Cyan
Write-Host ""

# Check Python
$pythonPath = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Host "ERROR: Python not found at $pythonPath" -ForegroundColor Red
    exit 1
}

Write-Host "Python: $pythonPath" -ForegroundColor Green
& $pythonPath --version

# Install minimal test dependencies
Write-Host ""
Write-Host "Installing test dependencies..." -ForegroundColor Yellow
$testDeps = @(
    "pytest==8.0.0",
    "pytest-asyncio==0.23.5",
    "httpx==0.28.1",
    "fastapi==0.110.0",
    "sqlalchemy[asyncio]==2.0.27",
    "pydantic[email]==2.11.7",
    "pydantic-settings==2.2.1",
    "PyJWT==2.8.0",
    "passlib[bcrypt]==1.7.4",
    "structlog==24.1.0",
    "redis==5.0.2",
    "aiosqlite==0.20.0"
)

foreach ($dep in $testDeps) {
    Write-Host "  Installing $dep..." -ForegroundColor Gray
    & $pythonPath -m pip install $dep --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  WARNING: Failed to install $dep" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Running Tests ===" -ForegroundColor Cyan
Write-Host ""

# Set PYTHONPATH to include backend directory
$env:PYTHONPATH = "$PSScriptRoot\backend"

# Run tests
& $pythonPath -m pytest backend/tests/ -v --tb=short --maxfail=10 -x

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "=== ALL TESTS PASSED ===" -ForegroundColor Green
} else {
    Write-Host "=== TESTS FAILED (Exit Code: $exitCode) ===" -ForegroundColor Red
}

exit $exitCode
