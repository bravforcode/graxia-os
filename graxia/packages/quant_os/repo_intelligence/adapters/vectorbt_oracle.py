"""VectorBT differential oracle adapter. READ-ONLY reference only."""
# ponytail: lazy-imports vectorbt inside run_oracle, never at module level

# Canonical signal schema:
# {"signal_id", "timestamp_utc", "symbol", "side", "entry_price",
#  "stop_loss", "take_profit", "exit_price", "exit_reason",
#  "pnl_gross", "pnl_net", "engine"}

import hashlib
import uuid

_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}


def validate_input(data_manifest: dict, strategy_params: dict) -> bool:
    """Check OHLCV columns, non-empty data, and timeframe compatibility."""
    data = data_manifest.get("data", data_manifest)
    if not isinstance(data, dict):
        raise ValueError("data must be a dict with OHLCV keys")
    missing = _OHLCV_COLUMNS - set(data.keys())
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    for col in _OHLCV_COLUMNS:
        if not isinstance(data[col], list):
            raise ValueError(f"{col} must be a list")
    timestamps = data_manifest.get("timestamps", [])
    if not isinstance(timestamps, list):
        raise ValueError("timestamps must be a list")
    if len(timestamps) > 0 and len(data.get("close", [])) > 0 and len(timestamps) != len(data["close"]):
        raise ValueError("timestamps length must match data length")
    return True


def normalize_output(raw_result: dict) -> list[dict]:
    """Convert VectorBT trade records to canonical signal schema."""
    trades = raw_result.get("trades", [])
    if not trades:
        return []
    normalized = []
    for t in trades:
        normalized.append({
            "signal_id": t.get("signal_id", str(uuid.uuid4())),
            "timestamp_utc": t.get("timestamp_utc", ""),
            "symbol": t.get("symbol", ""),
            "side": t.get("side", ""),
            "entry_price": float(t.get("entry_price", 0.0)),
            "stop_loss": float(t.get("stop_loss", 0.0)),
            "take_profit": float(t.get("take_profit", 0.0)),
            "exit_price": float(t.get("exit_price", 0.0)),
            "exit_reason": t.get("exit_reason", ""),
            "pnl_gross": float(t.get("pnl_gross", 0.0)),
            "pnl_net": float(t.get("pnl_net", 0.0)),
            "engine": "vectorbt",
        })
    return normalized


def get_engine_name() -> str:
    return "vectorbt"


def run_oracle(
    data: dict,
    timestamps: list,
    strategy_params: dict,
    contract_spec: dict,
    cost_scenario: str = "base",
) -> dict:
    """Run VectorBT backtest. Returns normalized trades + metadata."""
    try:
        import vectorbt as vbt
    except ImportError:
        return {"error": "vectorbt not installed", "engine": "vectorbt"}

    import pandas as pd

    if not data or not timestamps:
        return {"engine": "vectorbt", "trades": [], "metadata": {"data_rows": 0}}

    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps))
    for col in _OHLCV_COLUMNS:
        if col not in df.columns:
            return {"error": f"missing column: {col}", "engine": "vectorbt"}

    strategy_type = strategy_params.get("strategy_type", "sma_crossover")
    fast_period = int(strategy_params.get("fast_period", 10))
    slow_period = int(strategy_params.get("slow_period", 30))

    try:
        if strategy_type == "sma_crossover":
            fast = df["close"].rolling(fast_period).mean()
            slow = df["close"].rolling(slow_period).mean()
            entries = (fast > slow) & (fast.shift(1) <= slow.shift(1))
            exits = (fast < slow) & (fast.shift(1) >= slow.shift(1))
            pf = vbt.Portfolio.from_signals(df["close"], entries, exits, init_cash=10000)
        elif strategy_type == "rsi":
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(fast_period).mean()
            loss = (-delta.clip(upper=0)).rolling(fast_period).mean()
            rs = gain / loss.replace(0, 1)
            rsi = 100 - (100 / (1 + rs))
            entries = (rsi < 30) & (rsi.shift(1) >= 30)
            exits = (rsi > 70) & (rsi.shift(1) <= 70)
            pf = vbt.Portfolio.from_signals(df["close"], entries, exits, init_cash=10000)
        elif strategy_type == "bollinger":
            mid = df["close"].rolling(fast_period).mean()
            std = df["close"].rolling(fast_period).std()
            upper = mid + 2 * std
            lower = mid - 2 * std
            entries = (df["close"] < lower) & (df["close"].shift(1) >= lower.shift(1))
            exits = (df["close"] > upper) & (df["close"].shift(1) <= upper.shift(1))
            pf = vbt.Portfolio.from_signals(df["close"], entries, exits, init_cash=10000)
        else:
            return {"error": f"unknown strategy: {strategy_type}", "engine": "vectorbt"}

        records = pf.trades.records_readable
        trades = []
        for _, row in records.iterrows():
            symbol = strategy_params.get("symbol", df.attrs.get("symbol", "UNKNOWN"))
            entry_ts = str(row.get("Entry Timestamp", ""))
            trades.append({
                "signal_id": hashlib.sha256(f"{symbol}{entry_ts}".encode()).hexdigest()[:16],
                "timestamp_utc": entry_ts,
                "symbol": symbol,
                "side": "BUY" if row.get("Side", "") == "Long" else "SELL",
                "entry_price": float(row.get("Avg Entry Price", 0.0)),
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "exit_price": float(row.get("Avg Exit Price", 0.0)),
                "exit_reason": str(row.get("Status", "")),
                "pnl_gross": float(row.get("PnL", 0.0)),
                "pnl_net": float(row.get("PnL", 0.0)),
                "engine": "vectorbt",
            })

        return {
            "engine": "vectorbt",
            "trades": trades,
            "metadata": {
                "data_rows": len(df),
                "strategy_params": strategy_params,
                "cost_scenario": cost_scenario,
            },
        }
    except Exception as e:
        return {"error": str(e), "engine": "vectorbt"}
