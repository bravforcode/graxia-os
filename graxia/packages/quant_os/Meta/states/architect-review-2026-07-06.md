# Quant OS Architecture Review — 2026-07-06

## 1. Executive Summary

Quant OS is a **production-grade quantitative trading system** with event-driven architecture, 4-layer risk engine, multi-strategy ensemble, and staged live-readiness pipeline (Paper → Shadow → Canary → Micro → Limited → Controlled). The codebase is **~150+ Python files** across 15+ modules with **150+ test files**.

**Overall Assessment: B+ (Strong with gaps)**
- ✅ Excellent: Risk architecture, event-driven design, kill switch resilience
- ⚠️ Moderate: Circular dependency risks, test coverage gaps, security surface
- ❌ Critical: Some import-time side effects, dual Order dataclasses

---

## 2. Architecture Diagram (Text)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER (FastAPI)                         │
│  main.py ─── webhook.py ─── signal_service.py ─── rate_limit.py    │
│  admin.py ─── health.py ─── orders.py ─── positions.py ─── risk.py │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP/WebSocket
┌──────────────────────────▼──────────────────────────────────────────┐
│                     ORCHESTRATOR (core/orchestrator.py)              │
│  EventBus ← → TradingOrchestrator → Agents → TradingLoop → OMS     │
└──┬───────────────┬───────────────┬──────────────┬───────────────────┘
   │               │               │              │
┌──▼─────┐  ┌──────▼──────┐  ┌────▼─────┐  ┌────▼────────────────┐
│ EVENTS │  │   AGENTS    │  │ STRATEGIES│  │  RISK ENGINE        │
│        │  │             │  │           │  │                     │
│ BarEvt │  │ RiskAuditor │  │ base.py   │  │ engine.py (4-layer) │
│ SigEvt │  │ PortfolioMgr│  │ ensemble  │  │ kill_switch.py      │
│ FillEvt│  │ SignalValid │  │ mtm.py    │  │ circuit_breaker.py  │
│ KSEvt  │  │ Sentiment   │  │ mrb.py    │  │ risk_policy.py      │
│ Trades │  │ Correlation │  │ mlb.py    │  │ pre_trade_risk.py   │
│        │  │ HealthMon   │  │ walk_fwd  │  │ portfolio_heat.py   │
└──┬─────┘  └──────┬──────┘  └────┬─────┘  └────┬────────────────┘
   │               │               │              │
┌──▼───────────────▼───────────────▼──────────────▼───────────────────┐
│                    EXECUTION LAYER                                  │
│  oms.py ─── order.py ─── order_state_machine.py ─── ledger.py      │
│  adapters/base.py ─── adapters/mt5.py ─── adapters/paper.py        │
│  adapters/manager.py (failover) ─── adapters/binance.py            │
└──┬──────────────────────────────────────────────────────────────────┘
   │
┌──▼──────────────────────────────────────────────────────────────────┐
│                    BROKER LAYER                                     │
│  broker/mt5_gateway.py ─── broker/contract_spec.py                  │
│  live_readiness/ ─── shadow/ ─── canary/                           │
└─────────────────────────────────────────────────────────────────────┘
   │
┌──▼──────────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE                                    │
│  market_data/ ─── data_pipeline/ ─── data/                         │
│  backtest/engine.py ─── backtest/data_loader.py                    │
│  validation/ ─── artifacts/ ─── reports/                           │
└─────────────────────────────────────────────────────────────────────┘
   │
┌──▼──────────────────────────────────────────────────────────────────┐
│                    MONITORING & OBSERVABILITY                       │
│  monitoring/metrics.py ─── monitoring/alerting.py                  │
│  monitoring/health_check.py ─── monitoring/heartbeat.py            │
│  monitoring/prometheus_metrics.py ─── monitoring/grafana/           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Module Inventory

