# PowerShell script to fix all Graxia OS issues
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "🔧 GRAXIA OS - FIX ALL ISSUES" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Step 1: Create vault
Write-Host "`n[Step 1/4] Creating Obsidian Vault..." -ForegroundColor Yellow
$vaultPath = "C:\Users\menum\OneDrive\Documents\Gracia"
$secondBrain = "$vaultPath\Second Brain"

if (!(Test-Path $vaultPath)) {
    New-Item -ItemType Directory -Force -Path $vaultPath | Out-Null
    Write-Host "   ✅ Created vault: $vaultPath" -ForegroundColor Green
} else {
    Write-Host "   ✅ Vault exists: $vaultPath" -ForegroundColor Green
}

# Create folder structure
$folders = @(
    "$secondBrain\00-Inbox",
    "$secondBrain\01-Projects",
    "$secondBrain\02-Areas",
    "$secondBrain\03-Resources",
    "$secondBrain\04-Archive",
    "$secondBrain\90-System"
)

foreach ($folder in $folders) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
}
Write-Host "   ✅ Created Second Brain structure" -ForegroundColor Green

# Create README
$readmeContent = @"
# Graxia OS Second Brain

Connected to Graxia OS Agent System.

## Folders
- 00-Inbox: Quick capture
- 01-Projects: Active projects
- 02-Areas: Responsibility areas
- 03-Resources: Reference material
- 04-Archive: Completed/Inactive
- 90-System: System files
"@
$readmeContent | Out-File -FilePath "$secondBrain\README.md" -Encoding UTF8
Write-Host "   ✅ Created README.md" -ForegroundColor Green

# Step 2: Verify env file
Write-Host "`n[Step 2/4] Verifying .env configuration..." -ForegroundColor Yellow
$envFile = "backend\.env"
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    
    # Check OBSIDIAN_VAULT_PATH
    if ($content -match "OBSIDIAN_VAULT_PATH=C:/Users/menum/OneDrive/Documents/Gracia") {
        Write-Host "   ✅ OBSIDIAN_VAULT_PATH is correct" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  OBSIDIAN_VAULT_PATH may be incorrect" -ForegroundColor Yellow
    }
    
    # Check Redis
    if ($content -match "redis-18128.c295.ap-southeast-1-1.ec2.cloud.redislabs.com") {
        Write-Host "   ✅ Redis Labs configured" -ForegroundColor Green
    }
} else {
    Write-Host "   ❌ .env file not found!" -ForegroundColor Red
}

# Step 3: Clear Python cache
Write-Host "`n[Step 3/4] Clearing Python cache..." -ForegroundColor Yellow
$cacheDirs = @(
    "backend\app\__pycache__",
    "backend\app\core\__pycache__",
    "backend\app\integrations\__pycache__"
)

foreach ($dir in $cacheDirs) {
    if (Test-Path $dir) {
        Remove-Item -Path $dir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ Cleared: $dir" -ForegroundColor Gray
    }
}
Write-Host "   ✅ Python cache cleared" -ForegroundColor Green

# Step 4: Run test
Write-Host "`n[Step 4/4] Running final test..." -ForegroundColor Yellow
python scripts\test_agent_system.py 2>&1 | ForEach-Object {
    $line = $_
    if ($line -match "✅|PASS") {
        Write-Host $line -ForegroundColor Green
    } elseif ($line -match "❌|FAIL") {
        Write-Host $line -ForegroundColor Red
    } else {
        Write-Host $line
    }
}

Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "✅ FIX COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. Open Obsidian and select 'Gracia' vault" -ForegroundColor White
Write-Host "  2. Run backend: cd backend && python -m uvicorn app.main:app --reload" -ForegroundColor White
Write-Host "  3. Run frontend: cd frontend && bun run dev" -ForegroundColor White
Write-Host "=" * 70 -ForegroundColor Cyan
