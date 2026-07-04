# Production Readiness & Deployment Gaps — Deep Dive Research

> **Date:** 2026-07-04
> **Status:** Research Complete
> **Sources:** IB TWS API docs, QuantConnect LEAN docs, industry best practices, quant_os codebase audit

---

## 1. BACKTEST → LIVE TRADING TRANSITION

### Industry Best Practices (IB / QuantConnect)

**IB TWS API Requirements:**
- Funded IBKR Pro account required (IBKR Lite does NOT support API trading)
- TWS or IB Gateway v1045+ required for comprehensive feature support
- TCP Socket Protocol — all libraries must implement the same message format
- 2FA required: IB Key, Handy Key, SMS, or DSC+ (Security Code Card NOT supported via API)
- Weekly re-authentication mandatory for automated systems (IB Key notification every Sunday)
- Pacing limitations: strict rate limits on market data requests (especially historical bars < 30s)

**QuantConnect LEAN Transition Pattern:**
- Seamless backtest→live via same codebase; LEAN handles brokerage abstraction
- Automatic algorithm restarting on runtime errors (e.g., brokerage disconnection)
- Weekly restart scheduling with IB Key re-auth notification
- Hybrid data provider mode: QuantConnect data + IB execution
- Delayed market data fallback when subscriptions are missing

### quant_os Current State vs. Gap Analysis

| Component | Status | Gap |
|-----------|--------|-----|
| Backtest engine | ✅ Complete | None |
| Paper trading | ✅ Complete (demo_canary) | None |
| Shadow trading | ✅ Complete (shadow/) | None |
| Live preflight | ✅ micro_live/live_preflight.py | Needs broker-specific checks |
| Production readiness checker | ✅ core/production_readiness.py | Missing: broker API connectivity test |
| MT5 gateway | ✅ broker/mt5_gateway.py | Single broker only |
| Multi-broker failover | ⚠️ config has 3 brokers | Not wired in runtime |
| IB TWS integration | ❌ Missing | Not implemented |
| Pepperstone REST API | ❌ Missing | Referenced but not built |
| Walk-forward validation gate | ✅ validation/walk_forward.py | None |

### Critical Gaps to Fill

1. **No IB TWS / Gateway integration** — config references ICMarkets/Pepperstone/XM but no actual IB adapter
2. **No broker-specific contract validation** — `contract_spec.py` exists but not enforced pre-trade
3. **No pacing limiter** — IB enforces strict rate limits; we have no request throttling per-venue
4. **No 2FA re-auth scheduler** — IB requires weekly re-auth; no automated handling exists
5. **No market data subscription validator** — IB errors on missing subscriptions; we don't pre-check

---

## 2. PRODUCTION MONITORING & ALERTING

### Industry Best Practices

**Essential Monitoring Stack:**
- **Heartbeat monitoring**: Process liveness checks every 30-60s
- **Order latency tracking**: Time from signal→order placement→fill confirmation
- **P&L monitoring**: Real-time drawdown tracking with hard limits
- **Position drift detection**: Compare expected vs. broker positions every N seconds
- **Data feed health**: Staleness detection, gap detection, spread monitoring
- **Infrastructure metrics**: CPU, memory, disk, network for trading servers
- **Broker connection status**: TCP socket health, reconnection attempts

**Alerting Tiers:**
- **INFO**: Position opened/closed, daily P&L summary
- **WARNING**: Heartbeat stale > 5min, position drift detected, spread widened
- **CRITICAL**: Kill switch triggered, broker disconnected > 15min, drawdown > threshold
- **EMERGENCY**: Multiple broker failures, data feed outage, system crash

### quant_os Current State vs. Gap Analysis

