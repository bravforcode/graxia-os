# Grafana Dashboard Setup for Gracia OS

## 📊 Overview

Monitor your Gracia OS staging environment with real-time dashboards for:
- Circuit breaker state transitions
- Resilience score tracking
- Predictive alert visualization
- Service health metrics

## 🚀 Quick Start

### Option 1: Docker Grafana (Recommended)

```powershell
# Start Grafana container
docker run -d \
  --name=gracia-grafana \
  -p 3001:3000 \
  -e "GF_SECURITY_ADMIN_PASSWORD=admin" \
  -v ${PWD}/deploy/monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards \
  -v ${PWD}/deploy/monitoring/grafana/datasources:/etc/grafana/provisioning/datasources \
  grafana/grafana:latest
```

Then open http://localhost:3001 (admin/admin)

### Option 2: Local Grafana Install

1. Download from https://grafana.com/grafana/download
2. Install and start Grafana
3. Configure data source and dashboards

## 📁 Dashboard Files

| File | Description |
|------|-------------|
| `deploy/monitoring/grafana/dashboards/resilience-dashboard.json` | Main resilience monitoring |

## 🔌 Data Source Configuration

### Prometheus Data Source

1. Go to **Configuration** → **Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. URL: `http://localhost:9091` (or your Prometheus URL)
5. Click **Save & Test**

## 📈 Dashboard Panels

### 1. Circuit Breaker Status
- **Type:** Stat
- **Query:** `gracia_circuit_breaker_state`
- **Shows:** Current state (CLOSED/OPEN/HALF-OPEN)
- **Colors:** Green=Closed, Red=Open, Yellow=Half-Open

### 2. Resilience Score
- **Type:** Gauge
- **Query:** `gracia_resilience_score`
- **Range:** 0-100
- **Thresholds:** 
  - Red: 0-50 (Critical)
  - Yellow: 50-80 (Warning)
  - Green: 80-100 (Healthy)

### 3. Circuit Breaker Failures
- **Type:** Time series
- **Query:** `gracia_circuit_breaker_failures_total`
- **Shows:** Failure count over time per service

### 4. Predictive Alerts
- **Type:** Time series
- **Query:** `gracia_predictive_alerts_total`
- **Shows:** Alert frequency by severity

### 5. Redis Pool Health
- **Type:** Stat
- **Queries:** 
  - `gracia_redis_pool_healthy`
  - `gracia_redis_pool_connections_active`
- **Shows:** Pool health and connection count

### 6. Service Degradation Trends
- **Type:** Graph
- **Query:** `gracia_service_latency_ms`
- **Shows:** Latency trends for each service

### 7. Alert Cooldown Status
- **Type:** Table
- **Query:** `gracia_alert_cooldown_remaining`
- **Shows:** Which alerts are in cooldown

## 🔔 Annotations

Configure annotations to show:
- **Circuit breaker events:** State changes (CLOSED→OPEN→HALF-OPEN)
- **Predictive alerts:** Early warning triggers
- **Chaos test runs:** When chaos tests executed

## 🎯 Key Metrics to Monitor

| Metric | Target | Alert If |
|--------|--------|----------|
| Resilience Score | >80 | <50 |
| Circuit Breaker State | CLOSED | OPEN |
| Redis Pool Health | true | false |
| Queue Depth | <100 | >500 |
| Service Latency | <500ms | >2000ms |

## 📱 Accessing Dashboards

### With Auth Token
```bash
# Get token first
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@staging.local", "password": "any"}'

# Use token for API calls
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8001/api/v1/system/resilience/status
```

### Direct Metrics Endpoint
```bash
# Prometheus metrics (if enabled)
curl http://localhost:8001/metrics
```

## 🐛 Troubleshooting

### Grafana won't start
```powershell
# Check port conflict
Get-NetTCPConnection -LocalPort 3001

# Use different port
docker run -p 3002:3000 grafana/grafana
```

### No data in dashboards
1. Verify Prometheus is running
2. Check data source URL in Grafana
3. Ensure API is exposing metrics

### Dashboard import fails
1. Go to **Create** → **Import**
2. Upload `resilience-dashboard.json`
3. Select your Prometheus data source

## 🔗 Integration Commands

```powershell
# Start everything
.\scripts\start-staging-api.ps1
docker run -d -p 3001:3000 grafana/grafana

# Test chaos while monitoring
.\scripts\run-chaos-tests.ps1 -Continuous -Duration 300
```

## 📊 Example Dashboard View

```
┌─────────────────────────────────────────────────────────────────┐
│  CIRCUIT BREAKER STATUS          RESILIENCE SCORE              │
│  ✅ Redis: CLOSED                [████████░░] 85/100          │
│  ✅ OpenClaw: CLOSED              Healthy                      │
│                                                                │
├─────────────────────────────────────────────────────────────────┤
│  FAILURE COUNT (Last 1h)       PREDICTIVE ALERTS              │
│  Redis: 0                       Warning: 2                   │
│  OpenClaw: 1                    Critical: 0                   │
│                                                                │
├─────────────────────────────────────────────────────────────────┤
│  SERVICE LATENCY TRENDS                                       │
│  Redis: ████████░░░░ 120ms                                   │
│  Celery: ██████████░░ 80ms                                   │
│  OpenClaw: ███░░░░░░░ 45ms                                   │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
```

## 🎓 Next Steps

1. ✅ Start Grafana container
2. ✅ Import resilience dashboard
3. ✅ Configure Prometheus data source
4. ✅ Run chaos tests and watch real-time metrics
5. ✅ Set up alerts for resilience score drops

## 📚 Additional Resources

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Gracia OS Monitoring Guide](./STAGING-DEPLOYMENT.md)
