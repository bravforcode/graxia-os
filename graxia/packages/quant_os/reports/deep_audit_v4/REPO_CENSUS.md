# REPO_CENSUS.md -- Phase 0 Deep Audit (Tier 1)

## Sections 0.1-0.9

**Generated:** 2026-07-05 | **Version:** quant_os 0.2.0-dev

---

### 0.1 File Tree

Top-Level Structure: 22 directories, 500+ source files.
Key: alpha/, api/, backtest/, broker/, canary/, config/, core/, data/,
docker/, docs/, execution/, expansion/, gold_bot/, governance/, infra/,
live_readiness/, ml/, monitoring/, news_events/, oracle/, regime/,
reports/, research/, risk/, runtime/, scripts/, shadow/, strategies/,
tests/ (290 test files, 3,860 test functions), validation/.

Files over 500 lines for decomposition review:
  run_paper_trading.py: 803 lines (monolithic paper trader)
  gold_bot/run_paper.py: 834 lines (duplicate paper trader)
  execution/broker_adapter.py: 604 lines (deprecated, live-capable)
  execution/adapters/mt5.py: 522 lines (canonical MT5 adapter)
  strategies/ensemble.py: 534 lines (dynamic weighting)
  alpha/regime_detector.py: 535 lines (orphaned regime detector)
  docker-compose.yml: 450 lines (production orchestration)

### 0.2 Dependencies

Source: pyproject.toml (lines 10-25). ALL unpinned (>= not ==).

Core: pydantic>=2.0 (2.13.4), structlog>=23.0 (26.1.0), fastapi>=0.100 (0.133.1),
uvicorn>=0.23, pandas>=2.0 (2.3.3), numpy>=1.24 (2.4.6), duckdb>=0.10 (1.5.4),
sqlalchemy>=2.0 (2.0.51), redis>=5.0 (8.0.1), httpx>=0.25, websockets>=12.0,
python-dateutil>=2.8, tenacity>=8.0, orjson>=3.9.

Conditional: mt5: MetaTrader5>=5.0 (5.0.5735 installed, LIVE-capable),
yfinance>=0.2 (1.4.1), fred: fredapi>=0.5 (unverified),
ml: scikit-learn>=1.3 (**NOT INSTALLED**), xgboost>=2.0 (3.2.0),
arrow: pyarrow>=14.0 (unverified), charting: matplotlib>=3.7 (unverified).

Additional not in pyproject.toml: catboost (1.2.10), prometheus_client,
sentry_sdk.

CRITICAL: scikit-learn listed but not installed. ML pipeline would fail.
ALL deps use >= (unpinned). Risk of incompatible upstream releases.

### 0.3 Entry Points

LIVE TRADING (Paper mode, all hardcoded):
  start_bot.ps1:22 -> gold_bot/run_paper.py (duration 168, capital 49911.92)
  start_paper.bat:4 -> gold_bot/run_paper.py (duration 1)
  python gold_bot/run.py:22 -> GoldBotEngine (XAUUSD, BotConfig defaults)
  python gold_bot/run_paper.py:8 -> paper trading (13 strategies)
  python run_paper_trading.py:6 -> Liquidity Sweep pipeline (--duration, --symbols)
  python run_scheduled.py -> scheduler-based paper trading
  python api/main.py:268 -> FastAPI server (TRADING_MODE env var)
  docker-compose up -> multi-service deployment

BACKTEST/RESEARCH:
  python run_backtest.py -> Yahoo EURUSD backtest (MTM/MRB/MLB)
  python run_backtest_real.py -> real data backtest
  python run_ml_train.py -> XGBoost/CatBoost ML training
  scripts/tsm_ensemble_backtest.py -> ensemble backtest

MODE: NOT flag-based. Multiple separate entry points. TRADING_MODE env var
read by core/config.py:150 but individual scripts hardcode PAPER mode.

### 0.4 Configuration Inventory

PRIMARY SOURCES:
  QuantConfig dataclass: core/config.py:12-140
  Environment variables: .env / .env.example
  RiskPolicy frozen dataclass: risk/risk_policy.py
  paper_trade_config.json: config/paper_trade_config.json
  BotConfig: gold_bot/core/config.py
  PaperConfig: gold_bot/run_paper.py:41-79
  BacktestConfig: backtest/engine.py

KEY PARAMETER CONFLICTS (max_risk_per_trade_pct varies 4x):
  QuantConfig: 0.5, paper_trade_config.json: 1.0,
  gold_bot/run_paper.py: 0.25, run_paper_trading.py: 0.5

