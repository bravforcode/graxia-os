#!/usr/bin/env pwsh
# Graxia OS Background Daemon
# Runs continuously as Windows service/Task Scheduler
# Minimal RAM usage - direct process execution

param(
    [switch]$Status,    # Check if running
    [switch]$Stop,     # Stop daemon
    [switch]$Restart   # Restart daemon
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$pidFile = Join-Path $root ".graxia-daemon.pid"
$logDir = Join-Path $root "logs"

function Get-DaemonProcesses {
    $pids = @()
    if (Test-Path $pidFile) {
        $pids = Get-Content $pidFile -ErrorAction SilentlyContinue | Where-Object { $_ }
    }
    
    $alive = @()
    foreach ($p in $pids) {
        try {
            $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
            if ($proc -and -not $proc.HasExited) {
                $alive += $proc
            }
        } catch {}
    }
    return $alive
}

function Stop-Daemon {
    Write-Host "Stopping Graxia daemon..." -ForegroundColor Yellow
    $procs = Get-DaemonProcesses
    foreach ($proc in $procs) {
        try {
            taskkill /PID $proc.Id /F /T 2>$null | Out-Null
            Write-Host "  Stopped PID $($proc.Id)" -ForegroundColor Gray
        } catch {}
    }
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
    Write-Host "Daemon stopped" -ForegroundColor Green
}

function Start-Daemon {
    # Ensure not already running
    $existing = Get-DaemonProcesses
    if ($existing.Count -gt 0) {
        Write-Host "Graxia daemon already running (PIDs: $($existing.Id -join ', '))" -ForegroundColor Yellow
        return
    }
    
    # Create log directory
    $null = New-Item -ItemType Directory -Force -Path $logDir
    
    # Start Redis (if available)
    try {
        $redisRunning = (redis-cli ping 2>$null) -eq "PONG"
        if (-not $redisRunning) {
            $redisProc = Start-Process "redis-server" -ArgumentList "--port 6379" -PassThru -WindowStyle Hidden
            Start-Sleep -Seconds 1
        }
    } catch {}
    
    # Start Backend API
    $uvicorn = Join-Path $root "backend/venv/Scripts/uvicorn.exe"
    if (Test-Path $uvicorn) {
        $backendLog = Join-Path $logDir "backend-daemon.log"
        $backendProc = Start-Process $uvicorn -ArgumentList @(
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--workers", "1"           # Single worker = less RAM
        ) -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendLog
    }
    
    # Start Celery Worker (lightweight)
    $celery = Join-Path $root "backend/venv/Scripts/celery.exe"
    if (Test-Path $celery) {
        $celeryLog = Join-Path $logDir "celery-daemon.log"
        $celeryProc = Start-Process $celery -ArgumentList @(
            "-A", "app.tasks.celery_app",
            "worker",
            "--loglevel=warning",
            "--concurrency=1",           # Single worker
            "--pool=solo"                # No prefork = less RAM
        ) -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Hidden -RedirectStandardOutput $celeryLog -RedirectStandardError $celeryLog
    }
    
    # Save PIDs
    @($backendProc.Id, $celeryProc.Id) | Set-Content $pidFile
    
    Write-Host "Graxia daemon started" -ForegroundColor Green
    Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  Logs:     $logDir" -ForegroundColor Gray
    Write-Host "  PIDs:     $($backendProc.Id), $($celeryProc.Id)" -ForegroundColor Gray
}

# Main
if ($Status) {
    $procs = Get-DaemonProcesses
    if ($procs.Count -gt 0) {
        Write-Host "Graxia daemon RUNNING (PIDs: $($procs.Id -join ', '))" -ForegroundColor Green
    } else {
        Write-Host "Graxia daemon STOPPED" -ForegroundColor Red
    }
} elseif ($Stop) {
    Stop-Daemon
} elseif ($Restart) {
    Stop-Daemon
    Start-Sleep -Seconds 2
    Start-Daemon
} else {
    Start-Daemon
}
