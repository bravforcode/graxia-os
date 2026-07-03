# start_services_auto.ps1 — Auto-start TV MCP + PixelRAG
$ErrorActionPreference = "Continue"

$idxDir = "C:\Users\menum\graxia os\graxia\packages\quant_os\data\visual_index"
$articlesJson = "$idxDir\articles.json"

Write-Host "Starting PixelRAG on port 30002..."
$proc = Start-Process -FilePath "pixelrag" -ArgumentList "serve", "--index-dir", "`"$idxDir`"", "--articles-json", "`"$articlesJson`"", "--port", "30002", "--device", "cpu" -PassThru -NoNewWindow
Write-Host "PixelRAG PID: $($proc.Id)"

Start-Sleep -Seconds 20

Write-Host "`n=== Process ==="
Get-Process -Id $proc.Id -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime | Format-Table

Write-Host "`n=== Port ==="
netstat -aon | Select-String "3000[12].*LISTENING"

Write-Host "`n=== Health ==="
try { $r = Invoke-WebRequest -Uri "http://localhost:30002/health" -TimeoutSec 5 -ErrorAction Stop; Write-Host "PixelRAG: HTTP $($r.StatusCode)" -ForegroundColor Green } catch { Write-Host "PixelRAG: $($_.Exception.Message)" -ForegroundColor Yellow }
try { $r = Invoke-WebRequest -Uri "http://localhost:30001" -TimeoutSec 5 -ErrorAction Stop; Write-Host "TV MCP: HTTP $($r.StatusCode)" -ForegroundColor Green } catch { Write-Host "TV MCP: $($_.Exception.Message)" -ForegroundColor Yellow }