### 3.1 CORE (67 files)

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `config.py` | Global configuration, env overrides, hard limits | `QuantConfig`, `get_config()` |
| `enums.py` | System-wide enums (263 lines, 20+ enums) | `SystemState`, `OrderStatus`, `RegimeType`, `KillSwitchType`, etc. |
| `event_bus.py` | In-process pub/sub, sync+async, class+string routing | `EventBus` |
| `events.py` | Event vocabulary (frozen dataclasses) | `SignalEvent`, `FillEvent`, `KillSwitchEvent`, etc. |
| `exceptions.py` | Typed exception hierarchy (14 classes) | `RiskViolationError`, `KillSwitchTriggeredError`, etc. |
| `golden_rules.py` | Non-negotiable constraints, hardcoded | `GOLDEN_RULES`, `HARD_LIMITS` |
| `orchestrator.py` | Wires all components on startup | `TradingOrchestrator` |
| `trading_loop.py` | Signal → Order → Fill pipeline | `TradingLoop`, `PaperExecutor` |
| `position_manager.py` | Persistent position tracking (Parquet) | `PositionManager`, `Position` |
| `state_coordinator.py` | Kill switch state sync across 5 stores | `StateCoordinator` |
| `risk_policy.py` | Immutable risk policy (frozen dataclass, bps) | `RiskPolicy` |
| `safe_pickle.py` | Secure pickle loading (RestrictedUnpickler) | `safe_load_model()` |
| `smc_detectors.py` | Smart Money Concepts pattern detection | SMC detectors |
| `candle_pipeline.py` | Candle data processing pipeline | Candle pipeline |
| `correlation.py` | Cross-asset correlation calculations | Correlation engine |
| `cost_model.py` | Trading cost estimation | Cost model |
| `kelly.py` | Kelly criterion position sizing | Kelly sizing |
| `monte_carlo.py` | Monte Carlo simulation | MC engine |
| `ml_pipeline.py` | ML training pipeline | ML pipeline |
| `dashboard.py` | Dashboard generation | Dashboard |
| `telegram_notify.py` | Telegram notifications | Notifier |
| `observability.py` | Observability hooks | Observability |
| `agents/` (15 files) | AI agent subsystem | RiskAuditor, PortfolioManager, SignalValidator, etc. |

### 3.2 EXECUTION (32 files)

| File | Purpose | Key Classes |
|------|---------|-------------|
| `oms.py` | Order Management System — multi-venue router | `OMS` |
| `order.py` | Order entity + state machine | `Order`, `OrderStateMachine` |
| `order_state_machine.py` | State transition validation | `OrderStateMachine` |
| `ledger.py` | Trade ledger (JSONL event sourcing) | Ledger |
| `idempotency.py` | Duplicate order prevention | Idempotency guard |
| `reconciler.py` | Position reconciliation | Reconciler |
| `adapters/base.py` | Abstract broker adapter interface | `BrokerAdapter` |
| `adapters/mt5.py` | MetaTrader 5 adapter | `MT5Adapter` |
| `adapters/paper.py` | Paper trading adapter | `PaperAdapter` |
| `adapters/manager.py` | Failover manager | `BrokerManager` |
| `adapters/binance.py` | Binance adapter | `BinanceAdapter` |
| `execution_simulator.py` | Backtest execution simulation | Simulator |
| `slippage_guard.py` | Slippage protection | Guard |
| `swap_model.py` | Swap/rollover cost model | Swap model |
| `tca_metrics.py` | Transaction Cost Analysis | TCA |

### 3.3 RISK (25 files)

| File | Purpose | Key Classes |
|------|---------|-------------|
| `engine.py` | 4-layer risk engine (pre-trade gate) | `RiskEngine`, `Signal`, `RiskVerdict` |
| `risk_policy.py` | Immutable risk limits (bps) | `RiskPolicy` (frozen) |
| `kill_switch.py` | Persistent kill switch + Telegram | `KillSwitch`, `CloseMode` |
| `circuit_breaker.py` | Per-asset-class circuit breaker | `CircuitBreaker` |
| `pre_trade_risk.py` | Pre-trade risk gate | Pre-trade gate |
| `position_sizer.py` | Position sizing calculator | Sizer |
| `position_sizer_v2.py` | Enhanced position sizing (INV-007) | Sizer v2 |
| `portfolio_heat.py` | Portfolio heat monitoring | Heat monitor |
| `realtime_pnl.py` | Real-time PnL tracking | PnL tracker |
| `auto_stop.py` | Automatic stop-loss management | Auto stop |
| `correlation_provider.py` | Correlation data for risk checks | Correlation |
| `stress_test.py` | Stress testing framework | Stress test |
| `margin_simulator.py` | Margin level simulation | Margin sim |
| `risk_ledger.py` | Risk decision audit trail | Risk ledger |

