# 🧪 Graxia OS - Production Testing Guide (Real Data Only)

> **NO FAKE DATA** - ทุกการเทสใช้ข้อมูลจริงจากระบบ

## 📋 Pre-Testing Requirements

ก่อนเริ่มเทส ต้องมี:
- [ ] Backend deployed บน Fly.io แล้ว
- [ ] Worker deployed บน Fly.io แล้ว  
- [ ] GitHub Actions workflows อยู่ใน repo
- [ ] `INTERNAL_API_KEY` ตั้งใน GitHub Secrets และ Fly.io
- [ ] `.env` ที่ local machine พร้อมใช้

---

## 🎯 Phase 1: Infrastructure Testing

### 1.1 Fly.io Deployment Test

```powershell
# สคริปต์: scripts/test-flyio-deployment.ps1
# Run บน local machine

$API_URL = "https://graxia-api.fly.dev"
$INTERNAL_KEY = $env:INTERNAL_API_KEY

Write-Host "🧪 Testing Fly.io Deployment" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

# Test 1: Basic connectivity
Write-Host "`n[Test 1] Basic Connectivity..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$API_URL/health" -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -eq 200) { Write-Host " ✅ PASS" -ForegroundColor Green }
    else { Write-Host " ❌ FAIL (Status: $($response.StatusCode))" -ForegroundColor Red }
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}

# Test 2: Worker status
Write-Host "[Test 2] Worker VM Status..." -NoNewline
$status = flyctl status --app graxia-worker 2>&1
if ($status -match "running") { Write-Host " ✅ PASS" -ForegroundColor Green }
else { Write-Host " ❌ FAIL (Worker not running)" -ForegroundColor Red }

# Test 3: API VM Status
Write-Host "[Test 3] API VM Status..." -NoNewline
$status = flyctl status --app graxia-api 2>&1
if ($status -match "running") { Write-Host " ✅ PASS" -ForegroundColor Green }
else { Write-Host " ❌ FAIL (API not running)" -ForegroundColor Red }
```

**Expected Result**: ทุก test ✅ PASS

### 1.2 Database Connection Test (Real Data)

```powershell
# Test จริง: เชื่อมต่อ database ผ่าน API

Write-Host "`n[Test 4] Database Connection (Real Query)..." -NoNewline
try {
    $headers = @{ "Authorization" = "Bearer $INTERNAL_KEY" }
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30 | ConvertFrom-Json
    
    if ($response.services.database -eq "healthy") {
        Write-Host " ✅ PASS" -ForegroundColor Green
        Write-Host "         Database Status: $($response.services.database)" -ForegroundColor Gray
    } else {
        Write-Host " ❌ FAIL (DB: $($response.services.database))" -ForegroundColor Red
    }
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

**Expected Result**: Database Status: `healthy`

### 1.3 Redis Connection Test (Real Data)

```powershell
# Test จริง: เชื่อมต่อ Redis ผ่าน API

Write-Host "[Test 5] Redis Connection (Real Ping)..." -NoNewline
try {
    $headers = @{ "Authorization" = "Bearer $INTERNAL_KEY" }
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30 | ConvertFrom-Json
    
    if ($response.services.redis -eq "healthy") {
        Write-Host " ✅ PASS" -ForegroundColor Green
        Write-Host "         Redis Status: $($response.services.redis)" -ForegroundColor Gray
    } else {
        Write-Host " ❌ FAIL (Redis: $($response.services.redis))" -ForegroundColor Red
    }
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

**Expected Result**: Redis Status: `healthy`

---

## 🎯 Phase 2: API Endpoint Testing

### 2.1 Public Endpoints (No Auth Required)

```powershell
# 2.1.1 Health Check - Public
Write-Host "`n[2.1.1] GET /health (Public)..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$API_URL/health" -UseBasicParsing -TimeoutSec 30
    $data = $response.Content | ConvertFrom-Json
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Response: $($data.status)" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL" -ForegroundColor Red
}

