# 🚀 Pattern Integration Mega Plan — Graxia Quant OS

> **Version**: 1.0 DRAFT
> **Date**: 2026-06-26
> **Status**: Awaiting approval
> **Owner**: bridge agent (Ruflow/Project Gracia)
> **Scope**: Integrate 5 proven patterns from external repos into Graxia quant_os without adding runtime dependencies
> **Predecessor**: [`integration_plan.md`](./integration_plan.md) (high-level)
> **Related**: [`repo_audit_report.md`](./repo_audit_report.md), [`../graxia_mega_plan_v3.md`](../graxia_mega_plan_v3.md)

---

## 1. EXECUTIVE SUMMARY

This mega plan operationalizes the high-level [`integration_plan.md`](./integration_plan.md). It defines the exact work breakdown, acceptance criteria, day-by-day execution schedule, testing strategy, risk register, rollback procedures, and quality gates required to integrate five external patterns into Graxia quant_os:

1. **jesse-ai/jesse** — Strategy API ergonomics
2. **kvrancic/algorithmic-trading-bot** — Kelly + VaR risk analytics
3. **cyclux/tradeforce** — Numba/Arrow performance
4. **tauricresearch/tradingagents** — Multi-agent ensemble pipeline
5. **letianzj/quanttrader** — Event-driven decoupling

**Core constraint**: all patterns are copied as *ideas*, not dependencies. Graxia keeps its own source tree, license cleanliness, and deterministic runtime.

**Timeline**: 7 weeks (49 calendar days)
**Effort estimate**: ~340 engineering hours
**Critical path**: A1 → A3 → B1 → C4 → D2 (event-driven backtest refactor)

---

## 2. CONTEXT & CURRENT STATE

### 2.1 Graxia Architecture Baseline

```
Market Data → Strategy.generate_signal() → Signal
                                              ↓
RiskEngine.check_order() ← OrderRequest ← OrderManager
       ↓
  Approve / Reject
       ↓
Broker / BacktestExecutionSimulator
       ↓
Portfolio State + Equity Curve
```

**Strengths**:
- `Signal` dataclass carries rich metadata (confidence, regime, indicator_values).
- `RiskEngine` runs 17 explicit pre-trade checks with kill switch and circuit breaker.
- `BacktestEngine` has lookahead guards, MTF cursor, realistic fill model.
- `OrderManager` is idempotent and supports human approval.
- Configuration is typed, frozen, and env-overridable.

**Gaps**:
- Strategy authoring is verbose (no `should_long` / `go_long` helpers).
- No Kelly Criterion, VaR, or correlation-based position sizing.
- Backtest hot path is pure Python.
- No event bus; components call each other directly.
- Ensemble strategies use weighted averages, not agent debate.
- Hyperparameter search exists but is not ergonomic for strategy authors.

### 2.2 External Pattern Inventory

| Repo | License | Key Files Reviewed | Pattern to Adopt |
|------|---------|-------------------|------------------|
| jesse-ai/jesse | MIT | `strategies/Strategy.py`, `helpers.py` | Entry/exit helper API, hyperparameter metadata, trade-closed callback |
| kvrancic/algorithmic-trading-bot | MIT | `risk_management/`, `position_sizing/` | Kelly sizing, VaR, ensemble model weighting |
| cyclux/tradeforce | MIT | `tradeforce/backend/`, `config/` | Numba JIT hot paths, Arrow persistence, Optuna search harness |
| tauricresearch/tradingagents | MIT | `src/agents/`, `main.py` | Deterministic agent roles (analyst, bull/bear, risk auditor, portfolio manager) |
| letianzj/quanttrader | MIT | `quanttrader/event.py`, `portfolio.py` | Event types, event bus, bar-driven loop |

---

## 3. STRATEGIC OBJECTIVES

### 3.1 Primary Objectives

| ID | Objective | Measurement |
|----|-----------|-------------|
| O1 | Strategy authoring cycle time ↓ 30% | Time to implement a new simple MA-cross strategy from scratch |
| O2 | Backtest throughput ↑ 2× on 100k+ bar datasets | Benchmark: XAUUSD M15 5 years (~125k bars) |
| O3 | Risk engine supports Kelly + VaR checks | Unit tests + integration tests pass |
| O4 | Backtest engine uses event-driven decoupling | All tests pass; latency regression <5% |
| O5 | Ensemble strategy uses agent pipeline | At least 3 deterministic agent roles participate in signal generation |

