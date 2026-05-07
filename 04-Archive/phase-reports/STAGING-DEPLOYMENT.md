# Gracia OS Staging Deployment Guide

## 🎯 Overview

**Status**: ✅ All 77 tests passing (65 unit + 12 chaos tests)

Enterprise-grade resilience system deployed with:
- Circuit Breaker Pattern (Redis, OpenClaw)
- Weighted Failure Scoring for Scrapers
- Predictive Alerting with Trend Analysis
- Chaos Engineering Test Suite

---

## 🚀 Quick Start (Local Staging)

### Option 1: Quick Start Script (Recommended)
```powershell
# Start staging API on port 8001
.\scripts\quick-staging.ps1

# Or specify different port
.\scripts\quick-staging.ps1 -Port 8002
```

### Option 2: Manual Start
```powershell
cd backend
$env:ENVIRONMENT = "staging"
$env:DEBUG = "true"
$env:DATABASE_URL = "sqlite+aiosqlite:///./staging.db"
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## 📊 API Endpoints

Once running, test these endpoints:

### Basic Health
```bash
curl http://localhost:8001/health
```

### Detailed Health (with Circuit Breaker Status)
```bash
curl http://localhost:8001/api/v1/system/health/detailed
```

**Example Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-18T01:25:00",
  "circuit_breakers": {
    "redis": {
      "state": "CLOSED",
      "failure_count": 0,
      "success_count": 15
    },
    "openclaw": {
      "state": "CLOSED",
      "failure_count": 0,
      "success_count": 8
    }
  },
  "redis": {
    "healthy": true,
    "circuit_state": "CLOSED",
    "connection_pool_size": 10
  },
  "queues": {
    "critical": 0,
    "default": 2,
    "background": 0,
    "dlq": 0
  }
}
```

### Resilience Status Score
```bash
curl http://localhost:8001/api/v1/system/resilience/status
```

**Example Response:**
```json
{
  "timestamp": "2026-04-18T01:25:00",
  "circuit_breakers": {
    "redis": {
      "state": "CLOSED",
      "config": {
        "failure_threshold": 3,
        "recovery_timeout": 10,
        "half_open_max_calls": 2
      },
      "stats": {
        "failure_count": 0,
        "success_count": 15
      }
    }
  },
  "redis_pool": {
    "initialized": true,
    "health": {
      "healthy": true,
      "circuit_state": "CLOSED"
    }
  },
  "overall_resilience_score": 100
}
```

### Scraper Health
```bash
curl http://localhost:8001/api/v1/system/scraper-health
```

### Test Predictive Alerts
```bash
curl -X POST http://localhost:8001/api/v1/system/health/predictive-test \
  -H "Content-Type: application/json" \
  -d '{
    "service": "test-redis",
    "metrics": {
      "latency_ms": [10, 50, 120, 280, 500, 900]
    }
  }'
```

---

## 🧪 Run Tests

### Unit Tests
```powershell
cd backend
python -m pytest tests/test_redis_circuit_breaker.py tests/test_redis_pool.py tests/test_smart_scraper.py tests/test_advanced_health.py -v
```

### Chaos Tests
```powershell
cd backend
python -m pytest tests/chaos/test_resilience.py -v
```

### All Tests
```powershell
cd backend
python -m pytest tests/test_redis_circuit_breaker.py tests/test_redis_pool.py tests/test_smart_scraper.py tests/test_advanced_health.py tests/chaos/test_resilience.py
```

**Expected Result:** 77 passed, 3 skipped

---

## 🔧 Resilience System Architecture

### Circuit Breaker States
```
CLOSED (normal) → OPEN (after 3 failures) → HALF-OPEN (after 10s) → CLOSED (on success)
```

### Weighted Failure Scoring
| Error Type | Weight | Description |
|------------|--------|-------------|
| Timeout | 0.5 | Network timeout |
| Rate Limit | 0.3 | HTTP 429 |
| Parsing Error | 0.8 | Site structure changed |
| Site Changed | 1.0 | Blocking detected |

**Thresholds:**
- Early Warning: 2.0 points
- Auto-Mute: 3.0 points (6 hours)

### Predictive Alerting
- **Trend Analysis:** improving/stable/degrading/flapping
- **Prediction Window:** 10 minutes before failure
- **SLA Monitoring:** 99.9% uptime target
- **Alert Cooldown:** 5 minutes (prevents spam)

---

## 📈 Monitoring

### Resilience Score Calculation
```python
score = 100
if circuit OPEN:      score -= 30
if circuit HALF_OPEN: score -= 15
if Redis unhealthy:   score -= 25
# Range: 0-100
```

### Key Metrics to Monitor
1. `circuit_breaker.state` - Should be CLOSED
2. `redis_pool.healthy` - Should be true
3. `scraper_summary.healthy` - Number of active scrapers
4. `overall_resilience_score` - Should be 80+

---

## 🆘 Recovery Scripts

### List Scraper Status
```powershell
cd backend
.venv\Scripts\python.exe -m scripts.scraper_recovery list
```

### Unmute a Scraper
```powershell
cd backend
.venv\Scripts\python.exe -m scripts.scraper_recovery unmute upwork
```

### Emergency Recovery (Unmute All)
```powershell
cd backend
.venv\Scripts\python.exe -m scripts.scraper_recovery emergency
```

---

## 🐛 Troubleshooting

### API won't start
```powershell
# Check Python env
Test-Path backend\.venv\Scripts\python.exe

# Reinstall if needed
cd backend
python -m venv .venv
.venv\Scripts\pip install -e .
```

### Redis not available
- API will use in-memory fallback for circuit breaker state
- Queue functionality will be degraded
- Install Redis: `choco install redis-64` or use Docker

### Port already in use
```powershell
# Find process using port 8001
Get-NetTCPConnection -LocalPort 8001

# Kill it
Stop-Process -Id <PID> -Force
```

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `scripts/quick-staging.ps1` | Quick start staging API |
| `scripts/deploy-staging-local.ps1` | Full local deployment with chaos tests |
| `docker-compose.staging.yml` | Docker staging environment |
| `scripts/run-chaos-tests.ps1` | Chaos engineering test runner |
| `scripts/scraper_recovery.py` | Scraper management CLI |
| `deploy/monitoring/grafana/dashboards/resilience-dashboard.json` | Grafana dashboard |

---

## ✅ Deployment Checklist

- [ ] All 77 tests passing
- [ ] API starts successfully on port 8001
- [ ] `/health` endpoint returns 200
- [ ] `/api/v1/system/health/detailed` shows circuit breakers CLOSED
- [ ] `/api/v1/system/resilience/status` shows score 80+
- [ ] Predictive alert test triggers alert
- [ ] Scraper health endpoint returns data
- [ ] Chaos tests can be run successfully

---

## 🎓 Key Learnings

### Weighted vs Simple Failure Counting
**Old:** 3 failures → mute
**New:** Weighted score 3.0 → mute

Benefits:
- Timeout (0.5) is less severe than blocking (1.0)
- Early warning at 2.0 allows preventive action
- Site changes (1.0) trigger immediate mute

### Circuit Breaker Pattern
- Prevents cascade failures
- Auto-recovery through HALF-OPEN state
- Fail-fast when OPEN (no waiting)

### Predictive Alerting
- Detects trends, not just thresholds
- Warns 10 minutes before predicted failure
- Correlated failure detection for infrastructure issues

---

## 🔗 Next Steps

1. **Start API:** `.