### 3.4 STRATEGIES (8 files)

| File | Purpose | Key Classes |
|------|---------|-------------|
| `base.py` | Abstract strategy base (jesse-inspired) | `Strategy`, `Signal`, `StrategyConfig` |
| `ensemble.py` | Multi-strategy signal combiner | `StrategyEnsemble` |
| `mtm.py` | Multi-Timeframe Momentum | MTM strategy |
| `mrb.py` | Mean Reversion Bollinger | MRB strategy |
| `mlb.py` | ML-Enhanced Breakout | MLB strategy |
| `walk_forward.py` | Walk-forward optimization | WF engine |

### 3.5 API (22 files)

| File | Purpose | Key Classes |
|------|---------|-------------|
| `main.py` | FastAPI app, CORS, middleware, lifespan | `create_app()` |
| `signal_service.py` | MQL5 EA signal endpoint (XGBoost) | Signal service |
| `webhook.py` | TradingView webhook (HMAC auth) | Webhook router |
| `rate_limit.py` | Redis/in-memory rate limiter | `RateLimitMiddleware` |
| `admin.py` | Admin API routes | Admin router |
| `health.py` | Health check endpoints | Health router |
| `orders.py` | Order management API | Orders router |
| `positions.py` | Position query API | Positions router |
| `risk.py` | Risk status API | Risk router |

### 3.6 BACKTEST (18 files)

| File | Purpose |
|------|---------|
| `engine.py` | Backtesting engine |
| `data_loader.py` | Historical data loading |
| `walk_forward.py` | Walk-forward analysis |
| `metrics.py` | Backtest metrics computation |
| `continuous_spread.py` | Spread modeling |
| `fill_timing_model.py` | Fill timing simulation |

### 3.7 VALIDATION (45 files)

| File | Purpose |
|------|---------|
| `overfitting_detector.py` | Anti-overfitting validation |
| `deflated_sharpe.py` | Deflated Sharpe ratio |
| `walk_forward.py` | Walk-forward validation |
| `exit_gate.py` | Exit gate validation |
| `decision_gates.yaml` | Phase promotion gates |
| `evidence_pack.py` | Evidence packaging |
| `regime_detector.py` | Regime detection |

### 3.8 MARKET DATA (13 files)

| File | Purpose |
|------|---------|
| `ccxt_feeder.py` | CCXT data feed |
| `tick_store.py` | Tick data storage |
| `spread_monitor.py` | Spread monitoring |
| `market_health.py` | Market health checks |
| `clock_guard.py` | Time synchronization |

### 3.9 SHADOW (43 files) — Shadow Trading Pipeline

Shadow mode runs real gates and lifecycle without order submission.

### 3.10 CANARY (32 files) — Demo Canary System

Demo canary runs simulated live trading with real risk checks.

### 3.11 MONITORING (27 files)

| File | Purpose |
|------|---------|
| `alerting.py` | Alert management |
| `health_check.py` | System health checks |
| `heartbeat.py` | Heartbeat monitoring |
| `prometheus_metrics.py` | Prometheus integration |
| `grafana/` | Grafana dashboards |

---

## 4. Dependency Graph

### 4.1 Core Dependency Flow

```
core/config.py ──→ core/enums.py
core/config.py ──→ risk/risk_policy.py
core/config.py ──→ core/golden_rules.py

core/event_bus.py ──→ core/events.py
core/events.py ──→ core/enums.py

core/orchestrator.py ──→ core/event_bus.py
core/orchestrator.py ──→ core/config.py
core/orchestrator.py ──→ core/agents/*
core/orchestrator.py ──→ execution/oms.py
core/orchestrator.py ──→ execution/adapters/*
core/orchestrator.py ──→ core/trading_loop.py
core/orchestrator.py ──→ core/position_manager.py

core/trading_loop.py ──→ core/event_bus.py
core/trading_loop.py ──→ core/events.py
core/trading_loop.py ──→ core/golden_rules.py
```

### 4.2 Execution Dependency Flow

