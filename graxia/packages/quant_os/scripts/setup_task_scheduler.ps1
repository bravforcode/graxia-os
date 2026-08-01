# Windows Task Scheduler Setup for Quant OS
# Run this script as Administrator to create scheduled tasks

$PYTHON = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
$GRAXIA_ROOT = "C:\Users\menum\graxia os"
$QUANT_OS = "$GRAXIA_ROOT\graxia\packages\quant_os"

# Task 1: Spread Measurement (runs every 60 seconds)
$SpreadAction = New-ScheduledTaskAction -Execute $PYTHON -Argument "graxia/packages/quant_os/scripts/measure_spread.py --interval 60 --symbols XAUUSD,EURUSD,GBPUSD,BTCUSD" -WorkingDirectory $GRAXIA_ROOT
$SpreadTrigger = New-ScheduledTaskTrigger -AtStartup
$SpreadSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
$SpreadPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName "QuantOS-SpreadMeasurement" -Action $SpreadAction -Trigger $SpreadTrigger -Settings $SpreadSettings -Principal $SpreadPrincipal -Description "Quant OS Spread Measurement - 7 day data collection"

# Task 2: Paper Trade Bot (runs at startup, restarts on failure)
$PaperAction = New-ScheduledTaskAction -Execute $PYTHON -Argument "graxia/packages/quant_os/scripts/paper_trade_bot.py" -WorkingDirectory $GRAXIA_ROOT
$PaperTrigger = New-ScheduledTaskTrigger -AtStartup
$PaperSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 5) -RestartCount 5
$PaperPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName "QuantOS-PaperTradeBot" -Action $PaperAction -Trigger $PaperTrigger -Settings $PaperSettings -Principal $PaperPrincipal -Description "Quant OS Paper Trade Bot - 60 day validation"

Write-Host "Tasks created successfully!"
Write-Host "  - QuantOS-SpreadMeasurement: Runs every 60 seconds"
Write-Host "  - QuantOS-PaperTradeBot: Runs at startup, restarts on failure"
Write-Host ""
Write-Host "To verify: Get-ScheduledTask -TaskName 'QuantOS-*'"
Write-Host "To remove: Unregister-ScheduledTask -TaskName 'QuantOS-SpreadMeasurement'"
