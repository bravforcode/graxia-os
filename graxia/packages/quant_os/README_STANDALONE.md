# Quant OS

> Quantitative Trading Operating System — backtest, ML pipeline, live trading, risk management, all in one Python framework.

## Overview

Quant OS is a modular Python framework for algorithmic trading research, backtesting, and live execution. Built with production-grade risk controls, statistical validation, and a phase-based development methodology.

**Status:** 2,920+ tests passing · Version 0.2.0-dev

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  FastAPI Server (REST + WebSocket)                  │
├─────────────────────────────────────────────────────┤
│  Core Domain                                        │
│  ┌──────────┬──────────┬──────────┬──────────┐      │
│  │ Config   │ Enums    │ ML       │ Regime   │      │
│  │          │          │ Pipeline │ Filter   │      │
│  ├──────────┼──────────┼──────────┼──────────┤      │
│  │ Execution│ Risk     │ Backtest │ Strategy │      │
│  │ Engine   │ Manager  │ Engine   │ Engine   │      │
│  └──────────┴──────────┴──────────┴──────────┘      │
├─────────────────────────────────────────────────────┤
│  Infrastructure                                     │
│  ┌──────────┬──────────┬──────────┬──────────┐      │
│  │ MT5      │ Shadow   │ Canary   │ Monitor  │      │
│  │ Broker   │ Mode     │ System   │ Stack    │      │
│  └──────────┴──────────┴──────────┴──────────┘      │
├─────────────────────────────────────────────────────┤
│  Storage: DuckDB + PostgreSQL + Redis               │
└─────────────────────────────────────────────────────┘
```

## Key Features

### Backtest Engine
- **Deterministic** — MT5-independent, reproducible results
- **Multi-timeframe** — 1min, 5min, 15min, 1H, 4H, Daily
- **Real-cost simulation** — spread, slippage, commission modeling
- **Triple-barrier labeling** — for ML target generation

### ML Pipeline
- **Feature engineering** — 50+ technical indicators
- **XGBoost / scikit-learn** — model training and inference
- **Regime filter** — market condition detection
- **Walk-forward optimization** — out-of-sample validation
- **Deflated Sharpe** — multiple-testing correction

### Risk Management
- **Pre-trade risk gate** — mandatory before any order
- **Position sizing** — Kelly, fixed-fraction, volatility-target
- **Circuit breaker** — automatic trading halt on drawdown
- **Kill switch** — persists across restarts
- **Frozen risk policy** — immutable dataclass, no runtime mutation

### Live Trading
- **MetaTrader 5** — full broker integration
- **Shadow mode** — parallel dry-run before live
- **Canary system** — drill types for resilience testing
- **Paper trading** — simulated execution with real data

### Statistical Validation
- **Walk-forward analysis** — expanding/rolling window
- **Bootstrap** — confidence intervals for Sharpe/returns
- **Deflated Sharpe** — accounts for multiple testing
- **Probability of Backtest Overfitting (PBO)**

## Quick Start

```bash
# Clone
git clone https://github.com/bravforcode/quant-os.git
cd quant-os

# Setup
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1
pip install -e ".[all]"

# Run tests
make test

# Run backtest
python run_backtest.py

# Start API server
make api
```

## Module Structure

```
quant_os/
├── core/           Config, enums, ML pipeline, regime filter
├── execution/      Order management, fill model, cost model, broker adapter
├── risk/           Pre-trade risk, position sizing, circuit breaker
├── api/            FastAPI surface and runtime endpoints
├── backtest/       Backtesting engine (MT5-independent)
├── ml/             Model training, feature engineering, inference
├── validation/     Statistical validation (bootstrap, WFO, deflated Sharpe)
├── monitoring/     Observability, health checks, telemetry
├── strategies/     Strategy implementations
├── shadow/         Parallel dry-run mode
├── canary/         Resilience testing
├── broker/         Broker adapters
├── market_data/    Data ingestion and management
├── docker/         Container definitions
├── tests/          2,920+ tests
└── scripts/        Operational scripts
```

## Commands

| Target | Command |
|--------|---------|
| `make test` | Run full test suite |
| `make test-chaos` | Run chaos test suite |
| `make lint` | Run ruff linter |
| `make format` | Auto-format code |
| `make typecheck` | Run mypy type checker |
| `make coverage` | Run with coverage report |
| `make api` | Start the FastAPI server |
| `make release` | Run the release gate |

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI, Pydantic
- **Data:** pandas, numpy, DuckDB
- **ML:** scikit-learn, XGBoost
- **Database:** PostgreSQL, Redis
- **Broker:** MetaTrader 5
- **Validation:** scipy, statsmodels
- **Testing:** pytest, pytest-asyncio, pytest-cov

## Safety Constitution

Quant OS enforces strict invariants:

- Never claim guaranteed profit or zero loss
- Never present backtest results as live-trading evidence
- Risk policy is frozen dataclass, no runtime mutation
- All loss limits in basis points, never percentage floats
- Pre-trade risk gate mandatory before any order
- Every dataset has manifest with SHA-256 checksum

## License

Proprietary — Graxia OS