| Component | Status | Gap |
|-----------|--------|-----|
| Heartbeat monitor | ✅ monitoring/heartbeat_monitor.py | File-based only; no TCP health |
| Kill switch | ✅ risk/kill_switch.py (412L) | Complete, persistent, Telegram-integrated |
| Circuit breaker | ✅ risk/circuit_breaker.py (248L) | Per-asset-class; good |
| Telegram alerts | ✅ core/telegram_notify.py | None |
| Health check API | ✅ api/health.py | Basic; no broker deep-check |
| Grafana dashboard | ✅ monitoring/grafana/ | Template exists |
| Prometheus metrics | ✅ monitoring/prometheus_metrics.py | Needs live trading metrics |
| Dead man's switch | ✅ monitoring/dead_mans_switch.py | None |
| Log aggregation | ✅ monitoring/log_aggregator.py | Needs structured trade logging |
| Order latency tracker | ❌ Missing | Critical gap |
| Position drift detector | ⚠️ Partial (canary/position_reconciler.py) | 30 lines; too simplistic |
| Spread monitor | ✅ market_data/spread_monitor.py | None |
| Feed health | ✅ market_data/feed_health.py | None |
| Clock guard | ✅ market_data/clock_guard.py | None |
| Data watermark | ✅ market_data/data_watermark.py | None |
| Structured trade log | ⚠️ Partial (execution/trade_ledger.py) | Needs reconciliation hooks |
| P&L real-time tracker | ❌ Missing | Critical gap |
| Drawdown monitor | ⚠️ risk/portfolio.py has some | Needs dedicated real-time feed |
| Broker connection monitor | ❌ Missing | Critical gap |
| Order latency dashboard | ❌ Missing | Critical gap |

### Critical Gaps to Fill

1. **No real-time P&L tracker** — we compute P&L from ledger but no streaming aggregation
2. **No order latency measurement** — no signal→fill timing infrastructure
3. **No broker connection health monitor** — heartbeat is file-based, not TCP socket
4. **No position drift detector** — position_reconciler.py is 30 lines; needs continuous comparison
5. **No drawdown circuit breaker** — risk limits exist but no real-time enforcement loop
6. **No data staleness alerting** — feed_health exists but no escalation to kill switch

---

## 3. BROKER API FAILURES & DISCONNECTIONS

### IB TWS API Failure Modes (from official docs)

**Connection Failures:**
- `1100`: Connectivity lost (TWS/IB Gateway down)
- `1101`: Connectivity restored after loss
- `1102`: Connectivity restored — data farm reconnected
- `2100`: Data farm disconnected — no market data
- `2104`: Market data farm connection OK
- `2106`: Historical data farm disconnected
- `2108`: Historical data farm reconnected
- `1300`: TWS socket dropped — no client connected

**Authentication Failures:**
- Two-factor authentication timeout (no IB Key response)
- Session conflict: "An existing session was detected"
- Daily/weekly re-authentication required
- Invalid credentials (whitespace in password)

**Pacing Violations:**
- Max 60 historical data requests per 2 minutes
- Max 150 market data requests per 5 minutes (per security)
- Historical bar requests: max 30-second bars with pacing delays

**Order Failures:**
- "No security definition found" — invalid contract
- "Requested market data is not subscribed"
- Order pre-trade checks (IBKR precaution settings)
- "Cannot modify filled order"
- "Order would exceed account margin"

### quant_os Current State vs. Gap Analysis

| Component | Status | Gap |
|-----------|--------|-----|
| MT5 connection | ✅ mt5_connector/connection.py | Single broker |
| Broker identity guard | ✅ runtime/broker_identity_guard.py | None |
| Broker connection runtime | ✅ runtime/broker_connection.py | Basic |
| Demo disconnect drill | ✅ demo_campaign/drills.py | Tabletop only |
| Broker rejection drill | ✅ demo_campaign/drills.py | Tabletop only |
| Order timeout drill | ✅ demo_campaign/drills.py | Tabletop only |
| Auto-restart on crash | ⚠️ health_check.py watchdog | File-based; no process supervisor |
| Reconnection logic | ❌ Missing | Critical gap |
| IB-specific error handler | ❌ Missing | Critical gap |
| Pacing limiter | ❌ Missing | Critical gap |
| Session conflict handler | ❌ Missing | Critical gap |
| 2FA re-auth scheduler | ❌ Missing | Critical gap |
| Fallback broker switching | ❌ Missing | Critical gap |
| Market data subscription validator | ❌ Missing | Critical gap |

### Critical Gaps to Fill

1. **No automatic reconnection** — if broker disconnects, no retry/backoff logic exists
2. **No IB error code handler** — 200+ error codes need specific handling
3. **No pacing limiter** — will get banned by IB for rate limit violations
4. **No session conflict resolution** — IB disconnects if another client connects
5. **No 2FA automation** — IB requires weekly re-auth; no automated flow
6. **No fallback broker switching** — config has 3 brokers but no runtime failover
7. **No market data subscription pre-validator** — will fail at runtime

