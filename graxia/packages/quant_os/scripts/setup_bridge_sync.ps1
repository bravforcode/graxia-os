<#
.SYNOPSIS
    Setup bridge_automated_sync.py as a Windows Scheduled Task.

.DESCRIPTION
    Creates a scheduled task that runs bridge_automated_sync.py periodically,
    syncing quant_OS states, backtest results, strategy configs, and
    codebase graph into the Obsidian Second Brain vault.

    Upgrades installed:
      🥇 Meta/states/ → vault (every 30 min)
      🥈 Backtest results → vault inbox (on trigger)
      🥉 Strategy/risk config mirror → vault (daily)
      ④ Knowledge graph sync → vault (daily)
      ⑤ NotebookLM research pipeline → vault research (daily at 04:00)

.PARAMETER IntervalMinutes
    How often to run the full sync (default: 30)

.PARAMETER VaultPath
    Path to Obsidian vault (default: auto-detect from env or default location)

.EXAMPLE
    .\setup_bridge_sync.ps1
    .\setup_bridge_sync.ps1 -IntervalMinutes 15
#>

param(
    [int]$IntervalMinutes = 15,
    [string]$VaultPath = ""
)

$ErrorActionPreference = "Stop"

# ─── Auto-elevate if not admin ──────────────────────────────────────────
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Not running as Administrator. Re-launching with elevation..." -ForegroundColor Yellow
    $ps1 = $PSCommandPath
    if (-not $ps1) { $ps1 = $MyInvocation.MyCommand.Path }
    $args = "-ExecutionPolicy Bypass -File `"$ps1`""
    $psi = New-Object System.Diagnostics.ProcessStartInfo("powershell.exe", $args)
    $psi.Verb = "runas"
    $psi.WorkingDirectory = $PWD
    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($proc) {
        Write-Host "Elevated shell launched. This window will close." -ForegroundColor Green
        Start-Sleep -Seconds 2
    } else {
        Write-Error "Failed to elevate. Please run this script as Administrator manually."
    }
    exit
}

Write-Host "Running with Administrator privileges." -ForegroundColor Green

# ─── Resolve paths ──────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $PSCommandPath
$QuantOsRoot = Resolve-Path (Join-Path $ScriptDir "..")
$OrchestratorScript = Join-Path $ScriptDir "run_bridge.ps1"
$PythonExe = (Get-Command python).Source

if (-not $VaultPath) {
    $VaultPath = [Environment]::GetEnvironmentVariable("OBSIDIAN_VAULT_PATH", "User")
    if (-not $VaultPath) {
        $VaultPath = "$env:USERPROFILE\Documents\ObsidianVault\Second Brain"
    }
}

# ─── Validate ───────────────────────────────────────────────────────────
if (-not (Test-Path $SyncScript)) {
    Write-Error "Sync script not found: $SyncScript"
    exit 1
}

if (-not (Test-Path $VaultPath)) {
    Write-Warning "Vault not found at: $VaultPath"
    Write-Warning "The task will be created but will fail until the vault path is valid."
}

Write-Host "=== Bridge Sync Setup ===" -ForegroundColor Cyan
Write-Host "Script:     $SyncScript"
Write-Host "Python:     $PythonExe"
Write-Host "Vault:      $VaultPath"
Write-Host "Interval:   ${IntervalMinutes}min"
Write-Host "quant_OS:   $QuantOsRoot"
Write-Host ""

# ─── Set OBSIDIAN_VAULT_PATH in user env ────────────────────────────────
[Environment]::SetEnvironmentVariable("OBSIDIAN_VAULT_PATH", $VaultPath, "User")
Write-Host "[OK] OBSIDIAN_VAULT_PATH set to: $VaultPath" -ForegroundColor Green

# ─── Run initial sync ───────────────────────────────────────────────────
Write-Host "`n>>> Running initial sync..." -ForegroundColor Yellow
& $PythonExe $SyncScript
Write-Host ""

# ─── Create scheduled task ──────────────────────────────────────────────
$TaskName = "Graxia-Bridge-Sync"
$TaskDesc = "Ruflow/Gracia Bridge: sync quant_OS states, backtest, configs, graph to Obsidian vault"

# Build action: run orchestrator with -Mode sync
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode sync" `
    -WorkingDirectory $QuantOsRoot

# Build trigger: every IntervalMinutes
# IMPORTANT: Use future time (now + 5 min) so the first trigger fires properly
$StartTime = (Get-Date).AddMinutes(5)
$Trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 365) `
    -At $StartTime `
    -Once

# Run as current user, only when logged on
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

# Register
try {
    $Task = Register-ScheduledTask `
        -TaskName $TaskName `
        -Description $TaskDesc `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Force

    Write-Host "[OK] Scheduled task '$TaskName' created." -ForegroundColor Green
    Write-Host "    Runs every ${IntervalMinutes}min starting at $((Get-Date).AddMinutes(1).ToString('HH:mm'))."
}
catch {
    Write-Error "Failed to create scheduled task: $_"
    Write-Host ""
    Write-Host "Try running PowerShell as Administrator, then re-run this script."
    exit 1
}

# ─── Data-only sync (every 15 min) ────────────────────────────────────
$DataSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$DataTaskName = "Graxia-Data-Download"
$DataAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode data" `
    -WorkingDirectory $QuantOsRoot

$DataTrigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 365) `
    -At (Get-Date).AddMinutes(5) `
    -Once

