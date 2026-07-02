<#
.SYNOPSIS
    Daily health check and expectancy report for the Quant OS shadow trading system.

.DESCRIPTION
    Runs a suite of daily checks:
      1. Verifies shadow process is alive (PID in state file)
      2. Checks DuckDB file exists and is growing
      3. Scans logs/shadow_error.log for recent errors
      4. Runs expectancy analysis via shadow_report.py
      5. Sends summary to Telegram

    Designed to be scheduled via Windows Task Scheduler.

.PARAMETER PythonPath
    Path to Python executable.  Defaults to "python".

.PARAMETER ProjectRoot
    Project root directory.  Auto-detected from script location.

.PARAMETER DryRun
    Print output without sending to Telegram.

.EXAMPLE
    .\daily_check.ps1
    .\daily_check.ps1 -DryRun
    .\daily_check.ps1 -PythonPath "C:\Python312\python.exe"
#>

param(
    [string]$PythonPath = "python",
    [string]$ProjectRoot = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------

if (-not $ProjectRoot) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $ProjectRoot = Resolve-Path "$scriptDir\.."
}

$stateFile     = Join-Path $ProjectRoot "state\shadow_state.json"
$dbPath        = Join-Path $ProjectRoot "data\market_data.duckdb"
$errorLog      = Join-Path $ProjectRoot "logs\shadow_error.log"
$reportScript  = Join-Path $ProjectRoot "monitoring\shadow_report.py"
$today         = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$results = @()

# ---------------------------------------------------------------------------
# 1. Shadow process check
# ---------------------------------------------------------------------------

$processAlive = $false
$pidInfo = ""

try {
    if (Test-Path $stateFile) {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        $shadowPid = $state.pid

        if ($shadowPid) {
            $proc = Get-Process -Id $shadowPid -ErrorAction SilentlyContinue
            if ($proc) {
                $processAlive = $true
                $pidInfo = "PID $shadowPid alive (started $($proc.StartTime))"
            } else {
                $pidInfo = "PID $shadowPid not running (stale state)"
            }
        } else {
            $pidInfo = "No PID in state file"
        }
    } else {
        $pidInfo = "State file not found"
    }
} catch {
    $pidInfo = "Error reading state: $_"
}

$processIcon = if ($processAlive) { "✅" } else { "⚠️" }
$results += "$processIcon <b>Shadow Process:</b> $pidInfo"

# ---------------------------------------------------------------------------
# 2. DuckDB health check
# ---------------------------------------------------------------------------

$dbStatus = ""

if (Test-Path $dbPath) {
    $dbInfo = Get-Item $dbPath
    $sizeMB = [math]::Round($dbInfo.Length / 1MB, 2)
    $age = (Get-Date) - $dbInfo.LastWriteTime

    $dbStatus = "Exists ($($sizeMB) MB, updated $([math]::Round($age.TotalMinutes, 0))m ago)"

    # Check if file is growing (modified in last 10 minutes)
    if ($age.TotalMinutes -lt 10) {
        $dbStatus += " — actively growing"
    }
} else {
    $dbStatus = "NOT FOUND at $dbPath"
}

$dbIcon = if (Test-Path $dbPath) { "✅" } else { "🔴" }
$results += "$dbIcon <b>DuckDB:</b> $dbStatus"

# ---------------------------------------------------------------------------
# 3. Error log check
# ---------------------------------------------------------------------------

$errorCount = 0
$errorSummary = ""

if (Test-Path $errorLog) {
    $cutoff = (Get-Date).AddHours(-24)
    $lines = Get-Content $errorLog -Tail 200

    foreach ($line in $lines) {
        # Try to extract timestamp from log lines like "2024-01-15 14:30:00 ..."
        if ($line -match "^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})") {
            try {
                $logTime = [DateTime]::ParseExact(
                    $matches[1], "yyyy-MM-dd HH:mm:ss",
                    [System.Globalization.CultureInfo]::InvariantCulture
                )
                if ($logTime -gt $cutoff) {
                    $errorCount++
                }
            } catch {
                # Ignore parse errors
            }
        }
    }

    if ($errorCount -gt 0) {
        $errorSummary = "$errorCount errors in last 24h (last 3 lines shown)"
        $lastErrors = Get-Content $errorLog -Tail 3 | ForEach-Object { "  $_" }
        $errorSummary += "`n" + ($lastErrors -join "`n")
    } else {
        $errorSummary = "No errors in last 24h"
    }
} else {
    $errorSummary = "Log file not found (no shadow activity yet?)"
}

$errIcon = if ($errorCount -gt 0) { "⚠️" } else { "✅" }
$results += "$errIcon <b>Error Log:</b> $errorSummary"

# ---------------------------------------------------------------------------
# 4. Expectancy analysis
# ---------------------------------------------------------------------------

$expectancyOutput = ""

if (Test-Path $reportScript) {
    try {
        $args = @($reportScript, "--db-path", $dbPath)
        if ($DryRun) {
            $args += "--dry-run"
        }
        $output = & $PythonPath @args 2>&1
        $expectancyOutput = $output -join "`n"
        $results += "📊 <b>Daily Report:</b>`n<pre>$expectancyOutput</pre>"
    } catch {
        $results += "🔴 <b>Report Error:</b> Failed to generate report: $_"
    }
} else {
    $results += "⚠️ <b>Report:</b> shadow_report.py not found at $reportScript"
}

# ---------------------------------------------------------------------------
# 5. System summary
# ---------------------------------------------------------------------------

$summary = @"
📋 <b>Quant OS Daily Health Check</b>
🕐 $today
━━━━━━━━━━━━━━━━━━━━━━━

$($results -join "`n`n")
━━━━━━━━━━━━━━━━━━━━━━━
"@

# ---------------------------------------------------------------------------
# 6. Send to Telegram
# ---------------------------------------------------------------------------

if ($DryRun) {
    Write-Host "=== DRY RUN — NOT SENDING ===" -ForegroundColor Yellow
    Write-Host ""
    Write-Host $summary
    Write-Host ""
    Write-Host "=== END DRY RUN ===" -ForegroundColor Yellow
    exit 0
}

# Load Telegram config
$token = $env:TELEGRAM_BOT_TOKEN
$chatId = $env:TELEGRAM_CHAT_ID

if (-not $token -or -not $chatId) {
    $configPath = Join-Path $ProjectRoot "scripts\telegram_config.toml"
    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw
        if ($config -match 'bot_token\s*=\s*"([^"]+)"') {
            $token = $matches[1]
        }
        if ($config -match 'chat_id\s*=\s*"([^"]+)"') {
            $chatId = $matches[1]
        }
    }
}

if (-not $token -or -not $chatId) {
    Write-Host "[ERROR] Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID." -ForegroundColor Red
    Write-Host ""
    Write-Host $summary
    exit 1
}

# Send via Telegram API
$apiUrl = "https://api.telegram.org/bot$token/sendMessage"
$body = @{
    chat_id = $chatId
    text = $summary
    parse_mode = "HTML"
    disable_web_page_preview = $true
} | ConvertTo-Json -Depth 5

try {
    $resp = Invoke-RestMethod -Uri $apiUrl -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
    if ($resp.ok) {
        Write-Host "[OK] Daily check sent to Telegram." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Telegram API returned ok=false" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[ERROR] Telegram send failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host $summary
}
