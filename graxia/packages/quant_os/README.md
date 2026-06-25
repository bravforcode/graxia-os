# quant_os — Quantitative Trading Operating System

A modular Python framework for algorithmic trading research, backtesting, and live execution.

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
backtest/       Backtesting engine (class-based, MT5-independent)
canary/         Canary & demo campaign system (drills, monitoring)
core/           Core components (config, enums, ML pipeline, regime filter)
data/           Data loading, quality gate, warehouse (DuckDB/Parquet)
execution/      Order management, fill model, cost model, broker adapter
gold_bot/       Strategy implementations (13 strategies)
risk/           Pre-trade risk, position sizing, circuit breaker
shadow/         Shadow mode (canonical time, tick source, pipeline)
validation/     Statistical validation (bootstrap, WFO, deflated Sharpe)
```

## Key Features

- **Phase-based development**: self-contained increments with full test coverage
- **Canary system**: 13 drill types for resilience testing
- **Shadow mode**: parallel dry-run before live trading
- **Backtest engine**: deterministic, MT5-independent with multi-timeframe support
- **Statistical validation**: walk-forward, bootstrap, deflated Sharpe, PBO

## Commands

| `make test` | Run full test suite |
| `make lint` | Run ruff linter |
| `make format` | Auto-format code |
| `make coverage` | Run with coverage report |
| `make install-precommit` | Install git hooks |

## Status

Build: passing · Tests: 247+ (0 fail) · Version: 0.2.0-dev

## License

Proprietary — Graxia OS
