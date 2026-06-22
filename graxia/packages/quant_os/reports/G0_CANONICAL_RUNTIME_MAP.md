# G0.1 Canonical Runtime Map — Quant OS

**Generated:** 2026-06-22  
**Rule:** Each responsibility has EXACTLY ONE canonical module. Non-canonical modules get a status label.

---

## Canonical Responsibility → Module Mapping

| # | Responsibility | Canonical Module | Notes |
|---|---|---|---|
| 1 | MTF slicing | `backtest/mtf_cursor.py` | MultiTimeframeCursor, point-in-time slicing |
| 2 | Dataset validation | `data/manifests/` + `data/pipeline.py` | Manifests define shape, pipeline handles ingestion |
| 3 | Symbol/contract lookup | `broker/mt5_gateway.py` + `broker/contract_spec.py` | MT5 gateway fetches live specs, ContractSpec is immutable |
| 4 | Risk policy | `risk/risk_policy.py` | Soft limits: per-trade, daily, weekly, drawdown |
| 5 | Position sizing | `risk/position_sizer_v2.py` | Decoupled ContractSpec + RiskPolicy, no direct imports |
| 6 | Pre-trade checks | `risk/pre_trade_risk.py` | Checks sizing_result against ledger and kill_switch |
| 7 | Backtest execution | `backtest/engine.py` | MTF cursor integration, signal execution, equity tracking |
| 8 | Cost model | `execution/cost_model.py` | Spread, commission, slippage scenario calculation |
| 9 | Fill model | `execution/fill_model.py` | Entry/exit fill simulation with SL/TP trigger checks |
| 10 | Trade ledger | `execution/trade_ledger.py` | JSON-file records with provenance and hash integrity |
| 11 | Order state machine | `execution/order_state_machine.py` | 16 states, enforced transitions, no MT5 dependency |
| 12 | Conservative bar model | `execution/conservative_bar_model.py` | Bar high/low → synthetic bid/ask |
| 13 | Kill switch | `risk/kill_switch.py` | Persistent JSON-file, blocks all new orders |
| 14 | Risk ledger | `risk/risk_ledger.py` | Daily/weekly risk tracking, JSON-file reset |
| 15 | External repo registry | `repo_intelligence/registry/` | YAML registry, quarantine decisions |
| 16 | Contract snapshot store | `broker/contract_snapshot_store.py` | Immutable JSON with hash verification |
| 17 | Strategy definition | `strategies/base.py` | Signal dataclass + Strategy ABC |
| 18 | Data loading | `data/feed.py` | Live feed: MT5, Yahoo, fallback chain |
| 19 | Quality gate | `data/quality_gate.py` | Data validation before trading decisions |

---

## Scan Summary

| Metric | Count |
|---|---|
| **Total Python files scanned** | 118 |
| **ACTIVE** | 82 |
| **LEGACY_READ_ONLY** | 11 |
| **TEST_FIXTURE_ONLY** | 37 |
| **DEPRECATED_PENDING_DELETE** | 1 |
| **QUARANTINED** | 4 (directories/files) |

---

## ACTIVE Files (82)

### Core (`core/`)
- `config.py` — Configuration management, env override, hard limit enforcement
- `enums.py` — System enums (SystemState, TradingMode, OrderStatus, etc.)
- `exceptions.py` — Custom exception hierarchy
- `golden_rules.py` — Non-negotiable hardcoded constraints
- `bias_detector.py` — Recursive/lookahead bias detection
- `candle_pipeline.py` — Candle regeneration for Monte Carlo
- `dashboard.py` — Monitoring dashboard metrics
- `holdout_validation.py` — Final holdout + deflated Sharpe
- `hyperopt.py` — Hyperparameter optimization framework
- `lifecycle.py` — Strategy lifecycle hooks
- `lookahead_guard.py` — Zero look-ahead enforcement
- `ml_pipeline.py` — ML data gathering/training
- `monte_carlo.py` — Strategy robustness stress testing
- `multi_source_pipeline.py` — CCXT/CoinGecko/Yahoo/FRED aggregation
- `pair_filter.py` — Pipeline pair filtering
- `param_sweep.py` — Parameter sweep (vectorbt pattern)
- `regime_filter.py` — Market regime classification
- `rolling_metrics.py` — Rolling risk metrics
- `signal_filter.py` — Fake signal filtering (6 criteria)
- `stability.py` — Walk-forward stability metric
- `structured_trades.py` — Structured trade records

### Backtest (`backtest/`)
- `mtf_cursor.py` — **CANONICAL** MTF slicing
- `engine.py` — **CANONICAL** Backtest execution
- `data_loader.py` — CSV/MT5 data loading
- `metrics.py` — Performance metrics
- `walk_forward.py` — Walk-forward validation

### Broker (`broker/`)
- `mt5_gateway.py` — **CANONICAL** MT5 gateway
- `contract_spec.py` — **CANONICAL** ContractSpec
- `contract_snapshot_store.py` — **CANONICAL** Snapshot store

### Risk (`risk/`)
- `risk_policy.py` — **CANONICAL** Risk policy
- `position_sizer_v2.py` — **CANONICAL** Position sizing
- `pre_trade_risk.py` — **CANONICAL** Pre-trade checks
- `kill_switch.py` — **CANONICAL** Kill switch
- `risk_ledger.py` — **CANONICAL** Risk ledger
- `circuit_breaker.py` — Soft stop mechanism (auto-reset)
- `portfolio.py` — Portfolio exposure tracking

