# Phase 22.5 — AI Tester Safe Runtime Start
# Usage: .\scripts\ai_tester_runtime_start.ps1 [-DryRun] [-CheckOnly]

param(
    [switch]$DryRun,
    [switch]$CheckOnly
)

Write-Host "=== AI Tester Runtime Start ==="
Write-Host "Mode: dry-run=$DryRun check-only=$CheckOnly"
Write-Host ""

$BackendCmd = "cd backend; uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning"
$FrontendCmd = "cd frontend; bun run dev --port 5173"

if ($CheckOnly) {
    Write-Host "[CHECK] Backend command: $BackendCmd"
    try {
        $Response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "  — Backend is running (HTTP $($Response.StatusCode))"
    } catch {
        Write-Host "  — Backend is not running"
    }

    Write-Host "[CHECK] Frontend command: $FrontendCmd"
    try {
        $Response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "  — Frontend is running (HTTP $($Response.StatusCode))"
    } catch {
        Write-Host "  — Frontend is not running"
    }
} elseif ($DryRun) {
    Write-Host "[DRY-RUN] Would execute: $BackendCmd"
    Write-Host "[DRY-RUN] Would execute: $FrontendCmd"
} else {
    Write-Host "[START] Starting backend..."
    # Note: actual execution requires separate terminal
    Write-Host "  Run in separate terminal: $BackendCmd"

    Write-Host "[START] Starting frontend..."
    Write-Host "  Run in separate terminal: $FrontendCmd"
}

Write-Host ""
Write-Host "=== Done ==="
