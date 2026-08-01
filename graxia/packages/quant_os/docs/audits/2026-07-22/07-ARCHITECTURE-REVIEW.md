# ARCHITECTURE REVIEW — quant_os

**Date:** 2026-07-22
**Scope:** System architecture analysis
**Auditor:** Automated (evidence-based)

---

## 1. ARCHITECTURE OVERVIEW

### System Type
- **Domain:** Algorithmic Trading Platform
- **Pattern:** Event-Driven Architecture with 4-Layer Risk Engine
- **Deployment:** Monolith (modular Python package)

### Architecture Style
```
┌─────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                     │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────────┐ │
│  │ Orders  │ │ Positions│ │  Risk   │ │ Webhook/TradingV │ │
│  └────┬────┘ └────┬─────┘ └────┬────┘ └────────┬─────────┘ │
│       │           │            │                │           │
│  ┌────▼───────────▼────────────▼────────────────▼─────────┐ │
│  │              EVENT BUS (core/events.py)                │ │
│  │  BarEvent → TickEvent → SignalEvent → OrderEvent       │ │
│  └───────────────────────┬───────────────────────────────┘ │
│                          │                                 │
│  ┌───────────────────────▼───────────────────────────────┐ │
│  │           TRADING ORCHESTRATOR (core/orchestrator.py)  │ │
│  │  ┌──────────┬──────────┬──────────┬────────────────┐  │ │
│  │  │ Strategies│ Risk Eng │ Order Mgr│ Market Health  │  │ │
│  │  └──────────┴──────────┴──────────┴────────────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              BROKER ADAPTERS (execution/adapters/)     │ │
│  │  ┌────────┐ ┌────────────┐ ┌──────────┐ ┌─────────┐  │ │
│  │  │  MT5   │ │ IC Markets │ │Pepperstone│ │   XM    │  │ │
│  │  └────────┘ └────────────┘ └──────────┘ └─────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. COMPONENT ANALYSIS

### 2.1 API Layer (api/)
**Responsibility:** HTTP interface, authentication, rate limiting

**Components:**
- `main.py` — FastAPI app, lifespan, middleware
- `auth.py` — JWT + API key authentication
- `rate_limit.py` — Request throttling
- `webhook.py` — TradingView signal ingestion
- `admin.py` — System administration
- `orders.py` — Order CRUD
- `positions.py` — Position management
- `risk.py` — Risk queries

**Assessment:** ✅ Well-structured
- Clean separation of concerns
- Proper middleware chain
- Correlation IDs for tracing

### 2.2 Core Business Logic (core/)
**Responsibility:** Domain models, events, configuration

**Components:**
- `config.py` — QuantConfig (346L)
- `enums.py` — System enums (264L)
- `events.py` — Event types (217L)
- `golden_rules.py` — Immutable constraints (114L)
- `orchestrator.py` — Trading loop
- `exceptions.py` — Custom exceptions

**Assessment:** ✅ Strong domain modeling
- Frozen dataclass for golden rules
- Comprehensive enum coverage
- Event-driven communication

### 2.3 Execution Layer (execution/)
**Responsibility:** Order lifecycle management

**Components:**
- `manager.py` — OrderManager (478L)
- `order.py` — Order state machine
- `idempotency.py` — Duplicate prevention
- `smart_router.py` — Order routing
- `adapters/` — Broker integrations

**Assessment:** ✅ Robust
- State machine pattern for orders
- Multi-broker failover
- Idempotency checking

### 2.4 Risk Management (risk/)
**Responsibility:** Pre-trade validation, position limits

**Components:**
- `engine.py` — 4-Layer Risk Engine (625L)
- `risk_policy.py` — RiskPolicy (105L)
- `kill_switch.py` — Emergency stop
- `circuit_breaker.py` — Auto-halt
- `pre_trade_risk.py` — Pre-trade checks

**Assessment:** ✅ Excellent
- 4-layer defense in depth
- Immutable risk policy
- Multiple kill triggers

### 2.5 Market Data (market_data/)
**Responsibility:** Data ingestion, validation, health monitoring

**Components:**
- `unified_loader.py` — Multi-source loader
- `providers.py` — Data provider abstraction
- `market_health.py` — Health state machine (284L)
- `market_session_guard.py` — Session hours
- `spread_monitor.py` — Spread monitoring
- `clock_guard.py` — Clock drift detection
- `feed_health.py` — Feed health
- `tick_store.py` — Tick storage
- `data_watermark.py` — Data quality marks

**Assessment:** ✅ Comprehensive
- State machine for health
- Multiple validation layers
- Data quality tracking

### 2.6 Monitoring (monitoring/)
**Responsibility:** Observability, alerting, health checks

**Components:**
- `metrics.py` — Prometheus metrics
- `health_check.py` — Health + failover (83L)
- `alerting.py` — Alert system
- `heartbeat_monitor.py` — Heartbeat tracking

**Assessment:** ⚠️ Adequate but needs enhancement
- Basic monitoring present
- Missing: distributed tracing, log aggregation

---

## 3. DESIGN PATTERNS

### 3.1 Event-Driven Architecture
```python
# Evidence: core/events.py
class Event: ...
class BarEvent(Event): ...
class TickEvent(Event): ...
class SignalEvent(Event): ...
class OrderEvent(Event): ...
class FillEvent(Event): ...
```

**Assessment:** ✅ Proper implementation
- Typed events with metadata
- Async event bus
- Clear event hierarchy

### 3.2 State Machine Pattern
```python
# Evidence: execution/order.py
class OrderStateMachine: ...
```

**Assessment:** ✅ Correct usage
- Valid state transitions enforced
- Event-driven state changes
- Audit trail maintained

### 3.3 Strategy Pattern
```python
# Evidence: strategies/base.py
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, bar): ...
    def should_long(self) -> bool: ...
    def should_short(self) -> bool: ...
