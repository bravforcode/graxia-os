# REPO_CENSUS.md — Phase 0 (0.1–0.9)

## 0.1 — File & Directory Tree

### Top-Level Structure
```
quant_os/
├── core/           Domain components (config, orchestrator, trading loop, ML pipeline, regime)
├── execution/      Order management, fill model, cost model, broker adapters
├── risk/           Pre-trade risk, position sizing, circuit breaker, kill switch
├── api/            FastAPI surface, webhook, Telegram, health endpoints
├── backtest/       Backtesting engine (class-based, MT5-independent), walk-forward
├── ml/             Model training, feature engineering, drift detection
├── validation/     Statistical validation (bootstrap, WFO, deflated Sharpe, PBO)
├── monitoring/     Observability, health checks, metrics, Telegram alerts
├── strategies/     Strategy implementations, walk-forward, base protocol
├── alpha/          Signal engine (strategy router, regime detector, SMC features)
├── shadow/         Shadow-mode parallel validation (read-only, no order_send)
├── canary/         Drill types, demo config, preflight checks
├── governance/     Validation stack, promotion review
├── broker/         MT5 read-only gateway, contract specs
├── data/           Data models, DuckDB, MT5 tick ingester
├── data_pipeline/  Prefect-based data orchestration
├── market_data/    Tick store, spread monitor, health
├── cost/           Cost model labeled, quote calibration
├── regime/         Regime detector, risk overlay, entry executor
├── scripts/        Utility scripts (walk-forward, training, diagnostics)
├── tests/          Test suite (~2920 tests)
├── gold_bot/       XAUUSD-specific bot (legacy, partially deprecated)
├── autonomous/     Autonomous engine, persistence, orchestrator
├── live_readiness/ MT5 read-only client for live validation
└── experiments/    Locked experiment outputs
```

### LOC by Language (estimated from file counts)
| Language | Files | Est. LOC | Notes |
|----------|-------|----------|-------|
| Python   | ~350+ | ~45,000+ | Core source |
| SQL      | ~5     | ~500     | Alembic migrations |
| YAML/TOML| ~10    | ~200     | Config |
| Markdown | ~30    | ~3,000   | Docs |

### Large Files (>500 lines)
- `backtest/engine.py` (~1500 lines) — requires decomposition review
- `gold_bot/run_paper.py` (~800 lines) — legacy, partially deprecated
- `gold_bot/run_multi.py` (~700 lines) — legacy
- `api/telegram_commands.py` (~550 lines) — command registry
- `scripts/tsm_paper_trade.py` (~1200 lines) — monolithic paper trading script

## 0.2 — Dependency Inventory

### Core Dependencies (pyproject.toml)
| Library | Version | Where Imported | Classification | Flags |
|---------|---------|----------------|----------------|-------|
| pydantic | >=2.0 | Throughout | Validation | — |
| structlog | >=23.0 | Throughout | Logging | — |
| fastapi | >=0.100 | api/main.py | API | — |
| uvicorn | >=0.23 | api/main.py | Server | — |
| pandas | >=2.0 | backtest/, ml/, scripts/ | Data | — |
| numpy | >=1.24 | backtest/, ml/, validation/ | Numerical | — |
| duckdb | >=0.10 | data/ | Storage | — |
| sqlalchemy | >=2.0 | data/models.py, api/ | ORM | — |
| redis | >=5.0 | core/config.py | Cache | — |
| httpx | >=0.25 | api/, data_pipeline/ | HTTP | — |
| tenacity | >=8.0 | api/, data_pipeline/ | Retry | — |

### Optional Dependencies
| Library | Version | Category | Where Used |
|---------|---------|----------|------------|
| MetaTrader5 | >=5.0 | Execution | execution/adapters/mt5.py |
| xgboost | >=2.0 | ML | ml/pipeline.py, scripts/ |
| scikit-learn | >=1.3 | ML | ml/pipeline.py, validation/ |
| numba | unpinned | JIT | backtest/engine.py (optional) |
| pandas_ta | unpinned | Indicators | backtest/, ml/ |

### Supply-Chain Concerns
- `MetaTrader5` is an optional dep — lazy-imported throughout. Version mismatch with broker terminal build can cause silent data issues.
- `numba` is optional — graceful fallback to pure Python/pandas_ta.
- No `pip-audit` scan has been run. **[NO SCAN RUN]**

## 0.3 — Entry Points

### Live Trading System
**Primary entry**: `api/main.py` → `create_app()` → FastAPI lifespan wires:
1. `TradingOrchestrator(config=config)` → starts EventBus + TradingLoop + OMS
2. `BrokerManager.from_config()` → MT5 connection
3. Telegram handlers wired to orchestrator

