# Phase 3.1 Summary — Canonical Engine Integration

## Goal
Wire all Phase 2/3 components into backtest/engine.py

## Changes
- Replaced inline sizing with HistoricalSizingProvider (deterministic, no MT5)
- Replaced close-price fills with ConservativeBarFillModel (bid/ask, t+1)
- Integrated CostModel (spread, slippage, commission per trade)
- Integrated OrderStateMachine (state transitions for every order)
- Integrated TradeLedger (immutable records with provenance)
- Added explicit swap policy (Option A: model swap for D1)
- strict_mtf=True default
- CRITICAL_INCIDENT on missing SL

## Tests
24 integration tests covering all rules.

## Status
IN PROGRESS — awaiting test verification