```
execution/oms.py ──→ execution/adapters/base.py
execution/oms.py ──→ execution/order_state_machine.py
execution/adapters/mt5.py ──→ execution/adapters/base.py
execution/adapters/paper.py ──→ execution/adapters/base.py
execution/adapters/manager.py ──→ execution/adapters/*
execution/adapters/manager.py ──→ core/config.py
```

### 4.3 Risk Dependency Flow

```
risk/engine.py ──→ risk/risk_policy.py
risk/kill_switch.py ──→ (standalone, JSON persistence)
risk/circuit_breaker.py ──→ risk/kill_switch.py (optional)
risk/circuit_breaker.py ──→ (standalone, JSON persistence)
```

### 4.4 Strategy Dependency Flow

```
strategies/base.py ──→ core/enums.py
strategies/ensemble.py ──→ strategies/base.py
strategies/mtm.py ──→ strategies/base.py
strategies/mrb.py ──→ strategies/base.py
strategies/mlb.py ──→ strategies/base.py
```

### 4.5 API Dependency Flow

```
api/main.py ──→ core/config.py
api/main.py ──→ core/orchestrator.py
api/main.py ──→ core/golden_rules.py
api/main.py ──→ execution/adapters/manager.py
api/main.py ──→ api/rate_limit.py
api/webhook.py ──→ core/config.py
api/webhook.py ──→ execution/manager.py
api/webhook.py ──→ risk/engine.py
api/signal_service.py ──→ core/safe_pickle.py
```

---

## 5. Security Audit Findings

### 5.1 CRITICAL

| # | Finding | File | Risk |
|---|---------|------|------|
| S1 | **Two different Order dataclasses** exist: `execution/order.py` (Decimal-based, full validation) vs `execution/adapters/base.py` (float-based, simplified). The OMS uses `adapters/base.py` Order while the state machine uses `order.py` Order. **Type confusion risk.** | `execution/order.py`, `execution/adapters/base.py` | HIGH |
| S2 | **Webhook imports `revenue_os.db`** — cross-package dependency that may not exist in all deployments | `api/webhook.py:33` | MEDIUM |
| S3 | **`signal_service.py` has standalone FastAPI app** (line 1: `from __future__ import annotations`) — runs as separate process, has its own rate limiter that doesn't share with main app | `api/signal_service.py` | MEDIUM |

### 5.2 HIGH

| # | Finding | File | Risk |
|---|---------|------|------|
| S4 | **No JWT validation on most API routes** — `HTTPBearer(auto_error=False)` means unauthenticated requests pass through silently | `api/main.py:28` | HIGH |
| S5 | **Admin routes have no auth middleware** — `/api/v1/admin/*` endpoints accessible without authentication | `api/admin.py` | HIGH |
| S6 | **HMAC secret in env** — `webhook_hmac_secret` loaded from env, but `.env.example` doesn't include it (uses `TV_WEBHOOK_SECRET` instead) | `core/config.py`, `.env.example` | MEDIUM |

### 5.3 MEDIUM

| # | Finding | File | Risk |
|---|---------|------|------|
| S7 | **Safe pickle allowlist includes `numpy.ma.core.MaskedArray`** — wider than necessary | `core/safe_pickle.py:46` | LOW |
| S8 | **Kill switch state file uses `json.loads()` without size limit** — potential DoS via large file | `risk/kill_switch.py:346` | LOW |
| S9 | **No input validation on webhook payload** beyond HMAC — no schema validation for price ranges, symbol format | `api/webhook.py` | MEDIUM |
| S10 | **CORS allows `localhost:5173` and `localhost:3000`** in all modes including live | `api/main.py:116` | LOW |

### 5.4 POSITIVE SECURITY

- ✅ **RestrictedUnpickler** in `safe_pickle.py` — blocks deserialization RCE
- ✅ **Fail-closed defaults** — corrupted kill switch state → ACTIVE (block all)
- ✅ **Fail-closed circuit breaker** — corrupted state → all classes tripped
- ✅ **Rate limiting** — Redis-backed sliding window with in-memory fallback
- ✅ **Atomic file writes** — `tempfile + os.replace` pattern in kill switch, circuit breaker, OMS ledger
- ✅ **Golden Rules** — hardcoded, validated at startup, cannot be overridden
- ✅ **RiskPolicy is frozen dataclass** — immutable at runtime
- ✅ **HMAC-SHA256 webhook authentication**
- ✅ **Correlation ID middleware** — distributed tracing
- ✅ **Idempotency guards** — duplicate order prevention