**Alternative live entry**: `run_paper_trading.py` → `PaperTrader` class (multi-asset TSM paper bot with heartbeat monitor, broker reconnector, dead man's switch)

**Start command**: `python api/main.py` (FastAPI) or `python run_paper_trading.py` (paper bot)

### Backtest/Research Pipeline
**Entry**: `run_backtest.py` → `backtest/run_backtest.py::run_backtest()` or `run_ml_train.py`

### Paper Trading
**Entry**: `scripts/tsm_paper_trade.py` (multi-asset TSM) or `launch_7day.py` (7-day background process)

### Mode Flag
`TRADING_MODE` env var → `core/config.py:154-155` → `TradingMode` enum (PAPER, LIVE_MICRO, LIVE_LIMITED, LIVE_CONTROLLED)

## 0.4 — Configuration Inventory

| Parameter | Value | Where Defined | Hardcoded? | Used In |
|-----------|-------|---------------|------------|---------|
| Symbols traded | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, XAUUSD | core/config.py:53 | Config-driven | alpha/engine.py |
| Primary timeframe | M15 | core/config.py:56 | Config-driven | strategies/ |
| Risk per trade | 10 bps (0.10%) | risk/risk_policy.py:14 | Hardcoded default | risk/position_sizer.py |
| Max drawdown | 300 bps (3.00%) | risk/risk_policy.py:14 | Hardcoded default | backtest/engine.py |
| Max daily loss | 300 bps (3.00%) | risk/risk_policy.py:14 | Hardcoded default | risk/pre_trade_risk.py |
| Hard stop drawdown | 15% | core/golden_rules.py:11 | **HARDCODED** | monitoring/ |
| Strategy weights | mtm:0.40, mrb:0.25, mlb:0.35 | core/config.py:70-75 | Config-driven | alpha/engine.py |
| Spread (backtest) | 2.0 pips | backtest/engine.py:205 | Config-driven | backtest/ |
| Commission | $3.5/lot | core/config.py:118 | Config-driven | backtest/ |
| Slippage | 0.5 pips | core/config.py:117 | Config-driven | backtest/ |
| Paper initial capital | $10,000 | core/config.py:116 | Config-driven | execution/ |
| Units per lot | 100,000 | core/config.py:122 | Config-driven | risk/position_sizer.py |

### Multi-Place Parameters (Cross-Reference)
- `commission_per_lot` appears in: `core/config.py:118` (3.5), `backtest/engine.py:206` (3.5), `execution/adapters/paper.py:98` (config), `scripts/backtest_cost_aware.py` (varies)
- `spread_pips` appears in: `backtest/engine.py:205` (2.0), `backtest/dynamic_spread_model.py` (session-aware)
- **Risk limits**: `risk/risk_policy.py` (canonical), `core/golden_rules.py` (hard limits), `core/config.py` (env overrides) — three sources of truth

## 0.5 — Data Files on Disk

| File | Format | Size | Date Range | Status |
|------|--------|------|------------|--------|
| data/EURUSD_D1.csv | CSV | ~500KB | 2020–2024 | PRESENT |
| data/XAUUSD_D1.csv | CSV | ~500KB | 2020–2024 | PRESENT |
| data/kill_switch_state.json | JSON | ~5KB | Active state | PRESENT |
| data/visual_index/quant_meta.json | JSON | ~1KB | Index | PRESENT |
| data/heartbeat.txt | Text | ~30B | Latest heartbeat | PRESENT |
| state/audit_log.jsonl | JSONL | Growing | Audit trail | PRESENT |

### Missing Data
- No ForexFactory economic calendar data on disk (referenced in code but not present)
- No multi-symbol M1/M5/M15 data visible at project root (likely in data/ subdirectories)
- Pickle files in `ml/models/` for trained models — regeneration required if stale

## 0.6 — Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| tests/test_core_modules.py | Core enums, config, exceptions, golden rules |
| tests/test_execution.py | Order creation, state machine, paper broker |
| tests/test_risk_engine.py | Risk engine, Monte Carlo, scaling gates |
| tests/test_risk_modules.py | Circuit breaker, position sizers |
| tests/test_strategies.py | Strategy signals, signal service |
| tests/test_stop_loss_and_price_sanity.py | Stop-loss validation, price sanity |
| tests/test_signal_validator.py | Signal validation, IC analysis |
| tests/test_phase_*.py | Phase-specific integration tests (~20 files) |
| tests/chaos/*.py | Chaos engineering tests |
| tests/test_e2e_*.py | End-to-end pipeline tests |

**Estimated coverage**: ~30-40% of core modules have direct tests. ML pipeline, data pipeline, and monitoring have minimal test coverage. **No property-based tests** for numerical components.

## 0.7 — Compute & Runtime Environment

- **OS**: Windows (win32)
- **Python**: >=3.11 (pyproject.toml)
- **MT5 Terminal**: Pepperstone MetaTrader 5 (`C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe`)
- **Host**: Local machine (not VPS/cloud — based on file paths `C:\Users\menum\`)
- **Timezone**: UTC throughout (all timestamps use `datetime.now(UTC)`)
- **DST**: Handled via UTC — no local timezone conversion issues

## 0.8 — Process & Scheduling

- **Live bot**: Started via `api/main.py` (FastAPI) or `run_paper_trading.py` (background)
- **Auto-restart**: `monitoring/health_check.py` has a watchdog loop that checks `data/heartbeat.txt` — restarts on stale heartbeat (30min threshold)
- **Dead Man's Switch**: `monitoring/dead_mans_switch.py` — triggers emergency close-all on heartbeat stall
- **Process limits**: No explicit memory/CPU limits found
- **Scheduling**: `launch_7day.py` runs as background process with PID file tracking

## 0.9 — Supply-Chain & Vulnerability

- **MetaTrader5 package**: Installed from PyPI, lazy-imported. Version not pinned in pyproject.toml (>=5.0). **[VERSION MATCH UNVERIFIED]**
- **No pip-audit run**: No vulnerability scan has been performed against the dependency tree.
- **Safe pickle**: `core/safe_pickle.py` restricts numpy allowlist to prevent deserialization attacks.

---

*Next: See MODULE_WIRING_AND_CAPABILITY_AUDIT.md for Phase 0.10–0.11*
