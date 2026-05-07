# Deploy Graxia OS - All Systems
# Run: .\DEPLOY_ALL_NOW.ps1

Write-Host "🚀 Deploying Graxia OS - All Systems" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

# Step 1: Deploy API
Write-Host "`n[1/4] Deploying API..." -ForegroundColor Yellow
cd backend
flyctl deploy --config fly.toml --remote-only

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ API Deploy Failed!" -ForegroundColor Red
    exit 1
}

# Step 2: Deploy Worker
Write-Host "`n[2/4] Deploying Worker..." -ForegroundColor Yellow
flyctl deploy --config fly.worker.toml --remote-only

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Worker Deploy Failed!" -ForegroundColor Red
    exit 1
}

# Step 3: Check Status
Write-Host "`n[3/4] Checking Status..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "`n--- API Status ---" -ForegroundColor Gray
flyctl status --app graxia-api

Write-Host "`n--- Worker Status ---" -ForegroundColor Gray
flyctl status --app graxia-worker

# Step 4: Quick Test
Write-Host "`n[4/4] Testing API..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host "Testing health endpoint..." -ForegroundColor Gray
try {
    $response = Invoke-RestMethod -Uri "https://graxia-api.fly.dev/health" -Method GET -TimeoutSec 10
    Write-Host "✅ API Health: $($response | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "⚠️  API test failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "`n=====================================" -ForegroundColor Cyan
Write-Host "🎉 Deploy Complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor White
Write-Host "1. Run full tests: .\scripts\quick-validation.ps1" -ForegroundColor Gray
Write-Host "2. Check logs: flyctl logs --app graxia-api --no-tail" -ForegroundColor Gray
Write-Host "3. Test in browser: https://graxia-api.fly.dev/health" -ForegroundColor Gray
