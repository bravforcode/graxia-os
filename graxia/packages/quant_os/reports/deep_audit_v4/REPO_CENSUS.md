# REPO CENSUS
**Phase 0.1–0.9 | 2026-07-05**

---

## 0.1 — File & Directory Tree Summary
- **Total Python files:** ~400+ (estimated from tree walk)
- **Major directories:** `core/`, `execution/`, `risk/`, `strategies/`, `backtest/`, `validation/`, `data/`, `scripts/`, `tests/`, `reports/`
- **Large files (>500 lines):** `backtest/engine.py` (1391 lines), `execution/broker_adapter.py` (604 lines), `execution/adapters/mt5.py` (444 lines), `strategies/ensemble.py` (508 lines), `scripts/walk_forward.py` (420 lines)
- **Data files:** 135+ CSV files across 15 instruments × 9 timeframes, plus FRED macro data, yfinance data, COT reports

## 0.2 — Dependency Inventory
- `MetaTrader5` — MT5 Python API (version unpinned in requirements.txt)
- `pandas`, `numpy` — data manipulation
- `xgboost` — ML model (walk-forward)
- `scikit-learn` — ML utilities
- `structlog` — structured logging
- `numba` — JIT indicator calculation (optional)
- `pandas_ta` — technical indicators
- `duckdb` — data storage
- `chromadb` — vector store
- `fastapi` — API surface

## 0.3 — Entry Points

| Purpose | Command | File |
|---|---|---|
| Live trading | `python core/orchestrator.py` | `core/orchestrator.py` |
| Paper trading | `python run_paper_trading.py` | `run_paper_trading.py` |
| Backtest | `python scripts/walk_forward.py --symbol XAUUSD` | `scripts/walk_forward.py` |
| API server | `python api/main.py` | `api/main.py` |
| TSM paper trade | `python scripts/tsm_paper_trade.py` | `scripts/tsm_paper_trade.py` |

## 0.4 — Configuration

| Parameter | Value | Where Defined | Hardcoded/Config |
|---|---|---|---|
| Symbols traded | 15 (EURUSD..XPTUSD) | `data/` directory | Config-driven |
| Timeframes | M1, M5, M15, M30, H1, H4, D1, W1, MN1 | `data/` directory | Config-driven |
| Initial capital | $10,000 | `backtest/engine.py:157` | Config default |
| Spread pips | 2.0 | `backtest/engine.py:159` | Config default |
| Commission/lot | $3.50 | `backtest/engine.py:160` | Config default |
| Risk/trade | 10 bps | `backtest/engine.py:161` | Config default |
| Max positions | 5 | `backtest/engine.py:162` | Config default |
| Ensemble weights | MTM=40%, MRB=25%, MLB=35% | `strategies/ensemble.py:443-447` | **Hardcoded** |
| Walk-forward spread cost | 0.024 | `scripts/walk_forward.py:388` | CLI arg |
| Walk-forward slippage P90 | 0.02 | `scripts/walk_forward.py:389` | CLI arg |

## 0.5 — Data Files on Disk
- **15 instruments × 9 timeframes = 135 CSV files** in `data/`
- **FRED macro data:** 39 series in `data/fred/daily/`
- **yfinance data:** 29 tickers in `data/market_data/yfinance/`
- **COT data:** 3 files in `data/market_data/cot/`
- **ForexFactory calendar:** `data/news/forexfactory_calendar.json` — **PRESENT** ✅
- **Economic calendar:** `data/news/economic_calendar_4weeks.json` — **PRESENT** ✅

## 0.6 — Test Coverage
- **Test files:** 201 files in `tests/` directory
- **Coverage areas:** Core, execution, risk, strategies, backtest, integration, chaos, monitoring
- **Notable gaps:** No property-based tests for numerical components; label-shuffling test uses synthetic data only

## 0.7 — Compute & Runtime Environment
- **OS:** Windows (win32)
- **Python:** 3.11.14
- **MT5:** Pepperstone terminal (per config)

## 0.8 — Process & Scheduling
- `run_paper_trading.ps1` — PowerShell script for paper trading
- `scripts/setup_scheduler.ps1` — Windows Task Scheduler setup
- `scripts/fix_scheduled_tasks.py` — scheduler maintenance
- No systemd/Docker production deployment confirmed for live trading

## 0.9 — Dependency Supply Chain
- `MetaTrader5` package from PyPI — version match with Pepperstone terminal not verified
- No `pip-audit` scan found
- **Status:** `[NO VULNERABILITY SCAN RUN]`