```

**Assessment:** ✅ Well-designed
- Template method pattern
- Jesse-inspired ergonomics
- Hyperparameter support for Optuna

### 3.4 Adapter Pattern
```python
# Evidence: execution/adapters/base.py
class BrokerAdapter(ABC): ...
class MT5Adapter(BrokerAdapter): ...
```

**Assessment:** ✅ Clean abstraction
- Unified broker interface
- Easy to add new brokers
- Failover support

### 3.5 State Machine (Market Health)
```python
# Evidence: market_data/market_health.py
class MarketHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    STALE_FEED = "STALE_FEED"
    WIDE_SPREAD = "WIDE_SPREAD"
    ...
```

**Assessment:** ✅ Excellent
- Priority-ordered states
- Only HEALTHY permits orders
- Clear state transitions

---

## 4. DEPENDENCY ANALYSIS

### 4.1 Dependency Injection
```python
# Evidence: core/config.py
@dataclass
class QuantConfig:
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
```

**Assessment:** ⚠️ Partial
- Config uses default factories
- No formal DI container
- Some tight coupling in orchestrator

### 4.2 Coupling Analysis
```
Low Coupling:
✅ api/ → core/ (clean interface)
✅ strategies/ → core/ (event-based)
✅ risk/ → core/ (policy-based)

Medium Coupling:
⚠️ execution/ → risk/ (direct dependency)
⚠️ core/ → market_data/ (health check)

High Coupling:
❌ orchestrator.py → everything (God object risk)
```

### 4.3 Cohesion Analysis
```
High Cohesion:
✅ risk/ (single responsibility)
✅ market_data/ (focused domain)
✅ monitoring/ (observability)

Medium Cohesion:
⚠️ core/ (mixed concerns: config + events + models)

