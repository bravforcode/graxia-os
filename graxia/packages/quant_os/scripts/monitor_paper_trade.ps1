# XAUUSD TSM Paper Trade — Status Monitor
# Shows current position, P&L, and progress toward 60-day requirement

$ErrorActionPreference = "Stop"

# Paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateFile = Join-Path (Split-Path -Parent $scriptDir) "artifacts\paper_trade_xauusd\state.json"
$csvFile = Join-Path (Split-Path -Parent $scriptDir) "artifacts\paper_trade_xauusd\trade_log.csv"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "XAUUSD TSM Paper Trading Monitor" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Check MT5 connection
try {
    & python -c "
import MetaTrader5 as mt5
mt5.initialize()
info = mt5.account_info()
if info:
    print('MT5 Account:', info.server, '| Login:', info.login)
    print('Equity:', round(info.equity, 2))
    print('Balance:', round(info.balance, 2))
    print()
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            direction = 'BUY' if pos.type == 0 else 'SELL'
            print('Position:', pos.symbol, direction, pos.volume, 'lots')
            print('  Entry:', pos.price_open, '| Current:', pos.price_current)
            print('  P&L:', round(pos.profit, 2), '| Swap:', round(pos.swap, 2))
    else:
        print('No open positions')
else:
    print('Cannot read MT5 account')
mt5.shutdown()
" 2>&1
} catch {
    Write-Host "Cannot connect to MT5" -ForegroundColor Red
}

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Gray

# Check paper trading state
if (Test-Path $stateFile) {
    $state = Get-Content $stateFile | ConvertFrom-Json
    $startDate = [DateTime]::Parse($state.start_date)
    $daysElapsed = ((Get-Date).ToUniversalTime() - $startDate).Days

    Write-Host ""
    Write-Host "Paper Trading Progress:" -ForegroundColor Yellow
    Write-Host "  Start Date: $($startDate.ToString('yyyy-MM-dd'))"
    Write-Host "  Days: $daysElapsed / 60"
    Write-Host "  Trades: $($state.total_trades) / 100"
    Write-Host "  Initial Equity: $($state.initial_equity)"
    Write-Host "  Current Equity: $($state.current_equity)"
    Write-Host "  Total P&L: $($state.total_pnl)"
    Write-Host "  Max Drawdown: $([math]::Round($state.max_drawdown * 100, 2))%"
    Write-Host "  Position: $($state.position_direction) $($state.position_lots) lots"

    if ($daysElapsed -ge 60 -and $state.total_trades -ge 100) {
        Write-Host ""
        Write-Host "  [COMPLETE] Paper trading requirement met!" -ForegroundColor Green
    } else {
        $daysRemaining = [math]::Max(0, 60 - $daysElapsed)
        $tradesRemaining = [math]::Max(0, 100 - $state.total_trades)
        Write-Host ""
        Write-Host "  [IN PROGRESS] $daysRemaining days remaining, $tradesRemaining trades remaining" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "No paper trading state found. Run first rebalance first." -ForegroundColor Red
}

# Show recent trades
if (Test-Path $csvFile) {
    Write-Host ""
    Write-Host "Recent Trades:" -ForegroundColor Yellow
    $trades = Import-Csv $csvFile | Select-Object -Last 5
    foreach ($trade in $trades) {
        Write-Host "  $($trade.timestamp) | $($trade.action) | $($trade.lots) lots | P&L: $($trade.pnl)"
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