---

## 4. POSITION RECONCILIATION & STATE MANAGEMENT

### Industry Best Practices

**Position Reconciliation Requirements:**
- **Frequency**: Every N seconds during market hours; after every fill; after every disconnect
- **Granularity**: Symbol, quantity, avg price, P&L, margin requirement
- **Tolerance**: Allow for rounding differences (0.0001 for forex, 1 lot for futures)
- **Action on mismatch**: Alert → auto-close orphan positions → kill switch if > threshold
- **Audit trail**: Every reconciliation attempt logged with timestamp, expected vs. actual

**State Management Requirements:**
- **Atomic persistence**: State file writes must be atomic (temp + rename)
- **Idempotent operations**: Order placement must be idempotent (deduplicate by client_order_id)
- **Crash recovery**: On restart, reconcile state from broker before resuming trading
- **State versioning**: Migrate state files across versions
- **Corruption detection**: Checksum or hash on state files

### quant_os Current State vs. Gap Analysis

| Component | Status | Gap |
|-----------|--------|-----|
| Execution ledger | ✅ execution/ledger.py | Good; append-only |
| Reconcile module | ✅ execution/reconcile.py (321L) | Venue-level; good |
| Reconciler module | ✅ execution/reconciler.py | Duplicate? |
| Position reconciler | ⚠️ canary/position_reconciler.py | 30 lines; too simple |
| Protective stop verifier | ✅ canary/protective_stop_verifier.py | None |
| State store | ✅ core/state_store.py | File-based |
| State coordinator | ✅ core/state_coordinator.py | Cross-store sync |
| Kill switch persistence | ✅ risk/kill_switch.py | Atomic writes |
| Order state machine | ✅ execution/order_state_machine.py | None |
| Idempotency | ✅ execution/idempotency.py | None |
| Recovery module | ✅ execution/recovery.py | None |
| DB reconciliation logs | ✅ alembic (quant_reconciliation_logs) | Schema exists |
| Trade ledger integrity | ✅ execution/ledger_integrity.py | None |
| Provenance tracking | ✅ execution/provenance.py | None |
| Broker fill tracking | ⚠️ execution/quality_tracker.py | Needs reconciliation hook |
| Crash recovery on restart | ⚠️ execution/recovery.py | Exists but untested in live |
| Cross-venue reconciliation | ⚠️ reconcile.py multi-venue | Needs more tolerance config |
| Position state persistence | ⚠️ state_store.py | File-based; no DB persistence |

### Critical Gaps to Fill

1. **Position reconciler too thin** — 30 lines doesn't handle: orphan positions, partial fills, margin mismatches
2. **No continuous reconciliation loop** — reconcile happens on-demand, not every N seconds
3. **No orphan position detection** — positions in broker but not in our ledger
4. **No margin requirement tracking** — IB/margin brokers require margin monitoring
5. **No state migration** — if state file format changes, no migration path
6. **No crash recovery drill** — recovery.py exists but never tested in actual crash scenario

---

## 5. COMMON PRODUCTION INCIDENTS & PREVENTION

### Top 10 Algorithmic Trading Incidents (Industry Data)

| # | Incident | Cause | Prevention |
|---|----------|-------|------------|
| 1 | **Flash crash loss** | Algorithm entered during extreme volatility | Volatility circuit breaker + spread guard |
| 2 | **Duplicate order execution** | Broker reconnect + stale order state | Idempotency keys + order state machine |
| 3 | **Position drift** | Fill not reported to algo in time | Continuous reconciliation loop |
| 4 | **Data feed stale** | Provider outage; algo traded on old data | Staleness detection + data watermark |
| 5 | **API rate limit ban** | Too many requests to broker | Pacing limiter per-venue |
| 6 | **Auth expiration** | 2FA/session timeout during trading hours | Automated re-auth scheduler |
| 7 | **Contract rollover** | Expired futures contract not rolled | Rollover filter + contract snapshot |
| 8 | **Kill switch failure** | Kill switch state file corrupted | Atomic writes + corruption quarantine |
| 9 | **Slippage blowout** | Wide spread during news event | Spread monitor + news blackout |
| 10 | **Memory leak** | Long-running process OOM | Process supervisor + restart policy |

