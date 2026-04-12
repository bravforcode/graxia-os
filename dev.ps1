# BravOS Development Server Launcher
# Starts both Backend (FastAPI) and Frontend (Vite) in parallel

Write-Host "=== BravOS Development Environment ===" -ForegroundColor Cyan
Write-Host ""

# Activate Python venv if not already activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Activating Python virtual environment..." -ForegroundColor Yellow
    & ".\backend\.venv\Scripts\Activate.ps1"
}

# Install frontend dependencies if needed
$frontendNodeModules = ".\frontend\node_modules"
if (-not (Test-Path $frontendNodeModules)) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    cd frontend
    bun install
    cd ..
}

# Start Backend in new terminal
Write-Host "Starting Backend (FastAPI)..." -ForegroundColor Green
$backendCmd = "cd backend; python -m uvicorn app.main:app --reload --port 8000"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

# Wait a moment for backend to start
Start-Sleep -Seconds 2

# Start Frontend in new terminal
Write-Host "Starting Frontend (Vite)..." -ForegroundColor Green
$frontendCmd = "cd frontend; bun run dev"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

Write-Host ""
Write-Host "=== Services Starting ===" -ForegroundColor Cyan
Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "Docs:     http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop (or close each terminal separately)" -ForegroundColor Yellow
Write-Host ""

# Keep this terminal open
Read-Host "Press Enter to exit this launcher (services will continue running)"
