# PowerShell script to test Graxia OS setup
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "🚀 GRAXIA OS - QUICK TEST" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Test 1: Check vault
Write-Host "`n📁 Checking Obsidian Vault..." -ForegroundColor Yellow
$vaultPath = "C:\Users\menum\OneDrive\Documents\Gracia"
if (Test-Path $vaultPath) {
    Write-Host "   ✅ Vault exists: $vaultPath" -ForegroundColor Green
    $items = Get-ChildItem $vaultPath -ErrorAction SilentlyContinue | Select-Object -First 5
    Write-Host "   📂 Contents:" -ForegroundColor Gray
    $items | ForEach-Object { Write-Host "      - $($_.Name)" -ForegroundColor Gray }
} else {
    Write-Host "   ❌ Vault NOT found: $vaultPath" -ForegroundColor Red
    Write-Host "   🔧 Creating vault..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $vaultPath | Out-Null
    Write-Host "   ✅ Created" -ForegroundColor Green
}

# Create Second Brain folders
$folders = @(
    "$vaultPath\Second Brain",
    "$vaultPath\Second Brain\00-Inbox",
    "$vaultPath\Second Brain\01-Projects",
    "$vaultPath\Second Brain\02-Areas",
    "$vaultPath\Second Brain\03-Resources",
    "$vaultPath\Second Brain\04-Archive",
    "$vaultPath\Second Brain\90-System"
)

foreach ($folder in $folders) {
    if (!(Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}
Write-Host "   ✅ Second Brain structure ready" -ForegroundColor Green

# Test 2: Python connector
Write-Host "`n🐍 Testing Python Connector..." -ForegroundColor Yellow
$pythonTest = @"
import sys
sys.path.insert(0, 'backend')
from app.integrations.obsidian import build_obsidian_connector
connector = build_obsidian_connector()
if connector:
    print('OBSIDIAN_OK')
else:
    print('OBSIDIAN_FAIL')
"@

$result = python -c $pythonTest 2>&1
if ($result -contains "OBSIDIAN_OK") {
    Write-Host "   ✅ Obsidian connector working" -ForegroundColor Green
} else {
    Write-Host "   ❌ Obsidian connector failed" -ForegroundColor Red
    Write-Host "   Error: $result" -ForegroundColor Gray
}

# Test 3: Redis
Write-Host "`n🔌 Testing Redis..." -ForegroundColor Yellow
$redisTest = @"
import sys
sys.path.insert(0, 'backend')
from app.config import settings
import redis
try:
    r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()
    print('REDIS_OK')
except Exception as e:
    print(f'REDIS_FAIL: {e}')
"@

$result = python -c $redisTest 2>&1
if ($result -contains "REDIS_OK") {
    Write-Host "   ✅ Redis connected" -ForegroundColor Green
} else {
    Write-Host "   ❌ Redis failed" -ForegroundColor Red
    Write-Host "   Error: $result" -ForegroundColor Gray
}

Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "✅ TEST COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