### 3.2 Non-Objectives (Explicitly Out of Scope)

- Adding the 5 repos as git submodules or PyPI dependencies.
- Live LLM usage in agents (Graxia stays deterministic).
- GUI for live trading (Graxia uses Telegram/API).
- Real-time streaming architecture changes beyond event bus.
- Changes to broker adapter interfaces.
- Changes to `CONSTITUTION.md` invariants.

---

## 4. SCOPE & BOUNDARIES

### 4.1 In Scope

| Module | Changes |
|--------|---------|
| `strategies/base.py` | Helper methods, hyperparameter metadata, callbacks |
| `strategies/ensemble.py` | Refactor to agent pipeline |
| `risk/position_sizer.py` | Kelly sizing method |
| `risk/engine.py` | VaR check, correlation check |
| `risk/pre_trade_risk.py` | Trailing drawdown stop |
| `backtest/engine.py` | Event bus integration, Numba hot path, batch mode |
| `backtest/data_loader.py` | Arrow format support |
| `core/events.py` | Event dataclasses |
| `core/event_bus.py` | In-process event bus |
| `core/hyperopt.py` | Optuna integration improvements |
| `core/agents/` | New agent framework (4 agents) |
| `tests/` | New tests for every change |
| `docs/` | Architecture decision records (ADRs) |

### 4.2 Out of Scope

| Module | Reason |
|--------|--------|
| `broker/` adapters | No interface change |
| `live_readiness/` | No change to readiness gates |
| `shadow/` | No change to shadow trading |
| `market_data/` ingestion | Arrow is a loader format, not ingestion change |
| `api/main.py` | No API endpoint changes |

---

## 5. ARCHITECTURE BLUEPRINT (Target State)

### 5.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Data Layer                              │
│  CSV/Parquet/Arrow → DataLoader → BarEvent                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ BarEvent
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Event Bus (core/event_bus.py)              │
│   In-process pub/sub; typed event queue; no external broker     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│   Strategy   │  │  Risk Agent  │  │ Portfolio Agent  │
│  (enhanced)  │  │   (kvrancic) │  │  (kvrancic/jesse)│
└──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
       │                 │                   │
       ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────┐