### quant_os Drill Coverage Analysis

| Drill | Status | Effectiveness |
|-------|--------|---------------|
| Kill switch | ✅ drills.py | Good — tests activation |
| MT5 disconnection | ✅ drills.py | Tabletop only; no real disconnect |
| Stale tick | ✅ drills.py | Good — tests staleness detection |
| Wide spread | ✅ drills.py | Good — tests spread guard |
| Contract change | ✅ drills.py | Good — tests rollover |
| Broker rejection | ✅ drills.py | Tabletop only; no real rejection |
| Order timeout | ✅ drills.py | Tabletop only; no real timeout |
| Position mismatch | ✅ drills.py | Tabletop only; no real mismatch |
| Missing SL/TP | ✅ drills.py | Good — tests protective stops |
| Restart recovery | ✅ drills.py | Tabletop only; no real restart |
| Telemetry outage | ✅ drills.py | Good — tests observability |

### Prevention Strategies for quant_os

1. **Real chaos testing** — drills.py is tabletop; need actual process kill, network partition, broker mock
2. **Pre-trade risk gate** — ✅ exists (risk/pre_trade_gate.py) but needs IB-specific checks
3. **Order lifecycle tracking** — ✅ exists (canary/order_lifecycle.py) but needs fill verification
4. **Shadow mode validation** — ✅ exists (shadow/) — this is the right pattern
5. **Blue-green deployment** — ✅ exists (deploy/blue_green.py) — good for zero-downtime deploys

---

## 6. INFRASTRUCTURE GAP SUMMARY

### Priority 1: CRITICAL (Must-have before live trading)

| Gap | Impact | Effort | Files Needed |
|-----|--------|--------|--------------|
| **Broker reconnection logic** | Disconnected algo continues trading on stale state | Medium | `broker/reconnector.py` |
| **Continuous position reconciliation** | Position drift causes unbounded risk | Medium | `execution/continuous_reconciler.py` |
| **Real-time P&L tracker** | No drawdown enforcement in real-time | Medium | `monitoring/pnl_tracker.py` |
| **Order latency measurement** | No visibility into execution quality | Low | `monitoring/order_latency.py` |
| **IB pacing limiter** | Rate limit ban = no market data | Low | `broker/pacing_limiter.py` |

### Priority 2: HIGH (Before scaling beyond demo)

| Gap | Impact | Effort | Files Needed |
|-----|--------|--------|--------------|
| **Fallback broker switching** | Single point of failure | High | `broker/failover.py` |
| **2FA re-auth scheduler** | IB sessions expire weekly | Medium | `broker/auth_scheduler.py` |
| **Market data subscription validator** | Runtime failures on missing data | Low | `broker/data_validator.py` |
| **Crash recovery drill** | Untested recovery path | Medium | `tests/test_crash_recovery.py` |
| **State migration system** | State file format changes break live | Medium | `core/state_migrator.py` |

### Priority 3: MEDIUM (Before production graduation)

| Gap | Impact | Effort | Files Needed |
|-----|--------|--------|--------------|
| **IB error code handler** | Unknown errors cause silent failures | Medium | `broker/ib_error_handler.py` |
| **Margin requirement monitor** | Margin call risk | Medium | `risk/margin_monitor.py` |
| **Real chaos testing suite** | Tabletop drills don't catch real bugs | High | `tests/chaos/` expansion |
| **Process supervisor** | No auto-restart on crash | Low | `infra/supervisor.py` |
| **State versioning** | State format changes break live | Low | `core/state_version.py` |

---

## 7. RECOMMENDED PRODUCTION ARCHITECTURE

```
┌─────────────────────────────────────────────────────────┐
│                    MONITORING LAYER                      │
│  heartbeat_monitor ── pnl_tracker ── order_latency      │
│  spread_monitor ── feed_health ── clock_guard            │
│  grafana/prometheus ── telegram_alerts ── loki           │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    RISK LAYER                            │
│  kill_switch ── circuit_breaker ── pre_trade_gate        │
│  position_sizer ── portfolio_heat ── auto_stop           │
│  continuous_reconciler ── margin_monitor                 │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  EXECUTION LAYER                         │
│  signal_gateway ── order_state_machine ── ledger         │
│  idempotency ── reconciler ── recovery                   │
│  pacing_limiter ── reconnector ── auth_scheduler         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   BROKER LAYER                           │
│  MT5 gateway ── IB adapter ── Pepperstone adapter        │
│  failover ── contract_spec ── data_validator             │
│  broker_identity_guard ── session_manager                │
└─────────────────────────────────────────────────────────┘
```

