# Phase 3.3: Cross-Phase Integration — Complete Pipeline & Strategy Layer

## Context

The `news_events/` module currently has core infrastructure (event models, store, risk gate, stabilization gate, integration, macro policy) but lacks the data pipeline, strategy integration, and execution hook that would make it operational. Phase 3.3 ties these pieces together so the event risk gate actually blocks/orders in the execution pipeline.

## Existing Code Analysis

**What exists in `news_events/`:**
- `event_models.py:21-26` — `GateState` enum (CLEAR, PRE_EVENT_BLOCK, EVENT_BLOCK, POST_EVENT_STABILIZATION, UNKNOWN)
- `event_store.py:5-43` — `EventStore` in-memory point-in-time store with `add_event()` and `query_at()`
- `event_risk_gate.py:15-66` — `EventRiskGate.evaluate()` blocks HIGH importance events in pre/post windows
- `stabilization_gate.py:7-76` — `StabilizationGate.is_stabilized()` checks feed health, spread, elapsed time
- `integration.py:8-64` — `NewsEventIntegration.can_submit_order()` chains risk→stabilization gates
- `macro_policy.py:27-96` — `MacroPolicyGuard` + `LLMPolicyGuard` for data policy enforcement

**What exists in execution/risk:**
- `execution/manager.py:23-414` — `OrderManager.submit_order()` runs: kill switch → create → idempotency → validate → risk → compliance → broker
- `risk/engine.py:66-318` — `RiskEngine.check_order()` runs 13 checks but has **no event gate check**
- `strategies/base.py:109-223` — `Strategy` ABC with `generate_signal()`, `required_features()`, `is_valid_for_regime()`

**Key gap:** The `RiskEngine` in `risk/engine.py` has no `_check_news_event_gate` in its check list. The event gate exists but is never called during order submission.

## Implementation Plan

### 1. Add news event gate check to RiskEngine (`risk/engine.py`)

**File:** `C:\Users\menum\graxia os\graxia\packages\quant_os\risk\engine.py`

- Add optional `news_event_integration` parameter to `RiskEngine.__init__()` (line ~73)
- Add `_check_news_event_gate` method that calls `news_event_integration.can_submit_order()`
- Insert it into the `checks` list in `check_order()` (line ~97) after `_check_circuit_breaker` and before `_check_mode`
- Map `GateResult.state != CLEAR` → `RiskCheckResult.fail_check("NEWS_EVENT_GATE", ...)`

This is the critical integration point — it hooks the existing event gate into the existing risk engine without changing the OrderManager.

### 2. Create data pipeline (`news_events/pipeline.py`)

**New file:** `C:\Users\menum\graxia os\graxia\packages\quant_os\news_events\pipeline.py`

Contains:
- `EventIngestor` — abstract base class with `fetch_events()` method
- `HTTPPollingIngestor` — concrete implementation that polls an HTTP endpoint (e.g., ForexFactory, Investing.com API) and returns raw event dicts
- `EventNormalizer` — converts raw dicts into `EconomicEvent` instances, handling field mapping, timezone normalization, importance mapping
- `EventPersistence` — save/load events to JSON files for backtest replay and audit trail
- `NewsEventPipeline` — orchestrator that chains: ingest → normalize → store → log. Provides `run_cycle()` for live polling and `load_historical()` for backtest seeding.

### 3. Create strategy integration (`news_events/strategy.py`)

**New file:** `C:\Users\menum\graxia os\graxia\packages\quant_os\news_events\strategy.py`

Contains:
- `SignalGenerator` — wraps any base `Strategy` and adds event gate awareness. Before generating a signal, checks `NewsEventIntegration.get_gate_state()`. If BLOCKED, returns `None` (no signal). If CLEAR, delegates to wrapped strategy.
- `NewsEventStrategy` — extends `Strategy` ABC. Composes multiple sub-strategies (like Ensemble) but gates all signals through the event integration. Implements `generate_signal()`, `required_features()`, `is_valid_for_regime()`.

### 4. Update `news_events/__init__.py`

Add exports for `NewsEventPipeline`, `SignalGenerator`, `NewsEventStrategy`, `EventIngestor`, `HTTPPollingIngestor`, `EventNormalizer`, `EventPersistence`.

### 5. Add deployment readiness (`news_events/monitoring.py`)

**New file:** `C:\Users\menum\graxia os\graxia\packages\quant_os\news_events\monitoring.py`

Contains:
- `EventGateMetrics` — counters/histograms for gate checks (total, blocked, cleared, by reason)
- `EventPipelineHealth` — health check for the data pipeline (last successful fetch age, error rate)
- `event_gate_prometheus_metrics()` — returns Prometheus-compatible metric definitions

## Files to Create/Modify

| File | Action |
|------|--------|
| `risk/engine.py` | Modify — add `_check_news_event_gate` check |
| `news_events/pipeline.py` | Create — data pipeline (ingest, normalize, persist, orchestrate) |
| `news_events/strategy.py` | Create — strategy wrapper with event gate |
| `news_events/monitoring.py` | Create — metrics and health checks |
| `news_events/__init__.py` | Modify — add new exports |

## Verification

1. **Import check:** `python -c "from news_events import NewsEventPipeline, SignalGenerator, NewsEventStrategy"`
2. **Unit test:** Create `tests/test_news_event_integration.py` that:
   - Creates an `EventStore`, adds HIGH importance events
   - Verifies `NewsEventIntegration.can_submit_order()` returns BLOCKED during event window
   - Verifies `RiskEngine._check_news_event_gate()` returns fail when gate is BLOCKED
   - Verifies `SignalGenerator.generate_signal()` returns None when gate is BLOCKED
3. **Lint/typecheck:** Run project linter to verify no regressions