try {
    Register-ScheduledTask `
        -TaskName $DataTaskName `
        -Description "Graxia data download: pull OHLCV every 15min from MT5 for all symbols/TFs" `
        -Action $DataAction `
        -Trigger $DataTrigger `
        -Principal $Principal `
        -Settings $DataSettings `
        -Force | Out-Null
    Write-Host "[OK] Task '$DataTaskName' created (every 15min)." -ForegroundColor Green
}
catch {
    Write-Error "Failed to create data task: $_"
}

# ─── Full upgrade pipeline (every 6 hours) ─────────────────────────────
$UpgradeSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
$UpgradeTaskName = "Graxia-Bridge-Upgrade"
$UpgradeAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode upgrade" `
    -WorkingDirectory $QuantOsRoot

$UpgradeTrigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Hours 6) `
    -RepetitionDuration (New-TimeSpan -Days 365) `
    -At (Get-Date).AddMinutes(5) `
    -Once

try {
    Register-ScheduledTask `
        -TaskName $UpgradeTaskName `
        -Description "Graxia full upgrade pipeline: data + features + ML + backtest + NotebookLM + report" `
        -Action $UpgradeAction `
        -Trigger $UpgradeTrigger `
        -Principal $Principal `
        -Settings $UpgradeSettings `
        -Force | Out-Null
    Write-Host "[OK] Task '$UpgradeTaskName' created (every 6h)." -ForegroundColor Green
}
catch {
    Write-Error "Failed to create upgrade task: $_"
}

# ─── Quick upgrade (every 2 hours) ─────────────────────────────────────
$QuickTaskName = "Graxia-Bridge-Upgrade-Quick"
$QuickAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode upgrade-q" `
    -WorkingDirectory $QuantOsRoot

$QuickTrigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Days 365) `
    -At (Get-Date).AddMinutes(5) `
    -Once

try {
    Register-ScheduledTask `
        -TaskName $QuickTaskName `
        -Description "Graxia quick upgrade: data + backtest every 2h (skip ML)" `
        -Action $QuickAction `
        -Trigger $QuickTrigger `
        -Principal $Principal `
        -Settings $DataSettings `
        -Force | Out-Null
    Write-Host "[OK] Task '$QuickTaskName' created (every 2h)." -ForegroundColor Green
}
catch {
    Write-Error "Failed to create quick upgrade task: $_"
}

# ─── Full daily run (sync + research at 03:00) ────────────────────────
$DailyTaskName = "Graxia-Bridge-Daily"
$DailyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode full" `
    -WorkingDirectory $QuantOsRoot

# Run daily at 03:00 (includes sync + research)
$DailyTrigger = New-ScheduledTaskTrigger -Daily -At 03:00

try {
    $DailyTask = Register-ScheduledTask `
        -TaskName $DailyTaskName `
        -Description "Graxia Bridge full daily run: sync + NotebookLM research" `
        -Action $DailyAction `
        -Trigger $DailyTrigger `
        -Principal $Principal `
        -Settings $Settings `
        -Force

    Write-Host "[OK] Daily task '$DailyTaskName' created." -ForegroundColor Green
    Write-Host "    Runs daily at 03:00 (full sync + research)."
}
catch {
    Write-Error "Failed to create daily task: $_"
}

# ─── NotebookLM research pipeline (daily at 04:00) ──────────────────────
$NbTaskName = "Graxia-Bridge-Research"
$NbAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$OrchestratorScript`" -Mode pull-only" `
    -WorkingDirectory $QuantOsRoot

$NbTrigger = New-ScheduledTaskTrigger -Daily -At 04:00

try {
    $NbTask = Register-ScheduledTask `
        -TaskName $NbTaskName `
        -Description "Graxia NotebookLM research pipeline: pull insights from NotebookLM to vault" `
        -Action $NbAction `
        -Trigger $NbTrigger `
        -Principal $Principal `
        -Settings $Settings `
        -Force

    Write-Host "[OK] Research task '$NbTaskName' created." -ForegroundColor Green
    Write-Host "    Runs daily at 04:00."
    Write-Host "    [NOTE] Run 'notebooklm login' once for auth before first run." -ForegroundColor Yellow
}
catch {
    Write-Error "Failed to create research task: $_"
}

# ─── Verify ─────────────────────────────────────────────────────────────
Write-Host "`n=== Verification ===" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "Graxia-Bridge*" | Format-Table TaskName, State, NextRunTime -AutoSize

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "The bridge is now fully automated:"
Write-Host "  Data pull             +15min   (via Graxia-Data-Download)"
Write-Host "  States sync            +15min   (via Graxia-Bridge-Sync)"
Write-Host "  Quick upgrade          +2h      (via Graxia-Bridge-Upgrade-Quick)"
Write-Host "  Full upgrade           +6h      (via Graxia-Bridge-Upgrade)"
Write-Host "  Full sync + research   -> 03:00  (via Graxia-Bridge-Daily)"
Write-Host "  Research pull-only     -> 04:00  (via Graxia-Bridge-Research)"
Write-Host ""
Write-Host "Data coverage: 15 symbols × 3-9 TFs = 56+ CSVs (~100 MB)"
Write-Host ""
Write-Host "Manual commands:"
Write-Host "  scripts\run_bridge.ps1 -Mode data        # data pull only (15 symbols × M15/H1/D1)"
Write-Host "  scripts\run_bridge.ps1 -Mode sync        # one-shot sync"
Write-Host "  scripts\run_bridge.ps1 -Mode upgrade     # full upgrade pipeline"
Write-Host "  scripts\run_bridge.ps1 -Mode upgrade-q   # quick upgrade (skip ML)"
Write-Host "  scripts\run_bridge.ps1 -Mode all         # sync + upgrade + research"
Write-Host "  scripts\run_bridge.ps1 -Mode research    # research pipeline"
Write-Host "  scripts\run_bridge.ps1 -Mode pull-only   # pull insights only"