---

## 8. IB TWS API INTEGRATION NOTES

### Key Technical Details for Implementation

**Architecture:**
- TCP Socket Protocol to TWS or IB Gateway
- Client ID based multi-session (ClientId 0 = Master Client ID)
- EReader thread required for async message handling

**Connection Requirements:**
- TWS/IB Gateway must be running (desktop app or headless IB Gateway)
- Port 7497 (TWS) or 4002 (IB Gateway) for live; 7496/4001 for paper
- "Never Lock Trader Workstation" must be enabled
- Memory allocation: increase from default for heavy usage

**Critical Settings:**
- Order Precautions: configure maximum order size, price, notional value
- "Disconnect on Invalid Format": should be enabled for safety
- Per-Currency Account Value Prefix: affects account value reporting
- SMART Routing: use for best execution across venues

**Error Handling Required:**
- 200+ error codes documented at ibkrcampus.com
- Common: 321 (invalid format), 322 (duplicate order), 502 (couldn't connect)
- Market data farm errors (2100-2108): must handle reconnection
- Pacing violations: must implement request queuing

**Python API:**
- ib_insync / ib_async: third-party async wrapper (not official)
- Official Python API requires TWS API installation
- Minimum Python 3.11.0
- Protobuf serialization (recent migration from binary)

---

## 9. QUANTCONNECT LEAN PATTERNS TO ADOPT

### From QuantConnect's IB Integration

1. **Weekly restart scheduling** — IB requires re-auth; schedule during market hours
2. **Delayed market data fallback** — When subscription missing, use delayed data instead of crashing
3. **Hybrid data provider** — QuantConnect data + IB execution (we could do: our data + broker execution)
4. **Algorithm control API** — Submit/cancel/liquidate orders while algo is running
5. **Automatic restarting** — Restart algo on runtime error (brokerage disconnection)

### From QuantConnect's Error Handling

1. **"Login failed"** — Password whitespace check; TWS vs. deployment wizard mismatch
2. **"An existing session was detected"** — IB disconnects old session; algo must detect and reconnect
3. **"Two factor authentication request timed out"** — Must respond within window
4. **"No market data permissions"** — Pre-validate subscriptions before trading
5. **"Timeout waiting for brokerage response"** — Order timeout; must retry or cancel

---

## 10. ACTION ITEMS FOR quant_os

### Immediate (This Week)

- [ ] Add continuous reconciliation loop to trading_loop.py (every 60s)
- [ ] Add order latency measurement to order_state_machine.py
- [ ] Add P&L real-time tracker to monitoring/
- [ ] Write chaos test: actual process kill + recovery
- [ ] Add broker connection health check (TCP socket, not file-based)

### Short-Term (This Month)

- [ ] Implement broker reconnection with exponential backoff
- [ ] Add IB pacing limiter (request queue + rate tracking)
- [ ] Add market data subscription pre-validator
- [ ] Implement 2FA re-auth scheduler for IB
- [ ] Add margin requirement monitor

### Medium-Term (Before Live)

- [ ] Implement IB TWS adapter (broker/ib_adapter.py)
- [ ] Implement fallback broker switching
- [ ] Add IB error code handler
- [ ] State migration system
- [ ] Process supervisor (systemd / Docker restart policy)
- [ ] Real chaos testing suite (not tabletop)

---

## REFERENCES

1. IB TWS API Documentation: https://ibkrcampus.com/ibkr-api-page/twsapi-doc/
2. IB API Error Codes: https://ibkrcampus.com/ibkr-api-page/twsapi-doc/#api-error-codes
3. IB Pacing Limitations: https://ibkrcampus.com/ibkr-api-page/twsapi-doc/#paceapi
4. QuantConnect LEAN CLI Live Trading: https://www.quantconnect.com/docs/v2/lean-cli/live-trading
5. QuantConnect IB Integration: https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers
6. QuantConnect Algorithm Control: https://www.quantconnect.com/docs/v2/lean-cli/live-trading/algorithm-control
7. IB API Software Downloads: https://interactivebrokers.github.io/
