$ErrorActionPreference = "Stop"

# Kill existing
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 5

# Start MT5
Start-Process "C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe" -ArgumentList "/login:61547941","/password:Graxia-12345Ghr","/server:Pepperstone-Demo"
Write-Host "MT5 starting..."
Start-Sleep -Seconds 60

# Start bot — use & operator to invoke python with quoted paths
$workDir = "C:\Users\menum\graxia os"
$botScript = Join-Path $workDir "graxia\packages\quant_os\gold_bot\run_paper.py"
$logDir = Join-Path $workDir "graxia\packages\quant_os\logs"
$logFile = Join-Path $logDir "paper_7day.log"
$errFile = Join-Path $logDir "paper_7day_err.log"
$pidFile = Join-Path $logDir "paper_7day.pid"

# Use cmd /c to handle spaces in path properly
$cmdArgs = "/c python -u `"$botScript`" --duration 168 --capital 49911.92 --risk 0.25 > `"$logFile`" 2> `"$errFile`""
$p = Start-Process cmd.exe -ArgumentList $cmdArgs -WorkingDirectory $workDir -WindowStyle Hidden -PassThru

$p.Id | Out-File $pidFile -NoNewline
Write-Host "Bot started! PID=$($p.Id)"
Write-Host "Log: $logFile"
Write-Host "Stop: taskkill /PID $($p.Id) /F"
