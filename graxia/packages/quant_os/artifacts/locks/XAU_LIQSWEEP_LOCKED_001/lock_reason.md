# XAU_LIQSWEEP_LOCKED_001 — Lock Manifest

**Phase:** G0.1 — Freeze XAU candidate evidence artifacts
**Frozen at:** 2026-06-22T07:44:00Z
**Baseline commit:** `0be33752c9d38065a8e2d09413898f61e8981843`

## Why this lock exists

The `liquidity_sweep` strategy for XAUUSD is in `CANDIDATE_ONLY` status (per STATUS.md). This lock freezes all source artifacts, configuration, dataset manifests, contract snapshots, and backtest assumptions at a known-good commit to establish an immutable evidence baseline before any promotion decision (Phase G0.2+) or parameter mutation.

## What is locked

### Strategy source
- `gold_bot/strategies/liquidity_sweep.py` — Core strategy logic (2915 bytes)
- `backtest/mtf_cursor.py` — Multi-timeframe cursor for D1/H1/M15 context switching
- `risk/risk_policy.py` — Position sizing and risk guardrails
- `broker/contract_spec.py` — Contract specification (symbol, lot size, tick value)
- `broker/contract_snapshot_store.py` — Immutable contract snapshot binding (CONSTITUTION INV-010/INV-011)

### Execution config
- `execution/broker_adapter.py` — MT5 execution bridge

### Strategy config / assumptions
- `gold_bot/core/config.py` — Strategy registry and multipliers
- `core/config.py` — Global config (symbol list, risk params)
- `backtest/engine.py` — Backtest engine with commission_per_lot=3.5, spread_pips, slippage_pips assumptions

### Dataset manifests
- `data/manifests/XAUUSD_D1.manifest.json` — D1 context data
- `data/manifests/XAUUSD_H1.manifest.json` — H1 context data
- `data/manifests/XAUUSD_M15.manifest.json` — M15 primary strategy timeframe

### Backtest results
- `results/backtest_results.json` — Existing backtest evidence

## Lock integrity rules

1. No file listed above may be mutated while this lock is active without re-hashing and updating this manifest.
2. Any promotion decision (G0.2+) must reference this lock_id and baseline_commit.
3. SHA-256 hashes serve as the ground truth for artifact integrity verification.
