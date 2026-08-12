# Auto-elevate to admin
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs -PassThru
    $proc.WaitForExit()
    exit $proc.ExitCode
}

$ErrorActionPreference = "Stop"

# Python full path
$PYTHON = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
Write-Host "[OK] Python: $PYTHON" -ForegroundColor Green

# Set OBSIDIAN_VAULT_PATH
$env:OBSIDIAN_VAULT_PATH = "C:\Users\menum\quant\quant bot"
[System.Environment]::SetEnvironmentVariable("OBSIDIAN_VAULT_PATH", "C:\Users\menum\quant\quant bot", "User")
Write-Host "[OK] OBSIDIAN_VAULT_PATH = C:\Users\menum\quant\quant bot" -ForegroundColor Green

# Remove ALL old Graxia tasks
$existing = Get-ScheduledTask -TaskName "Graxia*" -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($task in $existing) {
        Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false
        Write-Host "[DEL] Removed: $($task.TaskName)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] No old tasks found" -ForegroundColor Gray
}

# Task definitions
$tasks = @(
    @{
        Name = "Graxia-Data-Download"
        Mode = "data"
        Desc = "Download market data every 15 min"
        Trigger = "OnceEvery15Min"
        Interval = 15
    },
    @{
        Name = "Graxia-Bridge-Sync"
        Mode = "sync"
        Desc = "Sync bridge every 15 min"
        Trigger = "OnceEvery15Min"
        Interval = 15
    },
    @{
        Name = "Graxia-Bridge-Upgrade"
        Mode = "upgrade"
        Desc = "Upgrade pipeline every 6h"
        Trigger = "OnceEvery6h"
        Interval = 360
    },
    @{
        Name = "Graxia-Bridge-Upgrade-Quick"
        Mode = "upgrade-q"
        Desc = "Quick upgrade every 2h"
        Trigger = "OnceEvery2h"
        Interval = 120
    },
    @{
        Name = "Graxia-Bridge-Daily"
        Mode = "full"
        Desc = "Daily full bridge at 03:00"
        Trigger = "Daily0300"
        Interval = $null
    },
    @{
        Name = "Graxia-Bridge-Research"
        Mode = "pull-only"
        Desc = "Daily research pull at 04:00"
        Trigger = "Daily0400"
        Interval = $null
    }
)

$scriptPath = "C:\Users\menum\graxia os\graxia\packages\quant_os\scripts\bridge_automated_sync.py"

foreach ($task in $tasks) {
    Write-Host "`n--- Creating: $($task.Name) ---" -ForegroundColor Cyan
    Write-Host "  Desc: $($task.Desc)"
    Write-Host "  Mode: $($task.Mode)"

    $action = New-ScheduledTaskAction -Execute $PYTHON -Argument "`"$scriptPath`" --mode $($task.Mode)" -WorkingDirectory "C:\Users\menum\graxia os\graxia\packages\quant_os"

    $trigger = $null
    if ($task.Trigger -eq "Daily0300") {
        $trigger = New-ScheduledTaskTrigger -Daily -At "03:00"
    } elseif ($task.Trigger -eq "Daily0400") {
        $trigger = New-ScheduledTaskTrigger -Daily -At "04:00"
    } else {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
            -RepetitionInterval (New-TimeSpan -Minutes $task.Interval) `
            -RepetitionDuration (New-TimeSpan -Days 365)
    }

    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    $principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$env:USERNAME" -LogonType S4U -RunLevel Highest

    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -Description $task.Desc

    Write-Host "[OK] Created: $($task.Name)" -ForegroundColor Green
}

# Verify all tasks
Write-Host "`n=== VERIFICATION ===" -ForegroundColor Magenta
Get-ScheduledTask -TaskName "Graxia*" | Select-Object TaskName, State, @{N='NextRun';E={($_.Triggers[0].StartBoundary)}} | Format-Table -AutoSize

$allGood = (Get-ScheduledTask -TaskName "Graxia*").Count -eq 6
if ($allGood) {
    Write-Host "`n[SUCCESS] All 6 tasks created and verified!" -ForegroundColor Green
} else {
    Write-Host "`n[WARN] Expected 6 tasks, found $((Get-ScheduledTask -TaskName "Graxia*").Count)" -ForegroundColor Yellow
}

Write-Host "`nPress any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
