# ADR-004: MT5 Dependency Strategy

**Status:** Accepted · **Date:** 2026-06-25

## Context
The backtest engine originally imported MetaTrader5 at module level, causing test collection failures in CI environments without MT5 installed. This made the test suite unreliable outside the trading terminal.

## Decision
- `backtest/engine.py` uses a class-based `BacktestEngine` that does NOT import MT5 at module level
- MT5 is only used by standalone scripts (`run_backtest.py`, `run_backtest_real.py`)
- All CI-tested code paths must be MT5-independent
- MT5-dependent code must fail early with a clear error message
- The `.env.example` documents MT5_* variables without default secrets

## Consequences
- Tests run on any Python environment without MT5 installed ✅
- MT5 scripts need manual setup with credentials via `.env`
- New contributors can run 247+ tests without MT5