---

## 6. Design Issues & Recommendations

### 6.1 CRITICAL

#### Issue C1: Dual Order Dataclasses
**Problem**: Two `Order` classes exist with incompatible types:
- `execution/order.py`: Uses `Decimal`, has `OrderStateMachine`, full validation
- `execution/adapters/base.py`: Uses `float`, simpler, used by OMS

**Impact**: Type confusion, potential precision loss, state machine not applied to broker orders.

**Recommendation**: Merge into a single canonical `Order` class. Use `execution/order.py` as the source of truth, have adapters accept/return it.

#### Issue C2: OMS State Machine Duplication
**Problem**: OMS creates its own `OrderStateMachine` (line 367: `OrderStateMachine(order_id=order.order_id, initial=OrderStatus.SIGNAL_CREATED)`) while `execution/order.py` has a different `OrderStateMachine(order: Order)` that takes the full Order object.

**Impact**: Two different state machine implementations with potentially different transition rules.

**Recommendation**: Unify to one `OrderStateMachine` implementation.

### 6.2 HIGH

#### Issue H1: Import-Time Side Effects
**Problem**: `api/main.py` line 33 imports `from graxia.packages.revenue_os.db import get_db as _get_db` — this is a cross-package import that fails if `revenue_os` isn't installed.

**Impact**: API server won't start without `revenue_os` package.

**Recommendation**: Remove cross-package dependency or make it conditional.

#### Issue H2: Config RiskPolicy Reconstruction
**Problem**: `core/config.py` creates new `RiskPolicy` instances 6 times in `_validate_from_env()` and 4 times in `_enforce_hard_limits()`, each time copying all fields manually.

**Impact**: Error-prone, hard to maintain, easy to miss a field.

**Recommendation**: Use `dataclasses.replace()` for immutable updates.

#### Issue H3: EventBus Synchronous by Default
**Problem**: `EventBus.publish()` is synchronous. Handlers that need async (like broker calls) block the event loop.

**Impact**: Slow handlers block all other handlers and the trading loop.

**Recommendation**: Use `publish_async()` for production, or make the bus async-first.

### 6.3 MEDIUM

#### Issue M1: No Circular Dependencies Detected
✅ The dependency graph is clean — no circular imports found.

#### Issue M2: Global Singletons
**Problem**: Multiple global singletons (`_config`, `_backend`, `_rate_limiter`) make testing harder.

**Recommendation**: Use dependency injection consistently.

#### Issue M3: Hardcoded Symbol Mappings
**Problem**: Symbol-to-asset-class mappings duplicated in `trading_loop.py`, `oms.py`, and `kill_switch.py`.

