#Requires -Version 7.0
<#
.SYNOPSIS
    Graxia OS - Quick Validation Script
    
.DESCRIPTION
    รัน tests สำคัญที่สุด 5 อย่าง ภายใน 2 นาที
    ใช้ตรวจสอบว่าระบบพร้อมใช้งานหรือไม่
    
.PARAMETER ApiUrl
    URL ของ API
    
.PARAMETER InternalApiKey
    INTERNAL_API_KEY
#>

param(
    [string]$ApiUrl = "https://graxia-api.fly.dev",
    [string]$InternalApiKey = $env:INTERNAL_API_KEY
)

Write-Host "🚀 Graxia OS - Quick Validation (2 minutes)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$tests = @()
$start = Get-Date

function Test-Quick {
    param([string]$Name, [scriptblock]$Test)
    Write-Host "`n[Test] $Name..." -NoNewline
    try {
        $result = & $Test
        if ($result) {
            Write-Host " ✅" -ForegroundColor Green
            return @{ Name = $Name; Passed = $true }
        } else {
            Write-Host " ❌" -ForegroundColor Red
            return @{ Name = $Name; Passed = $false }
        }
    } catch {
        Write-Host " ❌ ($($_.Exception.Message))" -ForegroundColor Red
        return @{ Name = $Name; Passed = $false; Error = $_.Exception.Message }
    }
}

# Test 1: Basic connectivity
$tests += Test-Quick "API Health Endpoint" {
    $r = Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 10
    $r.StatusCode -eq 200
}

# Test 2: Database connection (ถ้ามี key)
if ($InternalApiKey) {
    $tests += Test-Quick "Database Connection" {
        $h = @{ "Authorization" = "Bearer $InternalApiKey" }
        $r = Invoke-WebRequest -Uri "$ApiUrl/api/v1/internal/health" -Headers $h -UseBasicParsing -TimeoutSec 10
        $d = $r.Content | ConvertFrom-Json
        $d.services.database -eq "healthy"
    }
    
    # Test 3: Redis connection
    $tests += Test-Quick "Redis Connection" {
        $h = @{ "Authorization" = "Bearer $InternalApiKey" }
        $r = Invoke-WebRequest -Uri "$ApiUrl/api/v1/internal/health" -Headers $h -UseBasicParsing -TimeoutSec 10
        $d = $r.Content | ConvertFrom-Json
        $d.services.redis -eq "healthy"
    }
    
    # Test 4: Authentication working (should reject invalid key)
    $tests += Test-Quick "Auth Rejection (Security)" {
        try {
            $h = @{ "Authorization" = "Bearer invalid_key" }
            Invoke-WebRequest -Uri "$ApiUrl/api/v1/internal/health" -Headers $h -UseBasicParsing -TimeoutSec 10 | Out-Null
            $false  # Should have failed
        } catch {
            $_.Exception.Response.StatusCode -eq 401
        }
    }
    
    # Test 5: Queue status accessible
    $tests += Test-Quick "Queue Status" {
        $h = @{ "Authorization" = "Bearer $InternalApiKey" }
        $r = Invoke-WebRequest -Uri "$ApiUrl/api/v1/internal/queue-status" -Headers $h -UseBasicParsing -TimeoutSec 10
        $r.StatusCode -eq 200
    }
} else {
    Write-Host "`n⚠️  INTERNAL_API_KEY not set. Skipping DB/Redis/Auth tests." -ForegroundColor Yellow
}

# Summary
$duration = (Get-Date) - $start
$passed = ($tests | Where-Object { $_.Passed }).Count
$total = $tests.Count

Write-Host "`n╔═══════════════════════════════════════════════════╗" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })
Write-Host "║  Result: $passed/$total passed in $([math]::Round($duration.TotalSeconds, 1))s                ║" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })
Write-Host "╚═══════════════════════════════════════════════════╝" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })

if ($passed -eq $total) {
    Write-Host "`n✅ System is operational!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n⚠️  Some checks failed. Review issues above." -ForegroundColor Yellow
    $failed = $tests | Where-Object { -not $_.Passed }
    foreach ($f in $failed) {
        Write-Host "   ❌ $($f.Name)" -ForegroundColor Red
    }
    exit 1
}
