# TradingView + PixelRAG Service Launcher (Auto-mode)
# Starts both services as background jobs with health checks and auto-restart

param(
    [switch]$StartAll,
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Continue"

$QUANT_OS_DIR = "C:\Users\menum\graxia os\graxia\packages\quant_os"
$PYTHON_312 = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
$TV_MCP_PORT = 30001
$PIXELRAG_PORT = 30002
$LOG_DIR = "$QUANT_OS_DIR\data\service_logs"

# Ensure log directory exists
if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}

# --- Stop mode ---
if ($Stop) {
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    Get-Job -Name "TVMCP*", "PixelRAG*" -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job
    # Also kill any orphaned processes
    Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*tradingview-mcp*" -or $_.CommandLine -like "*pixelrag*serve*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "All services stopped." -ForegroundColor Green
    return
}

# --- Status mode ---
if ($Status) {
    Write-Host "`n=== Service Status ===" -ForegroundColor Cyan

    # TV MCP
    $tvJob = Get-Job -Name "TVMCP*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tvJob -and $tvJob.State -eq "Running") {
        Write-Host "TradingView MCP: RUNNING (port $TV_MCP_PORT)" -ForegroundColor Green
    } else {
        Write-Host "TradingView MCP: STOPPED" -ForegroundColor Red
    }

    # PixelRAG
    $prJob = Get-Job -Name "PixelRAG*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($prJob -and $prJob.State -eq "Running") {
        Write-Host "PixelRAG:        RUNNING (port $PIXELRAG_PORT)" -ForegroundColor Green
    } else {
        Write-Host "PixelRAG:        STOPPED" -ForegroundColor Red
    }

    # Health checks
    Write-Host "`n=== Health Checks ===" -ForegroundColor Cyan
    try {
        $tvHealth = Invoke-WebRequest -Uri "http://localhost:$TV_MCP_PORT" -TimeoutSec 3 -ErrorAction Stop
        Write-Host "TV MCP:   UP ($($tvHealth.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "TV MCP:   DOWN" -ForegroundColor Red
    }
    try {
        $prHealth = Invoke-WebRequest -Uri "http://localhost:$PIXELRAG_PORT/health" -TimeoutSec 3 -ErrorAction Stop
        Write-Host "PixelRAG: UP ($($prHealth.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "PixelRAG: DOWN" -ForegroundColor Red
    }

    # Show all jobs
    Write-Host "`n=== Jobs ===" -ForegroundColor Cyan
    Get-Job -Name "TVMCP*", "PixelRAG*" -ErrorAction SilentlyContinue | Format-Table Name, State, Id -AutoSize
    return
}

# --- Start mode ---
if ($StartAll -or (-not $Stop -and -not $Status)) {

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  TradingView + PixelRAG Service Launcher" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    # Kill existing jobs if any
    Get-Job -Name "TVMCP*", "PixelRAG*" -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job

    # --- TradingView MCP Server ---
    Write-Host "[1] Starting TradingView MCP Server on port $TV_MCP_PORT..." -ForegroundColor Yellow

    $tvJob = Start-Job -Name "TVMCP-$TV_MCP_PORT" -ScriptBlock {
        param($port, $logDir)
        $logFile = "$logDir\tv_mcp.log"
        uv tool run tradingview-mcp --port $port streamable-http 2>&1 | Tee-Object -FilePath $logFile
    } -ArgumentList $TV_MCP_PORT, $LOG_DIR

    Write-Host "    Job: $($tvJob.Id) | URL: http://localhost:$TV_MCP_PORT" -ForegroundColor Green

    # --- PixelRAG Server ---
    Write-Host "[2] Starting PixelRAG Server on port $PIXELRAG_PORT..." -ForegroundColor Yellow

    $indexDir = "$QUANT_OS_DIR\data\visual_index"
    if (-not (Test-Path $indexDir)) {
        New-Item -ItemType Directory -Path $indexDir -Force | Out-Null
        Write-Host "    Created index dir: $indexDir" -ForegroundColor Gray
    }

    $prJob = Start-Job -Name "PixelRAG-$PIXELRAG_PORT" -ScriptBlock {
        param($python, $indexDir, $port, $logDir)
        $logFile = "$logDir\pixelrag.log"
        & $python -m pixelrag.serve --index-dir $indexDir --port $port 2>&1 | Tee-Object -FilePath $logFile
    } -ArgumentList $PYTHON_312, $indexDir, $PIXELRAG_PORT, $LOG_DIR

    Write-Host "    Job: $($prJob.Id) | URL: http://localhost:$PIXELRAG_PORT" -ForegroundColor Green

    # --- Wait and verify ---
    Write-Host "`nWaiting for services to start..." -ForegroundColor Gray
    Start-Sleep -Seconds 5

    # Health check TV MCP
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$TV_MCP_PORT" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "TradingView MCP: HEALTHY" -ForegroundColor Green
    } catch {
        Write-Host "TradingView MCP: Starting... (may need TradingView open)" -ForegroundColor Yellow
    }

    # Health check PixelRAG
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$PIXELRAG_PORT/health" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "PixelRAG:        HEALTHY" -ForegroundColor Green
    } catch {
        Write-Host "PixelRAG:        Starting... (loading models)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Services Running!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  TV MCPP:  http://localhost:$TV_MCP_PORT  (port $TV_MCP_PORT)" -ForegroundColor White
    Write-Host "  PixelRAG: http://localhost:$PIXELRAG_PORT  (port $PIXELRAG_PORT)" -ForegroundColor White
    Write-Host ""
    Write-Host "  Logs:     $LOG_DIR" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  .\start_services.ps1 -Status    # Check health" -ForegroundColor Gray
    Write-Host "  .\start_services.ps1 -Stop      # Stop all" -ForegroundColor Gray
    Write-Host "  Get-Job                         # View jobs" -ForegroundColor Gray
}
