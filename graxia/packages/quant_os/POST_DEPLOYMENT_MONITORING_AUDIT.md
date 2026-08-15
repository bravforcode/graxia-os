# POST-DEPLOYMENT MONITORING AUDIT — Phase 22

## Executive Summary

Monitoring infrastructure is **architecturally comprehensive** (heartbeat, dead man's switch, Prometheus, Grafana) but has **critical inconsistencies** between components and incomplete alert routing.

## Component Inventory

| Component | File | Timeout | Status |
|-----------|------|---------|--------|
| HeartbeatMonitor | `monitoring/heartbeat_monitor.py` | 1h warn, 4h kill | ✅ Functional |
| DeadMansSwitch | `monitoring/dead_mans_switch.py` | 5min | ✅ Functional |
| AlertManager | `monitoring/alerts.py` | N/A | ❌ Stubbed |
| Prometheus | `docker-compose.yml` | 30d retention | ✅ Configured |
| Grafana | `docker-compose.yml` | Provisioned | ✅ Configured |
| Alertmanager | `docker-compose.yml` | Telegram routing | ✅ Configured |

## Critical Findings

### CRIT-22-01: Timeout Inconsistency Between Monitors
**Severity**: HIGH
**Files**: `monitoring/heartbeat_monitor.py:34-35`, `monitoring/dead_mans_switch.py:12`
```python
# HeartbeatMonitor
STALE_THRESHOLD_S = 3600      # 1 hour
CRITICAL_THRESHOLD_S = 14400   # 4 hours

# DeadMansSwitch
DEFAULT_TIMEOUT = 300.0        # 5 minutes
```
**Impact**: Two different watchdog mechanisms with different timeouts could create race conditions. DeadMansSwitch fires at 5 minutes, while HeartbeatMonitor warns at 1 hour. If both are active, the system may halt before the operator is notified.

### CRIT-22-02: AlertManager Does Not Send Alerts
**Severity**: CRITICAL
**File**: `monitoring/alerts.py:38-45`
**Impact**: All alerts are silently dropped. The `send_alert()` method returns `True` without actually routing notifications to Telegram or any other channel.

### CRIT-22-03: HeartbeatMonitor and DeadMansSwitch Are Separate
**Severity**: MEDIUM
**Files**: `monitoring/heartbeat_monitor.py`, `monitoring/dead_mans_switch.py`
**Impact**: Two independent heartbeat monitors with different implementations. The DeadMansSwitch watches a state dict, while HeartbeatMonitor reads a file. These should be unified or clearly documented as complementary.

## Positive Findings

1. **DeadMansSwitch**: Proper emergency sequence (halt → close positions → alert)
2. **HeartbeatMonitor**: Clear thresholds with escalating severity
3. **Docker monitoring stack**: Prometheus + Alertmanager + Grafana is production-grade
4. **MT5 close-all callback**: `create_mt5_close_all_callback()` provides real broker integration

## Alert Routing Status

| Channel | Configuration | Implementation |
|---------|---------------|----------------|
 | Telegram | docker-compose env vars | ⚠️ AlertManager stubbed |
| Prometheus | prometheus.yml | ✅ Metrics collection |
| Grafana | Provisioned dashboards | ✅ Visualization |
| Alertmanager | alertmanager.yml | ✅ Routing configured |

## Recommendations

1. **P0**: Unify heartbeat monitoring (single source of truth)
2. **P0**: Implement AlertManager actual routing to Telegram
3. **P1**: Align timeout thresholds across all watchdog components
4. **P2**: Add Prometheus metrics for heartbeat freshness
5. **P3**: Create runbook for monitoring alert response procedures