CRITICAL: max_drawdown_pct varies 2x (8.0 to 15.0).
CRITICAL: symbols vary completely across configs (8 forex vs 4-asset vs XAUUSD).

### 0.5 Data Files

M1 Data (1-minute): 90+ CSV files in data/ directory.
  Sufficient (100K rows): AUDUSD, EURUSD, GBPUSD, NAS100, US30, USDCAD,
    USDCHF, USDJPY, XAGUSD, XAUUSD.
  Insufficient: NZDUSD (5K), XPDUSD (5K), XPTUSD (5K), BTCUSD (7.8K), ETHUSD (7.8K).

  XAUUSD M1 starts 2026-05-14, EURUSD M1 starts 2026-05-18.
  ~100K rows = ~69 calendar days, ~7-10 weeks trading.

M15 Data: Sufficient for all major instruments (50-60K rows).

Other: COT parquet files (2024-2026), canonical XAUUSD_D1_clean.csv.
  ForexFactory economic calendar: NOT found on disk.
  news_events/ directory exists but has no data files.

### 0.6 Test Coverage

Summary: 290 test files, ~3,860 test functions, ~500+ test classes.

Coverage by area:
  Backtest engine: Excellent (10+ files)
  MT5 adapter: Good (chaos tests, edge cases)
  Risk limits: Good (kill switch, daily loss)
  Cost model: Good (swap, slippage, commission)
  ML pipeline: Good (training, drift)
  Shadow mode: Excellent (12 files)
  Gold bot: Good (7 test files)
  News blackout: Good (2 files)
  Data pipeline: Partial (no dedicated test)
  Docker integration: None
  Scheduler: Partial

Quarantine: quarantine_manifest.json exists with skipped tests.

### 0.7 Compute and Runtime

Declared: Python 3.11+, MT5 Latest, PostgreSQL 15+, Redis 7+.
OS: Primarily Windows (.ps1/.bat scripts, terminal64.exe paths).
Linux: gold_bot/mt5_adapter.py uses yfinance fallback (no MT5).

MT5 Path (hardcoded in 3 places):
  C:\\Program Files\\Pepperstone MetaTrader 5\\terminal64.exe
  (start_bot.ps1:9, core/config.py:33, run_paper_trading.py:168)

Docker: 5 services (api, signal, executor, trainer, mt5).
  MT5 container NOT IN USE (docker-compose.yml:284 note).
  Prometheus + Grafana + Alertmanager also deployed.

### 0.8 Process and Scheduling

Live loop:
  1. start_bot.ps1: Kills existing, launches MT5 with hardcoded creds,
     waits 60s, starts gold_bot/run_paper.py (cmd /c). PID saved to logs/.
  2. Asyncio loop: while self.is_running: trading_cycle(); sleep(10)
     (run_paper_trading.py:220-223). gold_bot uses 30s cycle.
  3. Docker: restart: unless-stopped, healthchecks (10-60s intervals).

Auto-restart/Watchdog:
  Docker: restart: unless-stopped provides auto-restart.
  NO OS-level watchdog (no systemd, supervisord, Windows Service).
  DMS monitors heartbeat staleness, can emergency-halt but does NOT restart.
  scripts/install_shadow_service.bat, scripts/install_services.bat exist
  but unverified.

### 0.9 Dependency Supply-Chain

Installed versions verified:
  MetaTrader5==5.0.5735 (closed-source, no CVE database)
  pandas==2.3.3, numpy==2.4.6, xgboost==3.2.0, catboost==1.2.10,
  scikit-learn: NOT INSTALLED (listed in pyproject.toml ml extras),
  fastapi==0.133.1, pydantic==2.13.4, sqlalchemy==2.0.51,
  duckdb==1.5.4, structlog==26.1.0, redis==8.0.1.

pip-audit: NOT installed. Cannot produce automated vulnerability report.

Security infrastructure exists:
  runtime/secret_scan.py, runtime/redaction.py,
  runtime/broker_identity_guard.py, repo_intelligence/supply_chain.py,
  repo_intelligence/hooks/pre_commit_security_check.py (order_send detection).

CRITICAL: Hardcoded MT5 credentials in start_bot.ps1:9.
CRITICAL: ALL dependencies use >= (unpinned). Supply-chain attack risk.

---

END OF REPO_CENSUS.md

See MODULE_WIRING_AND_CAPABILITY_AUDIT.md for sections 0.10-0.11.
See DOC_CODE_CONTRADICTION_AUDIT.md for sections 0.12-0.13.
