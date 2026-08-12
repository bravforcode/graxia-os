# GRAXIA-OS v3.0 — Library Integration Map

> Source: `Meta/graxia_mega_plan_v3.md` §3 + verification run 2026-06-26

## Library Status Summary

| Status | Count | Meaning |
|--------|-------|---------|
| ✅ OK  | 26    | Installed, import works |
| ⚠️ ALT | 1     | Substitute package needed |
| ❌ FAIL | 2     | Not installable (see workarounds) |

## Integration Table

| Library | Version | Module(s) | Purpose | Status |
|---------|---------|-----------|---------|--------|
| **pandera** | 0.32.0 | `core/schemas.py` | OHLCV schema validation (XAUUSD_M15_SCHEMA) | ✅ OK |
| **deepchecks** | 0.19.1 | `core/data_quality.py` (planned) | Automated dataset integrity checks | ❌ FAIL (max_error scorer removed in sklearn 1.9) |
| **smartmoneyconcepts** | 0.0.27 | `scripts/features_advanced.py` | Order Block, FVG, BOS, CHoCH, liquidity sweep, swing H/L | ⚠️ OK* (needs PYTHONIOENCODING=utf-8) |
| **jumpmodels** | 0.1.1 | `core/regime_detector.py` | PRIMARY regime detection (Sparse JM, Continuous JM) | ✅ OK |
| **hmmlearn** | 0.3.3 | `core/regime_detector.py` | SECONDARY regime detection (cross-check model) | ✅ OK |
| **skfolio** | 0.20.1 | `core/cross_validation.py` | CombinatorialPurgedCV (purged_size + embargo_size) | ✅ OK |
| **pypbo** | — | `validation/deflated_sharpe.py` (planned) | Deflated Sharpe Ratio, PBO, PSR | ❌ FAIL (not on PyPI) |
| **cot_reports** | 0.1.3 | `scripts/ingest_alternative.py` | Automated CFTC COT report fetching | ✅ OK |
| **mlfinpy** | 0.1.2 | `core/ml_pipeline.py` | Triple-barrier labels, frac-diff, microstructural features | ✅ OK |
| **vectorbt** | 1.0.0 | `backtest/engine.py`, `scripts/walk_forward.py` | Primary research backtest engine | ✅ OK |
| **nautilus_trader** | 1.221.0 | `shadow/canonical_bar_builder.py` (offline) | Secondary backtest cross-check (Dukascopy bars only) | ✅ OK |
| **fracdiff2** | 1.1 | `core/ml_pipeline.py` | Fractional differentiation for stationarity | ✅ OK (was `fracdiff`) |
| **river** | 0.25.0 | `core/regime_filter.py` | ADWIN drift detection, incremental ML | ✅ OK |
| **pandas** | 2.3.3 | All modules | DataFrames, time-series manipulation | ✅ OK |
| **numpy** | 2.4.6 | All modules | Numerical arrays, linear algebra | ✅ OK |
| **scipy** | 1.17.1 | `validation/bootstrap_sensitivity.py` | Statistical distributions, optimization | ✅ OK |
| **scikit-learn** | 1.9.0 | `core/ml_pipeline.py`, `validation/` | ML models, metrics, preprocessing | ✅ OK |
| **xgboost** | 3.2.0 | `core/ml_pipeline.py` | Gradient boosting models | ✅ OK |
| **matplotlib** | 3.11.0 | `core/dashboard.py`, `reports/` | Static charting | ✅ OK |
| **seaborn** | 0.13.2 | `reports/`, `validation/` | Statistical visualizations | ✅ OK |
| **plotly** | 6.8.0 | `core/dashboard.py`, `dashboard.html` | Interactive charts | ✅ OK |
| **pyarrow** | 24.0.0 | `data/pipeline.py`, `scripts/convert_to_parquet.py` | Parquet I/O, columnar data | ✅ OK |
| **duckdb** | 1.5.4 | `data/warehouse.py` (planned) | Embedded OLAP, SQL on Parquet | ✅ OK |
| **MetaTrader5** | 5.0.5735 | `broker/mt5_gateway.py`, `live_readiness/` | Live order routing, symbol info, tick data | ✅ OK |
| **requests** | 2.33.0 | `core/telegram_notify.py`, `api/webhook.py` | HTTP/TLS for APIs | ✅ OK |
| **python-dotenv** | 1.2.2 | `core/config.py` | Environment variable loading | ✅ OK |
| **tomli** | 2.4.1 | `core/config.py` | TOML config parsing | ✅ OK |
| **optuna** | 4.9.0 | `core/hyperopt.py` | Hyperparameter optimization | ✅ OK |

## Known Issues & Workarounds

### deepchecks (❌ FAIL)
- **Error**: `ValueError: 'max_error' is not a valid scoring value`
- **Cause**: scikit-learn 1.9.0 removed `max_error` from `_SCORERS`. deepchecks 0.19.1 hardcodes it.
- **Fix**: `pip install deepchecks==0.18.1 scikit-learn==1.5.2` (or wait for deepchecks 0.20+)
- **Impact**: Low. pandera + custom `validate_ohlcv()` in `core/schemas.py` cover the same use case.

### pypbo (❌ FAIL)
- **Error**: Not on PyPI (`pip install pypbo` → no matching distribution)
- **Git**: `github.com/esvhd/pypbo` has no `setup.py` or `pyproject.toml`
- **Fix**: Implement PBO/DSR/PSR directly from Bailey & Lopez de Prado (2014, 2015). The math is well-documented in their papers; code for PSR ≈ 15 lines.
- **Impact**: Medium. PBO/DSR are important for honest backtest evaluation. Manual implementation is viable.

### smartmoneyconcepts (⚠️ OK*)
- **Warning**: `UnicodeEncodeError` on Windows cp1252 terminals (emoji in print statement)
- **Fix**: Set `$env:PYTHONIOENCODING='utf-8'` before running Python scripts.
- **Impact**: Cosmetic only. Library functions work correctly.

### fracdiff (⚠️ ALT)
- **Note**: Package renamed from `fracdiff` to `fracdiff2` on PyPI.
- **Fix**: Use `import fracdiff2` instead of `import fracdiff`.
- **Impact**: None. Same functionality, different import name.

### mlfinlab (⚠️ COMMERCIAL)
- **Note**: Closed-source / commercial since ~2021 by Hudson & Thames.
- **Replacement**: `mlfinpy==0.1.2` (open-source community reimplementation) installed.
- **Per mega plan**: Triple-barrier labeling and fractional differentiation are short enough to implement directly. See `Meta/graxia_mega_plan_v3.md` §11A for code.

## Numba / NumPy Compatibility

- `numba==0.65.1` + `numpy==2.4.6` is the working combination
- `numba<0.65` (e.g., 0.60.0 installed by mlfinpy) requires `numpy<2.1` — upgrade numba to 0.65.1 if imports fail
- `llvmlite==0.47.0` must match numba version

## NautilusTrader: Scope Limitation (v3 Correction)

Per mega plan Finding F3: NautilusTrader has **no MetaTrader5 adapter**. Its stable integrations are IB, Binance, Bybit, Coinbase, Deribit, dYdX, Hyperliquid, Kraken, OKX, Polymarket, Betfair, BitMEX — no FX/CFD MT5 venue.

**Usage in GRAXIA-OS**: Offline only, on historical Dukascopy Parquet bars, as a second independent backtest engine to cross-check VectorBT results. Live execution stays on the `MetaTrader5` Python package talking directly to Pepperstone.