**Recommendation**: Centralize in `core/symbol_registry.py` (which exists but isn't used everywhere).

---

## 7. Test Coverage Analysis

### 7.1 Test File Count by Module

| Module | Test Files | Coverage Assessment |
|--------|-----------|-------------------|
| `tests/` (top-level) | 150+ files | Comprehensive |
| `tests/unit/` | 3 files | **UNDERSERVED** — only position_sizer, risk_engine, signal_gateway |
| `tests/integration/` | 1 file (database) | **UNDERSERVED** |
| `canary/test_*.py` | 12 files | Good |
| `shadow/test_*.py` | 15+ files | Good |
| `validation/test_*.py` | 10 files | Good |

### 7.2 Tested vs Untested

**Well-Tested:**
- ✅ Risk engine (4-layer validation)
- ✅ Kill switch (persistence, Telegram commands)
- ✅ Circuit breaker (trip, cooldown, state persistence)
- ✅ Order state machine (transitions)
- ✅ Ensemble signal generation
- ✅ Shadow pipeline (full lifecycle)
- ✅ Canary demo flow
- ✅ Walk-forward validation
- ✅ Overfitting detection
- ✅ Event bus (pub/sub)
- ✅ Golden rules validation

**Undertested or Untested:**
- ❌ `execution/oms.py` — No dedicated test file (tested indirectly via integration tests)
- ❌ `execution/adapters/mt5.py` — Mocked in tests, real integration untested
- ❌ `core/orchestrator.py` — No direct unit tests
- ❌ `core/trading_loop.py` — Only `test_trading_loop.py` (1 file)
- ❌ `core/position_manager.py` — No dedicated test file
- ❌ `api/main.py` — Only `test_api_endpoints.py` and `test_api_routes.py`
- ❌ `api/signal_service.py` — No dedicated test file
- ❌ `market_data/` — Only `test_market_data.py` (1 file for 13 modules)
- ❌ `monitoring/` — Only `test_monitoring.py` and `test_monitoring_infra.py`
- ❌ `broker/mt5_gateway.py` — Only `test_mt5_gateway.py`
- ❌ `core/agents/` — Only `test_agents_c1.py`
- ❌ `config/` — No dedicated config tests

### 7.3 Test Anti-Patterns

1. **Phase-numbered tests** (test_phase_3_1_*.py, test_phase_5_*.py) — 40+ files tied to specific phases. These should be consolidated into module-level tests.
2. **Diagnostic scripts** in tests/ (diagnostic_mrb.py, diagnostic_mtm.py) — should be in scripts/ or a separate diagnostic directory.
3. **run_*.py in tests/** (run_all_13_strategies_real.py, run_holdout_and_deflated.py) — these are scripts, not tests.

---

## 8. Critical Path Analysis (Live Trading)

### 8.1 Critical Path Components (Must Work)

```
Signal Generation → Risk Check → Order Submission → Fill → Position Tracking → Reconciliation
```

| Step | Component | Failure Mode | Mitigation |
|------|-----------|-------------|------------|
| 1 | Strategy signal | Wrong signal | Ensemble voting, confidence threshold |
| 2 | RiskEngine.evaluate() | Missed risk | 4-layer fail-closed design |
| 3 | OMS.submit_order() | Duplicate order | Idempotency via signal_id |
| 4 | MT5Adapter.submit_order() | Broker failure | Retry (3x), timeout, failover |
| 5 | Fill handling | Partial fill | 30s poll timeout, ledger persistence |
| 6 | Position tracking | Position drift | Parquet persistence, reconciliation |
| 7 | Kill switch | Stuck active | Fail-closed, Telegram override, coordinator |

### 8.2 Single Points of Failure

1. **MT5 connection** — Single broker adapter, no real failover (PaperAdapter is fallback but doesn't trade)
2. **JSONL ledger** — Single file, no replication (atomic writes help but no backup)
3. **EventBus** — In-process only, no cross-process pub/sub
4. **State files** (kill_switch, circuit_breaker) — Local filesystem only

### 8.3 Live Trading Readiness Checklist

- [x] Risk engine with 4 layers
- [x] Kill switch with persistence
- [x] Circuit breaker with cooldown
- [x] Order idempotency
- [x] Position reconciliation
- [x] Golden rules validation
- [x] Rate limiting
- [x] HMAC webhook auth
- [x] Structured logging
- [x] Correlation IDs
- [ ] **JWT authentication on API routes** (missing)
- [ ] **Admin route protection** (missing)
- [ ] **Unified Order dataclass** (dual classes)
- [ ] **MT5 adapter integration tests** (mocked only)
- [ ] **Cross-process EventBus** (in-process only)

---

## 9. Recommendations Summary

### Priority 1 (Before Live Trading)
1. **Unify Order dataclasses** — Single canonical Order class
2. **Add API authentication** — JWT or API key middleware on all routes
3. **Remove revenue_os dependency** from webhook.py
4. **Add OMS unit tests** — Critical path, currently untested directly

### Priority 2 (Hardening)
5. **Consolidate phase tests** into module-level tests
6. **Add MT5 integration tests** (with Docker MT5 or mock server)
7. **Centralize symbol mappings** in symbol_registry.py
8. **Use dataclasses.replace()** for RiskPolicy updates

### Priority 3 (Enhancement)
9. **Make EventBus async-first** for production
10. **Add distributed tracing** (OpenTelemetry)
11. **Add circuit breaker for MT5 connection** (not just trading)
12. **Move diagnostic scripts** out of tests/

---

*Generated by Architect Agent — 2026-07-06*
