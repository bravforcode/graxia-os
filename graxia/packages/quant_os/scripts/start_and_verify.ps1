# start_and_verify.ps1 — Start PixelRAG and verify both services
$ErrorActionPreference = "Continue"
$idxDir = "C:\Users\menum\graxia os\graxia\packages\quant_os\data\visual_index"
$articlesJson = "$idxDir\articles.json"

Write-Host "Starting PixelRAG on port 30002..."
$proc = Start-Process -FilePath "pixelrag" -ArgumentList "serve", "--index-dir", "`"$idxDir`"", "--articles-json", "`"$articlesJson`"", "--port", "30002", "--device", "cpu" -PassThru -NoNewWindow
Write-Host "PixelRAG PID: $($proc.Id)" -ForegroundColor Green

Start-Sleep -Seconds 20

Write-Host "`n=== Process ==="
Get-Process -Id $proc.Id -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime | Format-Table

Write-Host "=== Port ==="
netstat -aon | Select-String "3000[12].*LISTENING"

Write-Host "=== Health ==="
try { $r = Invoke-WebRequest -Uri "http://localhost:30002/health" -TimeoutSec 5 -ErrorAction Stop; Write-Host "PixelRAG: UP HTTP $($r.StatusCode)" -ForegroundColor Green } catch { Write-Host "PixelRAG: DOWN" -ForegroundColor Red }
try { $r = Invoke-WebRequest -Uri "http://localhost:30001" -TimeoutSec 5 -ErrorAction Stop; Write-Host "TV MCP: UP HTTP $($r.StatusCode)" -ForegroundColor Green } catch { Write-Host "TV MCP: HTTP Response" -ForegroundColor Yellow }