│              SignalEvent → OrderEvent               │
│   RiskEngine.pre_trade_checks + Kelly/VaR          │
│   OrderManager.human_approval + broker dispatch     │
└─────────────────────────────────────────────────────┘
```

### 5.2 Data Flow by Pattern

**Pattern 1 (jesse)**: `Strategy.should_long()` → returns bool → `Strategy.generate_signal()` wraps into `Signal`.

**Pattern 2 (kvrancic)**: `PositionSizer.kelly_fraction()` → used by `RiskEngine` to modify max position size.

**Pattern 3 (tradeforce)**: `BacktestEngine._simulate_bars_numba()` → replaces pure-Python loop for compatible strategies.

**Pattern 4 (tradingagents)**: `EnsembleStrategy` runs `TechnicalAnalyst` → `BullBearResearcher` → `RiskAuditorAgent` → `PortfolioManagerAgent`.

**Pattern 5 (quanttrader)**: `EventBus` routes `BarEvent` → subscribers; `BacktestEngine` becomes a subscriber, not a caller.

---

## 6. DETAILED IMPLEMENTATION ROADMAP

### 6.1 Phase A — Foundation (Week 1–2)

**Goal**: introduce additive, low-risk changes; establish event vocabulary.

**Phase A Acceptance Gate**:
- All existing tests pass.
- New unit tests for A1, A2, A3 pass.
- No breaking changes to `Strategy` ABC.

#### Week 1

**Day 1–2: A1 — Strategy Helper Methods (jesse)**
- File: `strategies/base.py`
- Tasks:
  - Add `should_enter(self, side: OrderSide, data: OHLCV) -> bool` with default `return False`.
  - Add `should_exit(self, position: Position, data: OHLCV) -> bool` with default `return False`.
  - Add `on_trade_closed(self, trade: TradeResult) -> None` callback stub.
  - Add `hyperparameters(self) -> Dict[str, HyperparameterRange]` default empty dict.
  - Add convenience properties: `self.price`, `self.balance`, `self.position`, `self.available_margin`.
  - Update `generate_signal()` default implementation to consult `should_enter` / `should_exit`.
- Acceptance Criteria:
  - `class TestStrategy(Strategy): def should_long(self): return True` produces a valid `Signal`.
  - Backward compatibility: existing `MTMStrategy` still passes tests without modification.
  - New unit tests: 10 cases covering helpers, callbacks, and defaults.
- Effort: 6 hrs

**Day 3–4: A2 — Kelly Criterion Sizing (kvrancic)**
- File: `risk/position_sizer.py` (new or existing)
- Tasks:
  - Implement `kelly_fraction(win_rate: float, avg_win: float, avg_loss: float, fraction: float = 0.25) -> float`.
  - Implement `kelly_position_size(equity, kelly_fraction, price, stop_price, max_risk_pct) -> Decimal`.
  - Add historical trade statistics tracker: `TradeStatsTracker`.
  - Guardrails: never return > `MAX_KELLY_FRACTION` (default 0.25 of Kelly).
- Acceptance Criteria:
  - Kelly formula mathematically correct (unit test with known inputs).
  - Position size bounded by `max_risk_pct`.
  - Zero-division safe.
- Effort: 8 hrs

**Day 5: A3 — Event Types (quanttrader)**
- File: `core/events.py` (new)
- Tasks:
  - Define `Event` base class with `timestamp`, `event_id`, `source`.
  - Define `BarEvent`, `SignalEvent`, `OrderEvent`, `FillEvent`, `TradeClosedEvent`, `RiskEvent`.
  - Implement `to_dict()` / `from_dict()` for serialization.
  - Add validation using existing Pydantic/dataclass patterns.
- Acceptance Criteria:
  - All event types are frozen/immutable.
  - Round-trip dict serialization passes.
  - 100% branch coverage on event validation.
- Effort: 5 hrs

#### Week 2

**Day 6–8: A4 — In-Process Event Bus (quanttrader)**
- File: `core/event_bus.py` (new)
- Tasks:
  - Implement `EventBus` with `subscribe(event_type, handler)`, `publish(event)`, `unsubscribe`.
  - Support synchronous and async handlers.
  - Add error handling: handler exceptions do not crash the bus.
  - Add metrics: events published/handled per second.
- Acceptance Criteria:
  - Publish/subscribe round-trip <1 µs for 1k events.
  - Exceptions in one handler do not affect others.
  - Async handlers run in event loop without blocking.
- Effort: 10 hrs

**Day 9–10: A5 — Integration Tests + ADRs**
- Files: `tests/unit/core/test_events.py`, `tests/unit/core/test_event_bus.py`, `tests/unit/strategies/test_strategy_helpers.py`, `tests/unit/risk/test_kelly_sizing.py`
- Tasks:
  - Write tests for all Week 1 work.
  - Write ADR-001: Event-driven architecture decision.
  - Write ADR-002: Kelly Criterion adoption.
- Acceptance Criteria:
  - `pytest graxia/packages/quant_os/tests/ --tb=short -q` passes.
  - New tests add ≥30 cases.
- Effort: 8 hrs

**Week 2 Checkpoint**: Run full test suite + performance baseline for XAUUSD 5-year backtest.

---

### 6.2 Phase B — Core Integration (Week 3–4)

**Goal**: wire risk checks and backtest performance improvements.

**Phase B Acceptance Gate**:
- Kelly/VaR checks active in `RiskEngine`.
- Backtest hot path shows measurable speedup on benchmark.
- Event bus used in at least one production path.

#### Week 3

**Day 11–13: B1 — Event Bus in Backtest Engine (quanttrader)**
- File: `backtest/engine.py`
- Tasks:
  - Refactor `BacktestEngine.run()` to publish `BarEvent` for each bar.
  - Strategy subscribes to `BarEvent` and publishes `SignalEvent`.
  - `BacktestExecutionSimulator` subscribes to `OrderEvent` and publishes `FillEvent`.
  - Maintain lookahead guard: event bus must not allow future data access.
  - Keep existing public API (`run()`, `results`) unchanged.
- Acceptance Criteria:
  - Existing backtest tests produce identical P&L before/after refactor.
  - Latency regression <5% vs baseline.
  - Lookahead guard still triggers on cheating strategy.
- Effort: 14 hrs

**Day 14–15: B2 — VaR Risk Check (kvrancic)**
- File: `risk/engine.py`
- Tasks:
  - Implement `var_95(returns: np.ndarray) -> float`.
  - Add `check_var_exposure(order, portfolio, config) -> RiskCheckResult`.
  - Add `check_correlation_exposure(order, portfolio, config)` using pairwise returns correlation.
  - Add VaR parameters to `RiskConfig`.
- Acceptance Criteria:
  - VaR check rejects order when 1-day 95% VaR > `max_var_pct` of equity.
  - Correlation check rejects when adding order increases portfolio concentration beyond threshold.
  - Unit tests cover edge cases (short history, all-zero returns).
- Effort: 10 hrs

#### Week 4

**Day 16–17: B3 — Numba Hot Path (tradeforce)**
- File: `backtest/engine.py`
- Tasks:
  - Identify hot loop: indicator precomputation and P&L aggregation.
  - Implement `_simulate_bars_numba()` fallback for strategies that expose a Numba-compatible signal function.
  - Add `Strategy.supports_numba()` flag, default `False`.
  - Provide graceful fallback to pure Python.
- Acceptance Criteria:
  - Benchmark: XAUUSD M15 5-year backtest ≥2× faster when Numba path active.
  - Pure-Python path unchanged and still default.
  - Numerical results match within `1e-9`.
- Effort: 12 hrs

**Day 18–19: B4 — Hyperparameter Helpers + Optuna (jesse/tradeforce)**
- Files: `strategies/base.py`, `core/hyperopt.py`
- Tasks:
  - Use `hyperparameters()` metadata to generate Optuna search space automatically.
  - Add `Strategy.from_hyperparameters(params)` classmethod.
  - Update `core/hyperopt.py` to use new helpers.
- Acceptance Criteria:
  - A strategy with `hyperparameters()` can be optimized without boilerplate.
  - Existing hyperopt tests pass.
- Effort: 8 hrs

**Day 20: B5 — Phase B Validation**
- Tasks:
  - Run full test suite.
  - Run benchmark suite (with/without Numba).
  - Write ADR-003: Event-driven backtest engine.
  - Write ADR-004: Numba performance path.
- Effort: 6 hrs

---

### 6.3 Phase C — Advanced Integration (Week 5–6)

**Goal**: introduce multi-agent ensemble and Arrow loader.

**Phase C Acceptance Gate**:
- Ensemble strategy uses ≥3 agents.
- Arrow loader supports backtest datasets.
- All advanced features are optional and backward compatible.

#### Week 5

**Day 21–23: C1 — Agent Framework (tradingagents)**
- Files: `core/agents/base.py`, `core/agents/analyst.py`, `core/agents/researcher.py`, `core/agents/risk_auditor.py`, `core/agents/portfolio_manager.py`
- Tasks:
  - Define `Agent` ABC with `observe(event)`, `act() -> Optional[Event]`.
  - Implement deterministic rule-based agents:
    - `TechnicalAnalystAgent`: reads indicators, emits `AnalystOpinion`.
    - `BullBearResearcherAgent`: combines bullish/bearish evidence, emits `ResearchConsensus`.
    - `RiskAuditorAgent`: checks position-level risk, emits `RiskOpinion`.
    - `PortfolioManagerAgent`: final signal assembly, emits `SignalEvent`.
  - Agents communicate only via EventBus.
- Acceptance Criteria:
  - Each agent has isolated unit tests.
  - Agents can be composed into a pipeline.
  - No LLM or external API calls.
- Effort: 18 hrs

**Day 24–25: C2 — Arrow Data Loader (tradeforce)**
- File: `backtest/data_loader.py`
- Tasks:
  - Add `load_arrow(path) -> pd.DataFrame`.
  - Convert to internal `OHLCV` format.
  - Add schema validation (columns, dtypes, sorted index).
  - Add `to_arrow(df, path)` export utility.
- Acceptance Criteria:
  - Arrow load ≥2× faster than CSV for same dataset.
  - Schema validation rejects malformed files with clear error.
  - Round-trip CSV → Arrow → DataFrame preserves values.
- Effort: 10 hrs

#### Week 6

**Day 26–28: C3 — Ensemble Strategy Refactor (tradingagents)**
- File: `strategies/ensemble.py`
- Tasks:
  - Refactor `EnsembleStrategy` to use agent pipeline.
  - Support weighted voting, consensus threshold, and veto rules.
  - Add metadata: `agent_votes`, `consensus_score`, `dissenting_views`.
  - Maintain existing `generate_signal()` interface.
- Acceptance Criteria:
  - Ensemble produces `Signal` with agent metadata.
  - Unit tests cover unanimous, split, and veto scenarios.
  - Backward compatible with existing ensemble config.
- Effort: 14 hrs

**Day 29–30: C4 — Batch Backtest Mode (tradeforce)**
- File: `backtest/engine.py`
- Tasks:
  - Add `run_batch(configs)` to run multiple backtests efficiently.
  - Share precomputed indicators across batch items.
  - Emit batch results with aggregate statistics.
- Acceptance Criteria:
  - Batch mode uses shared cache correctly.
  - Results match individual runs.
  - Memory usage does not grow unbounded.
- Effort: 10 hrs

**Day 31–32: C5 — Phase C Validation**
- Tasks:
  - Full test suite.
  - Agent pipeline integration tests.
  - Arrow loader benchmark.
  - Write ADR-005: Multi-agent ensemble.
  - Write ADR-006: Arrow data format.
- Effort: 8 hrs

---

### 6.4 Phase D — Validation & Hardening (Week 7)

**Goal**: prove correctness, performance, and stability.

**Phase D Acceptance Gate**:
- All tests pass.
- Performance targets met.
- Documentation complete.
- Rollback runbook validated.

#### Week 7

**Day 33–35: D1 — Comprehensive Test Campaign**
- Tasks:
  - Unit tests: ≥95% coverage on new modules.
  - Integration tests: end-to-end backtest with all 5 patterns active.
  - Regression tests: compare P&L against pre-integration baseline.
  - Property-based tests: Kelly sizing invariants, event bus ordering.
- Acceptance Criteria:
  - `pytest graxia/packages/quant_os/tests/ --tb=short -q` passes.
  - New code coverage ≥90%.
- Effort: 16 hrs

**Day 36–37: D2 — Performance Benchmarking**
- Tasks:
  - Benchmark 1: XAUUSD M15 5-year backtest (Numba on/off).
  - Benchmark 2: Arrow vs CSV load time.
  - Benchmark 3: Event bus throughput.
  - Benchmark 4: Agent pipeline latency per bar.
  - Document results in `artifacts/benchmarks/`.
- Acceptance Criteria:
  - ≥2× backtest speedup with Numba path.
  - ≥2× data load speedup with Arrow.
  - Event bus <1 µs per publish.
- Effort: 10 hrs

**Day 38–39: D3 — Documentation & Runbook**
- Tasks:
  - Update `README.md` with new strategy authoring examples.
  - Write migration guide for existing strategies.
  - Write operations runbook: how to enable/disable Numba, agents, Arrow.
  - Write rollback runbook.
- Effort: 8 hrs

**Day 40–41: D4 — Final Review & Sign-off**
- Tasks:
  - Run release gate: `python scripts/run_release_gate.py`.
  - Security review: no secrets, no unauthorized deps.
  - License audit: no GPL contamination.
  - Code review checklist.
- Effort: 8 hrs

**Day 42: D5 — Go/No-Go Decision**
- Deliverable: `Meta/states/integration_signoff.md`
- Criteria:
  - All acceptance gates passed.
  - Stakeholder approval.
  - Rollback plan rehearsed.

---

## 7. TESTING & VALIDATION STRATEGY

### 7.1 Test Pyramid

| Layer | Coverage Target | Tools | Examples |
|-------|-----------------|-------|----------|
| Unit | ≥95% new code | pytest | `test_kelly_sizing.py`, `test_event_bus.py` |
| Integration | All new paths | pytest | `test_event_driven_backtest.py` |
| Regression | Existing suite | pytest | `test_phase_10_micro_live.py` |
| Performance | Benchmark suite | pytest-benchmark | `test_backtest_numba_speedup.py` |
| Property | Invariants | hypothesis | `test_event_bus_ordering.py` |

### 7.2 Key Test Scenarios

1. **Backward Compatibility**: every existing strategy runs unchanged.
2. **Determinism**: same seed → same P&L.
3. **Event Ordering**: handlers receive events in publish order.
4. **Fault Isolation**: bad handler does not crash others.
5. **Kelly Bounds**: position size never exceeds max risk.
6. **VaR Rejection**: order rejected when VaR limit breached.
7. **Numba Equivalence**: Numba path P&L == Python path P&L.
8. **Agent Veto**: risk auditor can veto bullish consensus.

### 7.3 Regression Baseline

Before Phase A begins, capture:
- `pytest` duration and pass count.
- Backtest P&L for `MTMStrategy` on XAUUSD M15 1-year sample.
- Memory peak during backtest.

After each phase, re-run and diff. Any regression >5% triggers investigation.

---

## 8. DOCUMENTATION PLAN

| Document | Location | Owner | Phase |
|----------|----------|-------|-------|
| ADR-001: Event-driven architecture | `docs/adr/001-event-driven.md` | bridge | A |
| ADR-002: Kelly Criterion adoption | `docs/adr/002-kelly-criterion.md` | bridge | A |
| ADR-003: Event-driven backtest engine | `docs/adr/003-backtest-events.md` | bridge | B |
| ADR-004: Numba performance path | `docs/adr/004-numba-performance.md` | bridge | B |
| ADR-005: Multi-agent ensemble | `docs/adr/005-multi-agent.md` | bridge | C |
| ADR-006: Arrow data format | `docs/adr/006-arrow-format.md` | bridge | C |
| Migration guide | `docs/migration/integration-v1.md` | bridge | D |
| Operations runbook | `docs/runbooks/pattern-features.md` | bridge | D |
| Benchmark report | `artifacts/benchmarks/integration_v1/` | bridge | D |

---

## 9. RISK REGISTER

| ID | Risk | Probability | Impact | Mitigation | Owner |
|----|------|-------------|--------|------------|-------|
| R1 | Breaking existing strategies | Medium | High | Additive-only changes; comprehensive regression tests; feature flags | bridge |
| R2 | Numba path produces different results | Low | High | Numerical equivalence tests; default off until validated | bridge |
| R3 | Event bus adds latency | Medium | Medium | Benchmark; keep synchronous path available; optional feature | bridge |
| R4 | Agent pipeline too slow | Medium | Medium | Deterministic rule-based agents; pipeline depth configurable | bridge |
| R5 | Dependency bloat (pyarrow, numba) | Low | Medium | Optional imports; graceful degradation; license audit | bridge |
| R6 | VaR/Kelly misuse | Medium | High | Bounded fractions; guardrails; extensive unit tests; ADR | bridge |
| R7 | Scope creep | High | Medium | Explicit non-objectives; phase gates; sign-off required | bridge |
| R8 | Knowledge loss if bridge agent interrupted | Medium | Medium | State saved in `Meta/states/` after every phase | bridge |
| R9 | Existing tests false-pass after refactor | Low | High | Property-based tests; mutation testing on event bus | bridge |

---

## 10. ROLLBACK & RECOVERY PLAN

### 10.1 Rollback Triggers

- Regression in existing test suite.
- Backtest P&L drift >0.1% vs baseline.
- Performance degradation >10% on default path.
- Security or license issue.
- Stakeholder rejects phase gate.

### 10.2 Rollback Levels

| Level | Scope | Procedure | Time to Recover |
|-------|-------|-----------|-----------------|
| L1 | Feature flag | Set `NUMBA_ENABLED=false`, `AGENTS_ENABLED=false`, `EVENT_BUS_ENABLED=false` in config | Instant |
| L2 | Module revert | `git revert <commit>` for single phase | 1–2 hrs |
| L3 | Full rollback | Reset to pre-integration tag `pre-pattern-integration` | 2–4 hrs |

### 10.3 Pre-Integration Baseline

Before starting Phase A:
```bash
git tag pre-pattern-integration
git push origin pre-pattern-integration
python scripts/run_release_gate.py
# Save output to Meta/states/integration_baseline.json
```

---

## 11. PERFORMANCE BUDGETS

| Metric | Baseline | Target | Ceiling |
|--------|----------|--------|---------|
| Backtest: 125k bars XAUUSD M15 | ~TBD after baseline | ≤50% of baseline | ≤75% of baseline |
| Data load: 125k rows CSV | ~TBD | Arrow ≤50% of CSV | Arrow ≤75% of CSV |
| Event bus publish latency | N/A | <1 µs | <5 µs |
| Agent pipeline latency/bar | N/A | <100 µs | <500 µs |
| Memory peak backtest | ~TBD | ≤+20% | ≤+50% |
| Test suite runtime | ~TBD | ≤+25% | ≤+50% |

> Baseline values will be filled during Week 2 checkpoint.

---

## 12. MIGRATION STRATEGY

### 12.1 Existing Strategies

No mandatory migration. Existing strategies continue to work because `generate_signal()` remains the primary API.

Optional migration checklist:
- [ ] Implement `should_long()` / `should_short()` for clarity.
- [ ] Add `hyperparameters()` for Optuna.
- [ ] Implement `on_trade_closed()` for adaptive logic.
- [ ] Opt into Numba if signal function is compatible.

### 12.2 Existing Risk Config

Add optional fields:
```python
@dataclass(frozen=True)
class RiskConfig:
    # existing fields...
    max_var_pct: float = 0.02
    max_kelly_fraction: float = 0.25
    correlation_threshold: float = 0.8
