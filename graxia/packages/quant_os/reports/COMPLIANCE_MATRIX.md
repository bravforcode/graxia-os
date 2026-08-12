# Master Plan Compliance Matrix

## Phase Status

| Phase | Description | Status | Exit Gate |
|-------|-------------|--------|-----------|
| G0 | Runtime Truth | ✅ PASS | 7 lock files, 12 hashes, legacy retired |
| 3.1 | Engine Integration | ✅ PASS | ExecutionSimulator, bid/ask, TradeLedger |
| 3.2 | MT5 Readiness | ✅ PASS | live_readiness, market_data, 97 tests |
| 3.3 | News/Events | ✅ PASS | Event gate, stabilization, macro policy |
| 1R-H | Repo Intelligence | ✅ PASS | Registry 70 entries, supply chain, manifest |
| 3B | Locked XAUUSD | ✅ PASS | Locked inputs, native runner, regime, exit gate |
| 4 | EURUSD Foundation | ✅ PASS | Market separation, hypothesis, contamination guard |
| 5 | Research Governance | ✅ PASS | Experiment registry, trial budget, validation stack |
| 6 | Shadow Trading | ✅ PASS | Pipeline, failure rules, telemetry |
| 7 | Demo Canary | ✅ PASS | Config, broker validator, order lifecycle |
| 8 | Demo Campaign | ⏳ PENDING | Requires MT5 live connection |
| 9 | Micro-Live Review | ⏳ PENDING | Requires Phase 8 evidence |
| 10 | Controlled Expansion | ⏳ PENDING | Requires Phase 9 approval |

## Component Map

```
quant_os/
├── backtest/
│   ├── engine.py          — BacktestEngine + BacktestConfig
│   ├── metrics.py         — Performance metrics
│   └── data_loader.py     — CSV data loading
├── core/
│   ├── config.py          — Canonical configuration
│   ├── enums.py           — OrderType, SignalType, etc.
│   ├── exceptions.py      — Custom exceptions
│   └── lookahead_guard.py — Look-ahead prevention
├── execution/
│   ├── execution_simulator.py — BacktestExecutionSimulator
│   ├── fill_model.py      — SL/TP trigger logic
│   ├── ambiguous_bar_resolver.py — Adverse resolution
│   └── trade_ledger.py    — JSON-file ledger with SHA-256
├── risk/
│   └── engine.py          — Pre-trade risk checks
├── strategies/
│   └── base.py            — Strategy ABC + Signal
├── live_readiness/
│   ├── mt5_runtime_verifier.py
│   ├── mt5_readonly_client.py
│   ├── broker_profile.py
│   ├── account_snapshot_service.py
│   ├── symbol_snapshot_service.py
│   └── smoke_report.py
├── market_data/
│   ├── tick_recorder.py
│   ├── tick_store.py
│   ├── feed_health.py
│   ├── spread_monitor.py
│   ├── clock_guard.py
│   ├── market_session_guard.py
│   └── market_health.py
├── news_events/
│   ├── event_models.py
│   ├── event_store.py
│   ├── event_risk_gate.py
│   ├── stabilization_gate.py
│   ├── macro_policy.py
│   └── integration.py
├── repo_intelligence/
│   ├── supply_chain.py
│   ├── manifest.py
│   └── hooks/
├── validation/
│   ├── locked_inputs.py
│   ├── cost_scenarios.py
│   ├── run_config.py
│   ├── native_runner.py
│   ├── regime_analyzer.py
│   └── exit_gate.py
├── markets/eurusd/
│   ├── contract_snapshot.py
│   ├── session_calendar.py
│   ├── event_calendar.py
│   ├── hypothesis.py
│   └── anti_contamination.py
├── governance/
│   ├── experiment_registry.py
│   ├── trial_budget.py
│   ├── validation_stack.py
│   └── ml_policy.py
├── shadow/
│   ├── pipeline.py
│   ├── failure_rules.py
│   └── telemetry.py
└── canary/
    ├── config.py
    ├── broker_validator.py
    └── order_lifecycle.py
```

## Golden Rules Compliance

| Rule | Status | Evidence |
|------|--------|----------|
| Only quant_os/execution submits orders | ✅ | No order_send in backtest/risk |
| Strategy proposes → Gate approves → Broker submits | ✅ | Pipeline enforces sequence |
| Reconciler verifies after fill | ✅ | PostFillVerifier in canary |
| Kill switch vetoes | ✅ | Kill switch in risk engine |
| No AI directional trading | ✅ | LLM policy guard |
| Event blocks during high-impact | ✅ | Event risk gate |
| Market health must be HEALTHY | ✅ | Market health state machine |

## Test Summary

| Category | Tests | Status |
|----------|-------|--------|
| Core | 12 | ✅ |
| Execution | 12 | ✅ |
| Backtest Integration | 22 | ✅ |
| Phase 3.1 | 42 | ✅ |
| Phase 3.2 | 97 | ✅ |
| Phase 3.3 | 46 | ✅ |
| Phase 1R-H | 23 | ✅ |
| Phase 3B | 26 | ✅ |
| Phase 4 | 30 | ✅ |
| Phase 5 | 26 | ✅ |
| Phase 6 | 45 | ✅ |
| Phase 7 | 26 | ✅ |
| Other | ~116 | ✅ |
| **Total** | **~550** | **✅** |