### Execution (`execution/`)
- `cost_model.py` — **CANONICAL** Cost model
- `fill_model.py` — **CANONICAL** Fill model
- `trade_ledger.py` — **CANONICAL** Trade ledger
- `order_state_machine.py` — **CANONICAL** Order state machine
- `conservative_bar_model.py` — **CANONICAL** Conservative bar model
- `manager.py` — Order lifecycle orchestration
- `broker_adapter.py` — Broker adapter layer
- `idempotency.py` — Duplicate order prevention
- `order.py` — Order entity class

### Strategies (`strategies/`)
- `base.py` — **CANONICAL** Strategy ABC
- `ensemble.py` — Ensemble vote system (MTM+MRB+MLB)
- `mlb.py` — ML-Enhanced Breakout
- `mrb.py` — Mean Reversion Bollinger
- `mtm.py` — Multi-Timeframe Momentum

### Gold Bot (`gold_bot/`)
- `run.py` — Main entry point (13 strategies)
- `run_demo.py` — Demo trading script
- `strategy_adapter.py` — Adapts gold_bot strategies to backtest engine
- `core/config.py` — Gold Bot config
- `core/engine.py` — Gold Bot core engine (13 strategies, Claude AI validation)
- `ai/validator.py` — Claude AI signal validator
- `monitoring/telegram_bot.py` — Telegram notifications
- 13 strategy files in `strategies/` — All ACTIVE (used in production)

### Data (`data/`)
- `feed.py` — **CANONICAL** Live data feed
- `pipeline.py` — **CANONICAL** Data pipeline
- `quality_gate.py` — **CANONICAL** Quality gate
- `models.py` — SQLAlchemy database models

### ML (`ml/`)
- `pipeline.py` — Feature engineering + model training

### Monitoring (`monitoring/`)
- `alerts.py` — Alert routing
- `metrics.py` — Trade metrics collection
- `telegram.py` — Telegram notifications

### API (`api/`)
- `main.py` — FastAPI app
- `admin.py` — Admin endpoints
- `orders.py` — Order management
- `positions.py` — Position management
- `risk.py` — Risk management endpoints
- `webhook.py` — TradingView webhook handler

### Repo Intelligence (`repo_intelligence/registry/`)
- `__init__.py`, 5 YAML files — **CANONICAL** registry

### Scripts/Root
- `tasks.py` — Celery background tasks
- `download_*.py` — Data download utilities
- `run_*.py` — Entry point scripts
- `pine_script/QuantBot_Ensemble.pine` — TradingView Pine Script

---

## LEGACY_READ_ONLY Files (11)

| File | Why Legacy |
|---|---|
| `risk/position_sizer.py` | Superseded by `position_sizer_v2.py`. Old sizer with hardcoded methods, imports from config/golden_rules. |
| `risk/engine.py` | 17-check risk engine superseded by `pre_trade_risk.py`. |
| `core/structured_trades.py` | Vectorbt-pattern trade storage, superseded by `execution/trade_ledger.py`. |
| `repo_intelligence/adapters/backtesting_py_oracle.py` | Stub, read-only reference. |
| `repo_intelligence/adapters/backtrader_oracle.py` | Stub, read-only reference. |
| `repo_intelligence/adapters/vectorbt_oracle.py` | Stub, read-only reference. |
| `repo_intelligence/adapters/lean_oracle_contract.py` | Stub, interface only. |
| `repo_intelligence/adapters/__init__.py` | Empty init for legacy adapters. |
| `repo_intelligence/__init__.py` | Empty init. |
| `repo_intelligence/manifests/repository_manifest.json` | Static manifest. |

---

## TEST_FIXTURE_ONLY Files (37)

- `conftest.py` — Pytest fixtures (config reset, mock Redis)
- `tests/test_core.py` through `tests/run_holdout_and_deflated.py` — 32 test/utility files
- `gold_bot/tests/` — 4 gold_bot test files
- `repo_intelligence/tests/` — 2 repo_intelligence test files

---

## DEPRECATED_PENDING_DELETE (1)

- `alembic_migration.py` — Migration stub, not connected to alembic versions

---

## QUARANTINED (4)

- `lancedb/__manifest/` — External LanceDB manifest
- `docs/SAFETY_CHECKLIST.md` — External reference
- `docs/freqtrade_patterns.md` — Freqtrade pattern reference
- `docs/jesse_patterns.md` — Jesse pattern reference
- `docs/vectorbt_patterns.md` — VectorBT pattern reference

---

## Ambiguities Found

### 1. `config.py` legacy sizing fields
`core/config.py` has `max_risk_per_trade_pct` and similar fields. These feed into `risk_policy.py` as config values. The old `position_sizer.py` imports from config; `position_sizer_v2.py` does not. Both are ACTIVE — config is the source of truth.

### 2. `execution/order.py` vs `order_state_machine.py`
`order.py` has an older Order class with inline state. `order_state_machine.py` is the canonical 16-state machine. `order.py` is still imported by `broker_adapter.py` and `manager.py`. Consider deprecating `order.py`'s inline state in a future pass.

### 3. `gold_bot/strategies/base.py` vs `strategies/base.py`
Gold Bot has its own `GoldStrategy` ABC. `strategies/base.py` is the canonical `Strategy` ABC. Both ACTIVE — different lineages, different consumers.

### 4. `data/feed.py` vs `backtest/data_loader.py`
`feed.py` is the live data feed (MT5/Yahoo/fallback). `data_loader.py` loads CSVs for backtests. Both ACTIVE — different contexts (live vs backtest).

### 5. `risk/engine.py` vs `risk/pre_trade_risk.py`
`engine.py` has 17 pre-trade checks (older). `pre_trade_risk.py` is the newer, simpler check. `pre_trade_risk.py` is canonical; `engine.py` is LEGACY_READ_ONLY.
