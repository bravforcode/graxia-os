# start-pipeline.ps1 — Launch full vault pipeline
# Starts: vault-watcher + continuous-sync + initial dashboard refresh

param(
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain",
    [switch]$Daemon,
    [switch]$Status,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$pipelineDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$triggerDir = "$env:USERPROFILE\.graxia"
$logDir = $triggerDir

# Ensure dirs
New-Item -ItemType Directory -Force -Path $triggerDir | Out-Null

$watcherPidFile = Join-Path $triggerDir "vault-watcher.pid"
$syncPidFile = Join-Path $triggerDir "continuous-sync.pid"

function Write-Status {
    Write-Host "`n  Vault Pipeline Status" -ForegroundColor Cyan
    Write-Host "  =====================" -ForegroundColor Cyan

    # Check watchers
    $watcherRunning = $false
    $syncRunning = $false

    if (Test-Path $watcherPidFile) {
        $procId = Get-Content $watcherPidFile
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $watcherRunning = $proc -ne $null
        Write-Host "  Vault Watcher: $(if($watcherRunning){'RUNNING (PID '+$procId+')'}else{'STOPPED'})" -ForegroundColor $(if($watcherRunning){'Green'}else{'Red'})
    } else {
        Write-Host "  Vault Watcher: NOT STARTED" -ForegroundColor Red
    }

    if (Test-Path $syncPidFile) {
        $procId = Get-Content $syncPidFile
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $syncRunning = $proc -ne $null
        Write-Host "  Sync Daemon:   $(if($syncRunning){'RUNNING (PID '+$procId+')'}else{'STOPPED'})" -ForegroundColor $(if($syncRunning){'Green'}else{'Red'})
    } else {
        Write-Host "  Sync Daemon:   NOT STARTED" -ForegroundColor Red
    }

    # State info
    $stateFile = Join-Path $triggerDir "sync-state.json"
    if (Test-Path $stateFile) {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        Write-Host "`n  Last Graphify:    $($state.last_graphify)" -ForegroundColor Gray
        Write-Host "  Last Brain Sync:  $($state.last_brain_sync)" -ForegroundColor Gray
        Write-Host "  Total Syncs:      $($state.total_syncs)" -ForegroundColor Gray
        Write-Host "  Files Processed:  $($state.total_files_processed)" -ForegroundColor Gray
    }

    # MCP status
    Write-Host "`n  MCP Servers:" -ForegroundColor Yellow
    $configFile = "$env:USERPROFILE\.config\opencode\opencode.json"
    if (Test-Path $configFile) {
        $config = Get-Content $configFile -Raw | ConvertFrom-Json
        foreach ($prop in $config.mcp.PSObject.Properties) {
            $status = if ($prop.Value.enabled) { "ON" } else { "OFF" }
            $color = if ($prop.Value.enabled) { "Green" } else { "Red" }
            Write-Host "    $($prop.Name): $status" -ForegroundColor $color
        }
    }

    Write-Host ""
}

function Stop-Pipeline {
    Write-Host "`n  Stopping pipeline..." -ForegroundColor Yellow

    if (Test-Path $watcherPidFile) {
        $procId = Get-Content $watcherPidFile
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Remove-Item $watcherPidFile -Force -ErrorAction SilentlyContinue
        Write-Host "  Vault Watcher stopped" -ForegroundColor Green
    }

    if (Test-Path $syncPidFile) {
        $procId = Get-Content $syncPidFile
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Remove-Item $syncPidFile -Force -ErrorAction SilentlyContinue
        Write-Host "  Sync Daemon stopped" -ForegroundColor Green
    }

    Write-Host "  Pipeline stopped.`n" -ForegroundColor Green
}

function Start-Pipeline {
    Write-Host "`n  Starting Vault Pipeline..." -ForegroundColor Cyan
    Write-Host "  Vault: $VaultPath" -ForegroundColor Gray
    Write-Host "  Logs:  $logDir" -ForegroundColor Gray

    # Run initial dashboard refresh
    Write-Host "`n  [1/4] Dashboard refresh..." -ForegroundColor Yellow
    & "$pipelineDir\dashboard-refresh.ps1" -VaultPath $VaultPath

    # Start vault watcher in background
    Write-Host "`n  [2/4] Starting vault watcher..." -ForegroundColor Yellow
    $watcherJob = Start-Process -FilePath "pwsh" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$pipelineDir\vault-watcher.ps1`" -VaultPath `"$VaultPath`"" `
        -PassThru -WindowStyle Minimized
    $watcherJob.Id | Out-File $watcherPidFile
    Write-Host "  Vault Watcher started (PID: $($watcherJob.Id))" -ForegroundColor Green

    # Start sync daemon in background
    Write-Host "`n  [3/4] Starting sync daemon..." -ForegroundColor Yellow
    $syncJob = Start-Process -FilePath "pwsh" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$pipelineDir\continuous-sync.ps1`" -VaultPath `"$VaultPath`"" `
        -PassThru -WindowStyle Minimized
    $syncJob.Id | Out-File $syncPidFile
    Write-Host "  Sync Daemon started (PID: $($syncJob.Id))" -ForegroundColor Green

    # Initial brain sync
    Write-Host "`n  [4/4] Initial brain sync..." -ForegroundColor Yellow
    $brainSource = Join-Path $VaultPath "brain\latest.md"
    if (Test-Path $brainSource) {
        $brain = Get-Content -Raw $brainSource
        $wrapped = "<!--BRAIN_SNAPSHOT_START-->`n$brain`n<!--BRAIN_SNAPSHOT_END-->"
        $targets = @("$env:USERPROFILE\.codex\AGENTS.md", "$env:USERPROFILE\.gemini\GEMINI.md", "$env:USERPROFILE\.claude\CLAUDE.md")
        foreach ($t in $targets) {
            if (Test-Path $t) {
                Write-Host "    Synced: $t" -ForegroundColor Gray
            }
        }
    }

    Write-Host "`n  ============================" -ForegroundColor Green
    Write-Host "  Pipeline is RUNNING" -ForegroundColor Green
    Write-Host "  ============================" -ForegroundColor Green
    Write-Host "  Commands:" -ForegroundColor Gray
    Write-Host "    .\start-pipeline.ps1 -Status   # Check status" -ForegroundColor Gray
    Write-Host "    .\start-pipeline.ps1 -Stop      # Stop all" -ForegroundColor Gray
    Write-Host ""

    # Keep terminal alive if not daemon mode
    if (-not $Daemon) {
        Write-Host "  Press Ctrl+C to stop..." -ForegroundColor Gray
        try {
            while ($true) { Start-Sleep -Seconds 30 }
        } finally {
            Stop-Pipeline
        }
    }
}

# === ROUTER ===
if ($Stop) {
    Stop-Pipeline
} elseif ($Status) {
    Write-Status
} else {
    Start-Pipeline
}
