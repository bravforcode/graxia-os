"""Backtesting.py differential oracle adapter."""
# ponytail: lazy-imports backtesting only inside run_oracle; no module-level dep

import uuid
from datetime import UTC, datetime


def validate_input(data_manifest: dict, strategy_params: dict) -> bool:
    """Check data format compatibility before running Backtesting.py.

    Returns True if valid, raises ValueError otherwise.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    columns = data_manifest.get("columns", set())
    if not required.issubset(set(columns)):
        missing = required - set(columns)
        raise ValueError(f"Missing OHLCV columns: {missing}")

    freq = data_manifest.get("frequency")
    if freq and freq not in ("1m", "5m", "15m", "30m", "1h", "1d"):
        raise ValueError(f"Unsupported frequency: {freq}")

    return True


def normalize_output(raw_result: dict, symbol: str = "UNKNOWN") -> list[dict]:
    """Convert Backtesting.py stats/trades to canonical signal format.

    Args:
        raw_result: dict with 'trades' DataFrame or 'stats' from bt.run()
        symbol: ticker symbol for the canonical output
    """
    trades = raw_result.get("trades", [])
    signals = []

    for _, row in trades.iterrows():
        signal_id = f"bt-{uuid.uuid4().hex[:12]}"
        entry_time = row.get("EntryTime", datetime.now(UTC))
        if hasattr(entry_time, "isoformat"):
            entry_time = entry_time.isoformat()

        pnl_gross = float(row.get("PnL", 0.0))
        size = float(row.get("Size", 0))
        entry_price = float(row.get("EntryPrice", 0))
        exit_price = float(row.get("ExitPrice", 0))
        exit_reason = str(row.get("ExitReason", "unknown"))
        side = "long" if size > 0 else "short"

        # ponytail: net = gross for now; add commission calc when needed
        signals.append(
            {
                "signal_id": signal_id,
                "timestamp_utc": str(entry_time),
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "pnl_gross": pnl_gross,
                "pnl_net": pnl_gross,
                "engine": "backtesting_py",
            }
        )

    return signals


def run_oracle(
    data: dict,
    timestamps: list,
    strategy_params: dict,
    contract_spec: dict,
    cost_scenario: str = "base",
) -> dict:
    """Run Backtesting.py backtest in isolated mode (lazy import)."""
    try:
        import pandas as pd
        from backtesting import Backtest, Strategy
    except ImportError:
        return {"error": "backtesting not installed", "engine": "backtesting_py"}

    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps))

    class OracleStrategy(Strategy):
        def init(self):
            pass

        def next(self):
            pass

    cash = strategy_params.get("cash", 10000)
    commission = _commission_for_scenario(cost_scenario)

    bt = Backtest(df, OracleStrategy, cash=cash, commission=commission)
    stats = bt.run()
    trades_df = stats.get("_trades", pd.DataFrame())

    symbol = contract_spec.get("symbol", df.attrs.get("symbol", "UNKNOWN"))
    signals = normalize_output({"trades": trades_df}, symbol=symbol)

    return {
        "engine": "backtesting_py",
        "trades": signals,
        "metadata": {"data_rows": len(df), "stats_keys": list(stats.index)},
    }


def get_engine_name() -> str:
    return "backtesting_py"


def _commission_for_scenario(scenario: str) -> float:
    # ponytail: flat mapping, expand if scenario count grows
    return {"zero": 0.0, "base": 0.001, "high": 0.003}.get(scenario, 0.001)
