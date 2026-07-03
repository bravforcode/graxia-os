# Phase 22.5 — AI Tester Safe Runtime Stop
# Usage: .\scripts\ai_tester_runtime_stop.ps1 [-DryRun]

param([switch]$DryRun)

Write-Host "=== AI Tester Runtime Stop ==="

$BackendProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "uvicorn" }
if ($BackendProcs) {
    foreach ($proc in $BackendProcs) {
        if ($DryRun) {
            Write-Host "[DRY-RUN] Would stop backend PID: $($proc.Id)"
        } else {
            Write-Host "[STOP] Stopping backend (PID: $($proc.Id))..."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[INFO] Backend not running."
}

$FrontendProcs = Get-Process -Name "bun" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "bun run dev" }
if ($FrontendProcs) {
    foreach ($proc in $FrontendProcs) {
        if ($DryRun) {
            Write-Host "[DRY-RUN] Would stop frontend PID: $($proc.Id)"
        } else {
            Write-Host "[STOP] Stopping frontend (PID: $($proc.Id))..."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[INFO] Frontend not running."
}

Write-Host "=== Done ==="