Low Cohesion:
❌ orchestrator.py (too many responsibilities)
```

---

## 5. SCALABILITY ASSESSMENT

### 5.1 Current Limitations
1. **Single-process architecture** — No horizontal scaling
2. **Synchronous broker calls** — MT5 adapter blocks
3. **In-memory state** — No shared state across instances
4. **DuckDB single-writer** — Concurrent write limitations

### 5.2 Scaling Strategies
| Strategy | Effort | Impact |
|----------|--------|--------|
| Add worker pool | Medium | Horizontal scaling |
| Async broker calls | Low | Better throughput |
| Redis state sharing | Medium | Multi-instance |
| PostgreSQL migration | High | Better concurrency |

### 5.3 Capacity Planning
- **Current:** Single VPS, 1-2 symbols
- **Target:** Multi-symbol, multi-strategy
- **Bottleneck:** MT5 connection (single thread)

---

## 6. RELIABILITY ANALYSIS

### 6.1 Failure Modes
| Mode | Impact | Mitigation |
|------|--------|------------|
| MT5 disconnect | No orders | Broker failover |
| Market data gap | Bad signals | Health state machine |
| Memory leak | Crash | Watchdog restart |
| Clock drift | Bad timestamps | Clock guard |
| Network partition | No data | Feed health monitor |

### 6.2 Recovery Mechanisms
- **Kill switch:** Manual + automated
- **Watchdog:** Process restart
- **Failover:** Standby VPS
- **Circuit breaker:** Auto-halt on failures

### 6.3 Data Durability
- **DuckDB:** File-based, durable
- **Redis:** Volatile cache (acceptable)
- **Logs:** File-based (need rotation)

---

## 7. SECURITY ARCHITECTURE

### 7.1 Defense in Depth
```
Layer 1: API Gateway (auth, rate limiting)
Layer 2: Risk Engine (4-layer validation)
Layer 3: Market Health (state machine gating)
Layer 4: Golden Rules (immutable constraints)
Layer 5: Kill Switch (emergency stop)
```

### 7.2 Trust Boundaries
```
External (TradingView) → [Webhook] → Internal
Internal → [Risk Engine] → Broker
Broker → [Market] → External
```

### 7.3 Security Controls
- ✅ Authentication (JWT + API key)
- ✅ Authorization (role-based)
- ✅ Input validation (Pydantic)
- ✅ Rate limiting
- ✅ Kill switch
- ⚠️ Audit logging (needs enhancement)
- ❌ Encryption at rest (not implemented)

---

## 8. MAINTAINABILITY

### 8.1 Code Organization
**Score: 8/10**
- Clear module boundaries
- Consistent naming conventions
- Type hints throughout

### 8.2 Documentation
**Score: 6/10**
- Many audit docs (30+)
- Needs consolidation
- Missing: API docs, architecture diagrams

### 8.3 Testing
**Score: 7/10**
- 2920 tests
- No coverage measurement
- Missing: integration tests, chaos tests

### 8.4 Refactoring Needs
1. **Orchestrator.py** — Extract responsibilities
2. **Config.py** — Split into smaller configs
3. **Monitoring** — Add distributed tracing

---

## 9. ARCHITECTURAL RECOMMENDATIONS

### 9.1 Immediate (Low Effort)
1. Extract orchestrator into smaller services
2. Add API documentation (OpenAPI)
3. Implement coverage measurement

### 9.2 Short-Term (Medium Effort)
1. Add distributed tracing (OpenTelemetry)
2. Implement circuit breaker pattern
3. Add health check endpoints

### 9.3 Long-Term (High Effort)
1. Migrate to microservices (if scaling needed)
2. Add event sourcing for audit trail
3. Implement CQRS for read/write separation

---

## 10. ARCHITECTURE SCORE

| Dimension | Score | Notes |
|-----------|-------|-------|
| Modularity | 8/10 | Clean module boundaries |
| Scalability | 6/10 | Single-process limitation |
| Reliability | 8/10 | Good failure handling |
| Security | 8/10 | Defense in depth |
| Maintainability | 7/10 | Needs documentation |
| Performance | 7/10 | Some sync bottlenecks |
| Observability | 6/10 | Basic monitoring only |

**Overall Architecture Score: 7.1/10**
