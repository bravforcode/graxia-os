<#
.SYNOPSIS
Start all trading bots
#>
$QuantOs = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "Starting XAUUSD Bot..." -ForegroundColor Cyan
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-u scripts/paper_trade_bot.py --interval 60" -WorkingDirectory $QuantOs -RedirectStandardOutput "$QuantOs\data\bot_xauusd.log" -RedirectStandardError "$QuantOs\data\bot_xauusd_err.log"

Write-Host "Starting Multi-Symbol Bot..." -ForegroundColor Green
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-u scripts/multi_symbol_bot.py" -WorkingDirectory $QuantOs -RedirectStandardOutput "$QuantOs\data\bot_multi.log" -RedirectStandardError "$QuantOs\data\bot_multi_err.log"

Write-Host "Both bots started in background."
Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, @{N='Args';E={$_.CommandLine}}
