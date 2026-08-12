# quant_os — Quantitative Trading Operating System

[![quant_os CI](https://github.com/bravforcode/graxia-os/actions/workflows/quant_os.yml/badge.svg?branch=main)](https://github.com/bravforcode/graxia-os/actions/workflows/quant_os.yml)

A modular Python framework for algorithmic trading research, backtesting, and live execution.

> **Security note:** never commit `.env` files or credentials to the repository. `*.duckdb`, `data/ticks/`, and `.env` are already ignored.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -e graxia/packages/quant_os/

# Run tests
make test
```

## Structure

```
core/           Core domain components (config, enums, ML pipeline, regime filter)
execution/      Order management, fill model, cost model, broker adapter
risk/           Pre-trade risk, position sizing, circuit breaker
api/            FastAPI surface and runtime endpoints
backtest/       Backtesting engine (class-based, MT5-independent)
ml/             Model training, feature engineering, and inference helpers
validation/     Statistical validation (bootstrap, WFO, deflated Sharpe)
monitoring/     Observability, health checks, and telemetry
strategies/     Strategy implementations and research notebooks
docker/         Container definitions and deployment artifacts
```

## Key Features

- **Phase-based development**: self-contained increments with full test coverage
- **Canary system**: drill types for resilience testing
- **Shadow mode**: parallel dry-run before live trading
- **Backtest engine**: deterministic, MT5-independent with multi-timeframe support
- **Statistical validation**: walk-forward, bootstrap, deflated Sharpe, PBO

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

## Status

Build: passing · Tests: ~2920 (0 fail) · Version: 0.2.0-dev

## License

Proprietary — Graxia OS
