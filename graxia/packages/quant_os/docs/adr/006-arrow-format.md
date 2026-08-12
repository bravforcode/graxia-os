# ADR-006: Arrow/Feather Data Format

## Status
Accepted — Phase A (Week 1-2)

## Context
CSV is the default data format for historical OHLCV data. For datasets with millions of rows (tick data, multi-year minute bars), CSV parsing becomes a bottleneck. Arrow IPC / Feather format provides columnar storage with zero-copy reads, 5-10x faster load times, and 50% smaller files.

## Decision
Add Arrow/Feather support to `backtest/data_loader.py`:

1. `load_arrow(path)` — load `.arrow`, `.feather`, or `.parquet` files
2. `to_arrow(df, path)` — export DataFrame to Feather IPC format
3. Schema validation ensures DatetimeIndex + OHLCV columns
4. Optional dependency: `pyarrow` (clear error message if missing)

Key code path:
```python
# backtest/data_loader.py:287-336
def load_arrow(path: str) -> pd.DataFrame:
    pa = _require_pyarrow()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".feather":
        df = pd.read_feather(path, engine="pyarrow")
    elif ext == ".arrow":
        df = pd.read_feather(path, engine="pyarrow")
    elif ext == ".parquet":
        df = pd.read_parquet(path, engine="pyarrow")
    _validate_ohlcv_schema(df)
    return df

def to_arrow(df: pd.DataFrame, path: str) -> None:
    pa = _require_pyarrow()
    _validate_ohlcv_schema(df)
    df.reset_index().to_feather(path, engine="pyarrow")
```

## Consequences
+ 5-10x faster load vs CSV for large datasets
+ Columnar format reduces memory by ~50%
+ Schema validation catches bad data before backtest starts
+ Falls back gracefully with clear error when pyarrow missing
- Additional dependency (`pyarrow`) — not in base requirements
- Feather files not human-readable (unlike CSV)

## Schema Validation
```python
# backtest/data_loader.py:261-284
def _validate_ohlcv_schema(df: pd.DataFrame) -> None:
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")
    for col in OHLCV_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Column '{col}' must be numeric")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"Index must be DatetimeIndex")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Index must be sorted ascending")
```

## Usage
```python
from backtest.data_loader import load_arrow, to_arrow, load_csv_data

# Convert CSV to Arrow (one-time)
df = load_csv_data("data/XAUUSD_M15.csv")
to_arrow(df, "data/XAUUSD_M15.feather")

# Load Arrow in backtest (fast)
df = load_arrow("data/XAUUSD_M15.feather")
ohlcv = {col: df[col].tolist() for col in ["open", "high", "low", "close", "volume"]}
```

## Alternatives Considered
1. **Parquet only** — rejected: heavier dependency, less streaming-friendly
2. **HDF5** — rejected: complex licensing, declining community support
3. **Memory-mapped CSV** — rejected: no columnar benefit, still text parsing

## References
- `backtest/data_loader.py:243-336` — Arrow loader implementation
- `tests/test_arrow_loader_c2.py` — round-trip and schema validation tests
- `scripts/build_dataset.py` — Parquet export support