```

Default values preserve existing behavior.

### 12.3 Existing Backtest Code

Public API unchanged:
```python
engine = BacktestEngine(config)
results = engine.run()   # same as before
```

Internal event-driven refactor is transparent.

---

## 13. QUALITY GATES

### 13.1 Per-Phase Gates

| Phase | Gate Criteria | Evidence Required |
|-------|---------------|-------------------|
| A | All existing tests pass; new unit tests pass; ADRs written | Test report, ADR files |
| B | Backtest event refactor produces identical P&L; Numba path ≥2× faster; risk checks pass | Benchmark report, diff report |
| C | Agent pipeline produces signals; Arrow loader works; ensemble backward compatible | Integration test report |
| D | Full suite passes; coverage ≥90%; docs complete; release gate passes | Sign-off document |

### 13.2 Hard Stops

Stop and escalate if:
- Any existing test fails without a documented exception.
- VaR/Kelly check produces a position size >2× current default.
- Event bus introduces nondeterminism in backtest results.
- License audit finds GPL or incompatible code.

---

## 14. RESOURCE REQUIREMENTS

### 14.1 Engineering Effort

| Phase | Hours | Notes |
|-------|-------|-------|
| A | ~37 | Foundation |
| B | ~50 | Core integration |
| C | ~60 | Advanced |
| D | ~42 | Validation |
| Buffer (20%) | ~38 | Contingency |
| **Total** | **~227** | |

### 14.2 Compute

- Development machine: existing.
- Benchmark machine: same as development (documented).
- CI: existing GitHub Actions / local runner sufficient.

### 14.3 Dependencies

| Dependency | Purpose | Optional? | Added When |
|------------|---------|-----------|------------|
| `numba` | JIT hot path | Yes | Phase B |
| `pyarrow` | Arrow loader | Yes | Phase C |
| `optuna` | Already present | No | — |

---

## 15. SUCCESS METRICS

### 15.1 Technical KPIs

| KPI | Target | Measurement |
|-----|--------|-------------|
| Backtest speedup | ≥2× | Benchmark suite |
| Test coverage (new code) | ≥90% | pytest-cov |
| Regression test pass rate | 100% | pytest |
| Documentation completeness | 100% | Checklist |

### 15.2 Business KPIs

| KPI | Target | Measurement |
|-----|--------|-------------|
| Strategy authoring time | ↓30% | Time-to-implement simple MA strategy |
| Risk check granularity | +3 new checks | VaR, Kelly, correlation |
| System extensibility | New agent in <2 hrs | Timed exercise |

---

## 16. COMMUNICATION PLAN

| Event | Audience | Channel | Timing |
|-------|----------|---------|--------|
| Plan approval | User | This document | Start |
| Phase gate complete | User | Summary message | End of each phase |
| Blocker / risk | User | Immediate alert | As needed |
| Final sign-off | User | `integration_signoff.md` | End |
| State save | System | `Meta/states/*.md` | After each session |

---

## 17. APPENDICES

### Appendix A: Pattern Specification Sheets

#### A.1 jesse Pattern

| Aspect | Detail |
|--------|--------|
| Source | `jesse-ai/jesse`, MIT |
| Adopted | `should_long`, `should_short`, `go_long`, `go_short`, `on_trade_closed`, `hyperparameters` |
| Rejected | `self.buy = qty, price` syntax (Graxia uses `Signal`) |
| Files | `strategies/base.py`, `core/hyperopt.py` |

#### A.2 kvrancic Pattern

| Aspect | Detail |
|--------|--------|
| Source | `kvrancic/algorithmic-trading-bot`, MIT |
| Adopted | Kelly Criterion sizing, VaR, correlation risk |
| Rejected | Black-box ensemble model weighting (we use explicit agent pipeline) |
| Files | `risk/position_sizer.py`, `risk/engine.py`, `risk/pre_trade_risk.py` |

#### A.3 tradeforce Pattern

| Aspect | Detail |
|--------|--------|
| Source | `cyclux/tradeforce`, MIT |
| Adopted | Numba JIT, Arrow format, batch mode, Optuna harness |
| Rejected | Docker-first deployment, market server architecture |
| Files | `backtest/engine.py`, `backtest/data_loader.py`, `core/hyperopt.py` |

#### A.4 tradingagents Pattern

| Aspect | Detail |
|--------|--------|
| Source | `tauricresearch/tradingagents`, MIT |
| Adopted | Role-based agent pipeline: analyst → researcher → risk auditor → portfolio manager |
| Rejected | LLM-based reasoning, LangGraph dependency |
| Files | `core/agents/`, `strategies/ensemble.py` |

#### A.5 quanttrader Pattern

| Aspect | Detail |
|--------|--------|
| Source | `letianzj/quanttrader`, MIT |
| Adopted | Event types, event bus, bar-driven loop |
| Rejected | GUI, Interactive Brokers-specific live engine |
| Files | `core/events.py`, `core/event_bus.py`, `backtest/engine.py`, `execution/manager.py` |

### Appendix B: Proposed API Additions

```python
# strategies/base.py
class Strategy(ABC):
    # existing ...

    def should_long(self, data: OHLCV) -> bool:
        return False

    def should_short(self, data: OHLCV) -> bool:
        return False

    def on_trade_closed(self, trade: TradeResult) -> None:
        pass

    def hyperparameters(self) -> Dict[str, HyperparameterRange]:
        return {}

    def supports_numba(self) -> bool:
        return False

# risk/position_sizer.py
class PositionSizer:
    @staticmethod
    def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float,
                       fraction: float = 0.25) -> float: ...

# core/events.py
@dataclass(frozen=True)
class BarEvent(Event):
    timestamp: datetime
    symbol: str
    ohlcv: OHLCV

# core/event_bus.py
class EventBus:
    def subscribe(self, event_type: Type[Event], handler: Callable): ...
    def publish(self, event: Event): ...
```

### Appendix C: Test Cases Catalog

| ID | Module | Test Name | Purpose |
|----|--------|-----------|---------|
| TC-A1-01 | strategies | `test_should_long_generates_signal` | Helper method works |
| TC-A1-02 | strategies | `test_existing_strategy_untouched` | Backward compatibility |
| TC-A2-01 | risk | `test_kelly_known_values` | Math correctness |
| TC-A2-02 | risk | `test_kelly_bounds_max_risk` | Safety guard |
| TC-A3-01 | core | `test_event_immutability` | Frozen events |
| TC-A4-01 | core | `test_handler_isolation` | Fault tolerance |
| TC-B1-01 | backtest | `test_event_engine_parity` | Identical P&L |
| TC-B2-01 | risk | `test_var_rejects_over_limit` | Risk gate |
| TC-B3-01 | backtest | `test_numba_speedup` | Performance |
| TC-C1-01 | agents | `test_agent_pipeline_veto` | Agent authority |
| TC-C2-01 | backtest | `test_arrow_load_faster` | Data performance |
| TC-C3-01 | strategies | `test_ensemble_consensus` | Ensemble logic |
| TC-D1-01 | integration | `test_end_to_end_all_patterns` | Full system |

### Appendix D: Dependency & License Audit

| Dependency | License | Use | Compatibility |
|------------|---------|-----|---------------|
| numba | BSD 2-Clause | JIT | ✅ Compatible |
| pyarrow | Apache-2.0 | Arrow loader | ✅ Compatible |
| optuna | MIT | Hyperopt | ✅ Already used |

All copied patterns are MIT-licensed and will be reimplemented; no code is copied verbatim.

### Appendix E: Definition of Done

For this mega plan to be considered complete:

- [ ] All 4 phases executed and signed off.
- [ ] All acceptance criteria met.
- [ ] All ADRs written and reviewed.
- [ ] All documentation updated.
- [ ] Baseline and benchmark reports saved in `artifacts/benchmarks/`.
- [ ] Rollback runbook rehearsed.
- [ ] `Meta/states/integration_signoff.md` created and approved.

---

## 18. NEXT ACTION

Approve this mega plan, then begin **Phase A — Foundation**.

The first concrete task is **A1**: add `should_long` / `should_short` / `hyperparameters` / `on_trade_closed` to `strategies/base.py`.