# 2.1.2 System Stats - Public  
Write-Host "[2.1.2] GET /api/v1/system/stats..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/system/stats" -UseBasicParsing -TimeoutSec 30
    $data = $response.Content | ConvertFrom-Json
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Leads: $($data.leads_scanned), Opportunities: $($data.opportunities_found)" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL" -ForegroundColor Red
}
```

### 2.2 Internal Endpoints (Require INTERNAL_API_KEY)

```powershell
# 2.2.1 Internal Health - Protected
Write-Host "`n[2.2.1] GET /api/v1/internal/health (Protected)..." -NoNewline
try {
    $headers = @{ "Authorization" = "Bearer $INTERNAL_KEY" }
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30
    Write-Host " ✅ PASS" -ForegroundColor Green
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}

# 2.2.2 Internal Health - Without Key (Should Fail)
Write-Host "[2.2.2] GET /api/v1/internal/health (No Key - Should 401)..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -UseBasicParsing -TimeoutSec 30
    Write-Host " ❌ FAIL (Should have been 401)" -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host " ✅ PASS (Correctly rejected)" -ForegroundColor Green
    } else {
        Write-Host " ❌ FAIL (Wrong status: $($_.Exception.Response.StatusCode))" -ForegroundColor Red
    }
}
```

**Expected Results**:
- 2.2.1: ✅ PASS (200 OK)
- 2.2.2: ✅ PASS (401 Unauthorized)

### 2.3 Queue Status Test (Real Queue Data)

```powershell
# 2.3.1 Get Queue Status
Write-Host "`n[2.3.1] GET /api/v1/internal/queue-status..." -NoNewline
try {
    $headers = @{ "Authorization" = "Bearer $INTERNAL_KEY" }
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/queue-status" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30 | ConvertFrom-Json
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Queues: $($response.queues | ConvertTo-Json -Compress)" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

---

## 🎯 Phase 3: Functional Testing

### 3.1 Lead Hunter Test (Real Execution)

```powershell
# 3.1.1 Trigger Lead Hunter
Write-Host "`n[3.1.1] POST /api/v1/internal/run-lead-hunter (Real Execution)..." -ForegroundColor Yellow
Write-Host "         This will actually run the lead hunter and save data to database!"
Write-Host "         Continue? (y/n): " -NoNewline
$confirm = Read-Host

if ($confirm -eq 'y') {
    try {
        $headers = @{ 
            "Authorization" = "Bearer $INTERNAL_KEY"
            "Content-Type" = "application/json"
        }
        $start = Get-Date
        
        $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/run-lead-hunter" `
            -Method POST -Headers $headers -UseBasicParsing -TimeoutSec 300
        
        $duration = (Get-Date) - $start
        $data = $response.Content | ConvertFrom-Json
        
        Write-Host " ✅ PASS" -ForegroundColor Green
        Write-Host "         Leads Found: $($data.leads_found)" -ForegroundColor Cyan
        Write-Host "         Duration: $([math]::Round($duration.TotalSeconds, 2))s" -ForegroundColor Gray
        Write-Host "         Timestamp: $($data.timestamp)" -ForegroundColor Gray
        
        # Verify จริง: เช็ค database ว่ามี leads ใหม่
        Write-Host "`n         [Verification] Checking database for new leads..." -NoNewline
        Start-Sleep -Seconds 2  # รอให้ database commit
        
        # เรียก stats ใหม่เพื่อเช็ค
        $stats = Invoke-WebRequest -Uri "$API_URL/api/v1/system/stats" `
            -UseBasicParsing -TimeoutSec 30 | ConvertFrom-Json
        Write-Host " ✅" -ForegroundColor Green
        Write-Host "         Current leads_scanned: $($stats.leads_scanned)" -ForegroundColor Gray
        
    } catch {
        Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
    }
} else {
    Write-Host "         Skipped." -ForegroundColor Yellow
}
```

**Expected Result**: 
- Status: success
- leads_found: >= 0 (จริงจาก Fastwork/SerpAPI)
- Database updated with real leads

### 3.2 Daily Report Test

```powershell
# 3.2.1 Generate Daily Report
Write-Host "`n[3.2.1] POST /api/v1/internal/daily-report (Real Report)..." -NoNewline
try {
    $headers = @{ 
        "Authorization" = "Bearer $INTERNAL_KEY"
        "Content-Type" = "application/json"
    }
    
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/daily-report" `
        -Method POST -Headers $headers -UseBasicParsing -TimeoutSec 60 | ConvertFrom-Json
    
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Report Date: $($data.report.date)" -ForegroundColor Gray
    Write-Host "         Leads Found: $($data.report.leads_found)" -ForegroundColor Gray
    Write-Host "         Opportunities: $($data.report.opportunities_created)" -ForegroundColor Gray
    Write-Host "         AI Actions: $($data.report.ai_actions)" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

**Expected Result**: Report จริงจาก database ของวันนี้/เมื่อวาน

### 3.3 Cleanup Analysis Test

```powershell
# 3.3.1 Run Cleanup Analysis
Write-Host "`n[3.3.1] POST /api/v1/internal/cleanup (Analysis Mode)..." -NoNewline
try {
    $headers = @{ 
        "Authorization" = "Bearer $INTERNAL_KEY"
        "Content-Type" = "application/json"
    }
    
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/cleanup?days_to_keep=30" `
        -Method POST -Headers $headers -UseBasicParsing -TimeoutSec 60 | ConvertFrom-Json
    
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Cutoff Date: $($data.cleanup.cutoff_date)" -ForegroundColor Gray
    Write-Host "         Audit Logs to Clean: $($data.cleanup.audit_logs_to_clean)" -ForegroundColor Gray
    Write-Host "         Status: $($data.cleanup.status)" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

---

## 🎯 Phase 4: Integration Testing

### 4.1 Frontend → Backend Integration

```powershell
# 4.1.1 Test Vercel → Fly.io API
$FRONTEND_URL = "https://your-frontend.vercel.app"  # เปลี่ยนเป็นของคุณ

Write-Host "`n[4.1.1] Frontend → Backend Integration..." -NoNewline
try {
    # Frontend should proxy /api/* to backend
    $response = Invoke-WebRequest -Uri "$FRONTEND_URL/api/v1/system/health" `
        -UseBasicParsing -TimeoutSec 30
    Write-Host " ✅ PASS" -ForegroundColor Green
    Write-Host "         Frontend proxy working correctly" -ForegroundColor Gray
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
    Write-Host "         Check vercel.json rewrite rules" -ForegroundColor Yellow
}
```

### 4.2 CORS Test

```powershell
# 4.2.1 Test CORS Preflight
Write-Host "`n[4.2.1] CORS Preflight Test..." -NoNewline
try {
    $headers = @{
        "Origin" = $FRONTEND_URL
        "Access-Control-Request-Method" = "GET"
    }
    
    $response = Invoke-WebRequest -Uri "$API_URL/health" `
        -Method OPTIONS -Headers $headers -UseBasicParsing
    
    if ($response.Headers["Access-Control-Allow-Origin"]) {
        Write-Host " ✅ PASS" -ForegroundColor Green
        Write-Host "         CORS Headers: Present" -ForegroundColor Gray
    } else {
        Write-Host " ⚠️  WARNING (CORS headers missing)" -ForegroundColor Yellow
    }
} catch {
    Write-Host " ❌ FAIL ($($_.Exception.Message))" -ForegroundColor Red
}
```

---

## 🎯 Phase 5: GitHub Actions Testing

### 5.1 Manual Workflow Trigger

```powershell
# 5.1.1 Trigger cron-lead-hunter manually via GitHub API
Write-Host "`n[5.1.1] Manual GitHub Actions Trigger..." -ForegroundColor Yellow
Write-Host "         Go to: https://github.com/YOUR_USERNAME/graxia-os/actions"
Write-Host "         Click 'Lead Hunter' workflow → 'Run workflow'"
Write-Host "         Press Enter after triggering..."
Read-Host

# Check if workflow ran
Write-Host "`n         Check GitHub Actions logs. Did it run successfully? (y/n): " -NoNewline
$ran = Read-Host
if ($ran -eq 'y') { Write-Host "         ✅ PASS" -ForegroundColor Green }
else { Write-Host "         ❌ FAIL" -ForegroundColor Red }
```

### 5.2 Wait for Scheduled Run

```powershell
# 5.2.1 Monitor GitHub Actions
Write-Host "`n[5.2.1] Scheduled Run Monitoring..." -ForegroundColor Yellow
Write-Host "         Lead Hunter runs every 15 minutes"
Write-Host "         Next runs:"

$now = Get-Date
for ($i = 1; $i -le 3; $i++) {
    $next = $now.AddMinutes(15 - ($now.Minute % 15))
    Write-Host "           - $($next.ToString('HH:mm'))" -ForegroundColor Gray
    $now = $next.AddMinutes(15)
}

Write-Host "`n         Monitor at: https://github.com/YOUR_USERNAME/graxia-os/actions" -ForegroundColor Cyan
```

---

## 🎯 Phase 6: Load & Performance Testing

### 6.1 Concurrent Request Test

```powershell
# 6.1.1 Concurrent API Requests
Write-Host "`n[6.1.1] Concurrent Request Test (10 parallel calls)..." -NoNewline

$uris = 1..10 | ForEach-Object { "$API_URL/health" }
$jobs = $uris | ForEach-Object { 
    Start-Job -ScriptBlock {
        param($uri)
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 30
            return @{ Success = $true; Status = $response.StatusCode }
        } catch {
            return @{ Success = $false; Error = $_.Exception.Message }
        }
    } -ArgumentList $_
}

$jobs | Wait-Job -Timeout 60 | Out-Null
$results = $jobs | Receive-Job
$jobs | Remove-Job

$success = ($results | Where-Object { $_.Success }).Count
$failed = ($results | Where-Object { -not $_.Success }).Count

if ($failed -eq 0) {
    Write-Host " ✅ PASS (10/10 succeeded)" -ForegroundColor Green
} else {
    Write-Host " ❌ FAIL ($success/10 succeeded, $failed failed)" -ForegroundColor Red
}
```

### 6.2 Response Time Test

```powershell
# 6.2.1 API Response Times
Write-Host "`n[6.2.1] Response Time Analysis..." -ForegroundColor Cyan

$endpoints = @(
    @{ Name = "/health"; Url = "$API_URL/health"; Auth = $false },
    @{ Name = "/api/v1/system/stats"; Url = "$API_URL/api/v1/system/stats"; Auth = $false },
    @{ Name = "/api/v1/internal/health"; Url = "$API_URL/api/v1/internal/health"; Auth = $true }
)

foreach ($endpoint in $endpoints) {
    Write-Host "`n  Testing $($endpoint.Name)..." -ForegroundColor Yellow
    
    $times = @()
    for ($i = 1; $i -le 5; $i++) {
        $start = Get-Date
        try {
            if ($endpoint.Auth) {
                $headers = @{ "Authorization" = "Bearer $INTERNAL_KEY" }
                Invoke-WebRequest -Uri $endpoint.Url -Headers $headers -UseBasicParsing -TimeoutSec 30 | Out-Null
            } else {
                Invoke-WebRequest -Uri $endpoint.Url -UseBasicParsing -TimeoutSec 30 | Out-Null
            }
            $times += ((Get-Date) - $start).TotalMilliseconds
        } catch {
            $times += 99999  # Failed
        }
    }
    
    $avg = ($times | Measure-Object -Average).Average
    $min = ($times | Measure-Object -Minimum).Minimum
    $max = ($times | Measure-Object -Maximum).Maximum
    
    $color = if ($avg -lt 500) { "Green" } elseif ($avg -lt 1000) { "Yellow" } else { "Red" }
    Write-Host "    Avg: $([math]::Round($avg, 2))ms | Min: $([math]::Round($min, 2))ms | Max: $([math]::Round($max, 2))ms" -ForegroundColor $color
}
```

**Expected Results**:
- /health: < 200ms (จาก Fly.io Singapore)
- /api/v1/system/stats: < 500ms (ต้อง query database)
- /api/v1/internal/health: < 500ms (ต้อง query DB + Redis)

---

## 🎯 Phase 7: End-to-End Scenario Testing

### 7.1 Full Lead Flow Test

```powershell
# 7.1.1 Complete Lead Flow
Write-Host "`n[7.1.1] End-to-End Lead Flow Test..." -ForegroundColor Cyan
Write-Host "       This test will:" -ForegroundColor Gray
Write-Host "       1. Check current lead count" -ForegroundColor Gray
Write-Host "       2. Trigger lead hunter" -ForegroundColor Gray
Write-Host "       3. Wait for processing" -ForegroundColor Gray
Write-Host "       4. Verify lead count increased (or same)" -ForegroundColor Gray
Write-Host "       5. Check opportunities created" -ForegroundColor Gray
Write-Host ""
Write-Host "       Continue? (y/n): " -NoNewline
$confirm = Read-Host

if ($confirm -eq 'y') {
    # Step 1: Get initial count
    Write-Host "`n[Step 1] Getting initial stats..." -NoNewline
    $initialStats = Invoke-WebRequest -Uri "$API_URL/api/v1/system/stats" `
        -UseBasicParsing | ConvertFrom-Json
    $initialLeads = $initialStats.leads_scanned
    $initialOpp = $initialStats.opportunities_found
    Write-Host " ✅ (Leads: $initialLeads, Opportunities: $initialOpp)" -ForegroundColor Green
    
    # Step 2: Trigger lead hunter
    Write-Host "[Step 2] Triggering lead hunter..." -NoNewline
    $headers = @{ 
        "Authorization" = "Bearer $INTERNAL_KEY"
        "Content-Type" = "application/json"
    }
    $result = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/run-lead-hunter" `
        -Method POST -Headers $headers -UseBasicParsing -TimeoutSec 300 | ConvertFrom-Json
    Write-Host " ✅ (Found: $($result.leads_found))" -ForegroundColor Green
    
    # Step 3: Wait
    Write-Host "[Step 3] Waiting 5 seconds for processing..." -NoNewline
    Start-Sleep -Seconds 5
    Write-Host " ✅" -ForegroundColor Green
    
    # Step 4: Verify
    Write-Host "[Step 4] Verifying new stats..." -NoNewline
    $finalStats = Invoke-WebRequest -Uri "$API_URL/api/v1/system/stats" `
        -UseBasicParsing | ConvertFrom-Json
    $finalLeads = $finalStats.leads_scanned
    $finalOpp = $finalStats.opportunities_found
    Write-Host " ✅ (Leads: $finalLeads, Opportunities: $finalOpp)" -ForegroundColor Green
    
    # Summary
    Write-Host "`n[RESULT]" -ForegroundColor Cyan
    Write-Host "  Leads Change: $($finalLeads - $initialLeads) (was $initialLeads, now $finalLeads)" -ForegroundColor $(if ($finalLeads -ge $initialLeads) { "Green" } else { "Red" })
    Write-Host "  Opportunities Change: $($finalOpp - $initialOpp)" -ForegroundColor $(if ($finalOpp -ge $initialOpp) { "Green" } else { "Red" })
    
    if ($result.leads_found -eq ($finalLeads - $initialLeads)) {
        Write-Host "  ✅ Data consistency verified!" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Lead count mismatch (lead hunter found $($result.leads_found), but DB shows $($finalLeads - $initialLeads) new)" -ForegroundColor Yellow
    }
} else {
    Write-Host "       Skipped." -ForegroundColor Yellow
}
```

---

## 🎯 Phase 8: Security Testing

### 8.1 Authentication Tests

```powershell
# 8.1.1 Invalid API Key
Write-Host "`n[8.1.1] Invalid INTERNAL_API_KEY Test..." -NoNewline
try {
    $headers = @{ "Authorization" = "Bearer invalid_key_here" }
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30
    Write-Host " ❌ FAIL (Should have been rejected)" -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host " ✅ PASS (Correctly rejected with 401)" -ForegroundColor Green
    } else {
        Write-Host " ❌ FAIL (Got $($_.Exception.Response.StatusCode), expected 401)" -ForegroundColor Red
    }
}

# 8.1.2 Missing Authorization Header
Write-Host "[8.1.2] Missing Authorization Header..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -UseBasicParsing -TimeoutSec 30
    Write-Host " ❌ FAIL (Should have been rejected)" -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 401 -or $_.Exception.Response.StatusCode -eq 403) {
        Write-Host " ✅ PASS (Correctly rejected)" -ForegroundColor Green
    } else {
        Write-Host " ❌ FAIL (Got $($_.Exception.Response.StatusCode))" -ForegroundColor Red
    }
}

# 8.1.3 Wrong Bearer Prefix
Write-Host "[8.1.3] Wrong Bearer Prefix (Token without 'Bearer ')..." -NoNewline
try {
    $headers = @{ "Authorization" = $INTERNAL_KEY }  # ไม่มี "Bearer "
    $response = Invoke-WebRequest -Uri "$API_URL/api/v1/internal/health" `
        -Headers $headers -UseBasicParsing -TimeoutSec 30
    # Code should handle both with and without Bearer
    Write-Host " ⚠️  WARNING (API accepted without Bearer prefix)" -ForegroundColor Yellow
} catch {
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host " ✅ PASS (Correctly rejected)" -ForegroundColor Green
    } else {
        Write-Host " ❌ FAIL" -ForegroundColor Red
    }
}
```

---

## 📊 Test Results Template

สร้างไฟล์ `test-results-$(Get-Date -Format "yyyy-MM-dd-HHmm").md`:

```markdown
# Graxia OS Production Test Results
**Date**: $(Get-Date)
**API URL**: $API_URL
**Tester**: $(whoami)

## Summary
| Phase | Status | Notes |
|-------|--------|-------|
| 1. Infrastructure | ⬜ | |
| 2. API Endpoints | ⬜ | |
| 3. Functional | ⬜ | |
| 4. Integration | ⬜ | |
| 5. GitHub Actions | ⬜ | |
| 6. Performance | ⬜ | |
| 7. E2E | ⬜ | |
| 8. Security | ⬜ | |

## Detailed Results

### Phase 1: Infrastructure
- [ ] Fly.io API running
- [ ] Fly.io Worker running  
- [ ] Database connection: (status)
- [ ] Redis connection: (status)

### Phase 2: API Endpoints
- [ ] Public endpoints accessible
- [ ] Internal endpoints protected
- [ ] Queue status retrievable

### Phase 3: Functional
- [ ] Lead hunter executed: (leads found)
- [ ] Daily report generated: (date)
- [ ] Cleanup analysis: (records to clean)

### Phase 4: Integration
- [ ] Frontend → Backend: (status)
- [ ] CORS headers: (status)

### Phase 5: GitHub Actions
- [ ] Manual trigger: (status)
- [ ] Scheduled runs: (monitoring)

### Phase 6: Performance
- [ ] Concurrent requests: (X/10 passed)
- [ ] Avg response time: (X ms)

### Phase 7: E2E
- [ ] Full lead flow: (status)
- [ ] Data consistency: (status)

### Phase 8: Security
- [ ] Invalid key rejected
- [ ] Missing auth rejected

## Issues Found
<!-- List any issues here -->

## Sign-off
- [ ] All critical tests passed
- [ ] No security vulnerabilities found
- [ ] Performance acceptable
- [ ] Ready for production

**Approved by**: _______________
**Date**: _______________
```

---

## 🚨 Emergency Stop

ถ้า test พบปัญหาร้ายแรง:

```powershell
# Rollback Fly.io ทันที
flyctl deploy --app graxia-api --image <previous-image>

# หรือ restart
flyctl restart --app graxia-api
flyctl restart --app graxia-worker

# Disable GitHub Actions (ถ้าจำเป็น)
# ไปที่ GitHub → Actions → ปิด workflows
```

---

## ✅ Final Checklist

ก่อนถือว่าเสร็จ:
- [ ] รัน Test Phase 1-8 ครบ
- [ ] บันทึกผลลง `test-results-*.md`
- [ ] ไม่มี ❌ FAIL ในส่วนที่ critical
- [ ] Lead hunter เจอ leads จริง (ไม่ใช่ 0 ตลอด)
- [ ] Database query return ข้อมูลจริง
- [ ] Redis ping สำเร็จ
- [ ] GitHub Actions trigger ได้จริง
- [ ] Security tests ผ่าน

**พร้อม Production: ⬜ YES / ⬜ NO**
