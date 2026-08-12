# ADR-005: Data Format & Storage

**Status:** Accepted · **Date:** 2026-06-25

## Context
Multiple data formats evolved across phases: CSV (legacy backtest ticks), Parquet (feature matrices), DuckDB (warehouse), and MT5 direct feeds. Need a consistent storage strategy.

## Decision
- **Canonical offline storage**: DuckDB + Parquet (warehouse pattern in `data/warehouse/`)
- **Legacy compatibility**: CSV read support maintained for backtest fixtures
- **Feature storage**: Parquet partitioned by symbol/frequency in `artifacts/features/`
- **Manifests**: JSON files in `data/manifests/` tracking dataset provenance, hashes, row counts
- **No raw data committed to git**: `data/warehouse/`, `*.duckdb`, `*.parquet`, `*.pkl` are gitignored

## Consequences
- Migrating from CSV to Parquet is incremental (parallel readers exist)
- Warehouse queries via DuckDB for historical analysis without Python objects
- Manifests provide audit trail without storing large binary files in git
