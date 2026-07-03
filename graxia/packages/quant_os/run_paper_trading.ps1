<#
.SYNOPSIS
    Paper Trading Wrapper — auto-restart on MT5 disconnect
.DESCRIPTION
    Runs run_paper_trading.py in 24h chunks with auto-restart.
    - Ensures Pepperstone terminal64 is the ONLY running terminal
    - Restarts terminal + script on IPC timeout or any crash
    - Creates/checks stop flag for clean shutdown
    - Logs everything to logs/wrapper_{timestamp}.log
#>

param(
    [int]$DurationMinutes = 1440,       # 24h per chunk
    [string]$LogDir = "logs",
    [string]$StopFlag = "logs\STOP_PAPER_TRADING"
)

$ErrorActionPreference = "Continue"
$Python = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
$Script = Join-Path $PSScriptRoot "run_paper_trading.py"
$TerminalPath = "C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
$StartTime = Get-Date

# Ensure log dir
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$LogFile = Join-Path $LogDir "wrapper_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$StopFlagPath = Join-Path $PSScriptRoot $StopFlag

function Write-Log {
    param([string]$Msg)
    $Line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line
}

function Remove-StopFlag {
    if (Test-Path $StopFlagPath) {
        Remove-Item $StopFlagPath -Force
        Write-Log "Removed existing stop flag"
    }
}

function Ensure-Terminal {
    Write-Log "Ensuring Pepperstone terminal is running (and only one)..."
    # Kill ALL terminal64 processes
    Get-Process -Name terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 3

    # Start Pepperstone terminal
    Start-Process $TerminalPath -WindowStyle Normal
    Write-Log "Started Pepperstone terminal, waiting 20s for sync..."
    Start-Sleep 20

    # Verify it's running
    $procs = Get-Process -Name terminal64 -ErrorAction SilentlyContinue
    if (-not $procs) {
        Write-Log "CRITICAL: Terminal failed to start!"
        return $false
    }
    if ($procs.Count -gt 1) {
        Write-Log "WARNING: $($procs.Count) terminals running (expected 1)"
    }
    Write-Log "Terminal OK: PID=$($procs[0].Id)"
    return $true
}

# Remove old stop flag if present
Remove-StopFlag

Write-Log "=" x 60
Write-Log "Paper Trading Wrapper — starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Log "Duration per chunk: $DurationMinutes min"
Write-Log "Stop flag: $StopFlagPath"
Write-Log "Log: $LogFile"
Write-Log "=" x 60

$cycle = 0
while ($true) {
    # Check stop flag
    if (Test-Path $StopFlagPath) {
        Write-Log "Stop flag detected — shutting down"
        break
    }

    $cycle++
    Write-Log "`n--- Cycle $cycle at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---"

    # Ensure terminal is running
    $ok = Ensure-Terminal
    if (-not $ok) {
        Write-Log "Terminal start failed, retrying in 30s..."
        Start-Sleep 30
        continue
    }

    # Run paper trading
    Write-Log "Launching paper trading (--duration $DurationMinutes)..."
    $repoRoot = "C:\Users\menum\graxia os"
    Push-Location $repoRoot
    $outFile = Join-Path $LogDir "cycle_${cycle}_out.txt"
    $errFile = Join-Path $LogDir "cycle_${cycle}_err.txt"
    $exitCode = 0
    try {
        $output = & $Python -u $Script "--duration" $DurationMinutes 2>&1
        $exitCode = $LASTEXITCODE
        $output | Out-File -FilePath $outFile -Encoding utf8
    } catch {
        $exitCode = 1
        Write-Log "Exception: $_"
        $_ | Out-File -FilePath $errFile -Encoding utf8
    }
    Pop-Location

    Write-Log "Script exited with code $exitCode"

    if ($exitCode -eq 0) {
        Write-Log "Clean exit (duration completed). Restarting next cycle..."
        continue
    }

    # Non-zero — likely IPC or connection error
    Write-Log "Non-zero exit. Will restart terminal + script."
    Get-Process -Name terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 10
}

Write-Log "`n=== Wrapper ended at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Total elapsed: $([math]::Round(((Get-Date) - $StartTime).TotalHours, 1)) hours"
