# Launch TradingView Desktop with CDP enabled
# Run this BEFORE starting the autonomous loop

Write-Host "=== TradingView Desktop CDP Launcher ===" -ForegroundColor Cyan

# Check if TradingView Desktop is installed
$tvPaths = @(
    "$env:LOCALAPPDATA\Programs\TradingView\TradingView.exe",
    "$env:ProgramFiles\TradingView\TradingView.exe",
    "${env:ProgramFiles(x86)}\TradingView\TradingView.exe"
)

$tvExe = $null
foreach ($p in $tvPaths) {
    if (Test-Path $p) {
        $tvExe = $p
        break
    }
}

if (-not $tvExe) {
    Write-Host "[ERROR] TradingView Desktop not found. Install from https://www.tradingview.com/desktop/" -ForegroundColor Red
    Write-Host "Alternative: Use Chrome with TradingView Web:" -ForegroundColor Yellow
    Write-Host '  & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug" "https://www.tradingview.com/chart/"' -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Found TradingView Desktop: $tvExe" -ForegroundColor Green
Write-Host "[INFO] Launching with --remote-debugging-port=9222 ..." -ForegroundColor Yellow

# Kill existing TradingView processes if any
Get-Process -Name "TradingView" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Launch with CDP flag
Start-Process -FilePath $tvExe -ArgumentList "--remote-debugging-port=9222" -WindowStyle Normal

Write-Host "[OK] TradingView Desktop launched with CDP on port 9222" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Login to your TradingView account" -ForegroundColor White
Write-Host "  2. Open chart for XAUUSD (or your first symbol)" -ForegroundColor White
Write-Host "  3. Run: python -m autonomous.orchestrator" -ForegroundColor White
